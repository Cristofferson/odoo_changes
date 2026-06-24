# -*- coding: utf-8 -*-
import base64
import io
import logging
import mimetypes

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def _success_reload(message):
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': _("Done"),
            'message': message,
            'type': 'success',
            'sticky': False,
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
        },
    }


class XiboMedia(models.Model):
    _name = 'xibo.media'
    _description = 'Xibo Media (Library Item)'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(string='Name', required=True, tracking=True)
    server_id = fields.Many2one('xibo.server', required=True, ondelete='restrict', tracking=True)
    xibo_media_id = fields.Integer(string='Xibo Media ID', readonly=True, copy=False)

    # Local binary (only set for files originally uploaded from Odoo)
    file_data = fields.Binary(string='File', attachment=True)
    file_name = fields.Char(string='Filename')
    file_type = fields.Selection(
        [('image', 'Image'), ('video', 'Video'), ('audio', 'Audio'), ('other', 'Other')],
        compute='_compute_file_type', store=True,
    )
    duration = fields.Integer(
        string='Duration (seconds)', default=10,
        help="How long this media is shown in a layout. Set 0 for video's actual length.",
    )
    tags = fields.Char(string='Tags', help="Comma separated Xibo tags.")
    description = fields.Text()
    size_bytes = fields.Integer(string='File Size (bytes)', readonly=True)
    origin = fields.Selection(
        [('odoo', 'Uploaded from Odoo'),
         ('xibo', 'Pre-existing in Xibo Library')],
        default='odoo', readonly=True, copy=False,
        help="Tracks whether the binary lives in Odoo or only in Xibo.",
    )

    state = fields.Selection(
        [('draft', 'Draft'),
         ('uploaded', 'Uploaded to Xibo'),
         ('xibo_only', 'In Xibo (no local copy)'),
         ('error', 'Error')],
        default='draft', tracking=True, readonly=True,
    )
    last_error = fields.Text(readonly=True)
    company_id = fields.Many2one(related='server_id.company_id', store=True)

    _sql_constraints = [
        ('xibo_id_unique_per_server', 'unique(server_id, xibo_media_id)',
         'This Xibo media is already registered for this server.'),
    ]

    @api.depends('file_name')
    def _compute_file_type(self):
        for rec in self:
            if not rec.file_name:
                rec.file_type = 'other'
                continue
            mime, _enc = mimetypes.guess_type(rec.file_name)
            if not mime:
                rec.file_type = 'other'
            elif mime.startswith('image/'):
                rec.file_type = 'image'
            elif mime.startswith('video/'):
                rec.file_type = 'video'
            elif mime.startswith('audio/'):
                rec.file_type = 'audio'
            else:
                rec.file_type = 'other'

    @api.constrains('file_data', 'file_name')
    def _check_file(self):
        for rec in self:
            if rec.file_data and not rec.file_name:
                raise ValidationError(_("Filename is required when uploading a file."))

    # -------------------------------------------------------------------------
    # Sync from Xibo (metadata only)
    # -------------------------------------------------------------------------
    @api.model
    def _sync_from_server(self, server):
        """Pull Library metadata from Xibo. Does NOT download binaries.

        Pre-existing items get state='xibo_only' so users see them in Odoo
        and can reference them in broadcasts/layouts without duplicating bytes.
        """
        try:
            payload = server._request('GET', '/api/library', raise_on_error=False)
        except Exception:
            return False
        if not isinstance(payload, list):
            return False

        existing = {m.xibo_media_id: m for m in self.search([
            ('server_id', '=', server.id),
            ('xibo_media_id', '!=', 0),
        ])}

        count = 0
        for entry in payload:
            xid = entry.get('mediaId')
            if not xid:
                continue
            mtype = (entry.get('mediaType') or '').lower()
            file_type = 'other'
            if mtype in ('image', 'picture'):
                file_type = 'image'
            elif mtype in ('video',):
                file_type = 'video'
            elif mtype in ('audio',):
                file_type = 'audio'

            values = {
                'name': entry.get('name') or _('Unnamed media'),
                'server_id': server.id,
                'xibo_media_id': xid,
                'file_name': entry.get('storedAs') or entry.get('fileName') or '',
                'duration': entry.get('duration') or 10,
                'tags': entry.get('tags') or '',
                'size_bytes': entry.get('fileSize') or 0,
            }
            if xid in existing:
                # Update only safe fields (don't overwrite local file_data)
                m = existing[xid]
                m.write({
                    'name': values['name'],
                    'duration': values['duration'],
                    'tags': values['tags'],
                    'size_bytes': values['size_bytes'],
                })
            else:
                values.update({
                    'origin': 'xibo',
                    'state': 'xibo_only',
                })
                self.create(values)
                count += 1
        _logger.info("Xibo: synced %s new media entries for %s", count, server.name)
        return True

    # -------------------------------------------------------------------------
    # Upload to Xibo
    # -------------------------------------------------------------------------
    def action_upload_to_xibo(self):
        for rec in self:
            rec._upload()
        return _success_reload(_("%s media file(s) uploaded to Xibo.") % len(self))

    def _upload(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_("There is no file to upload. Attach a file first."))
        if self.xibo_media_id:
            raise UserError(_("This media is already linked to Xibo. Use 'Update' or 'Replace File' instead."))

        # Pre-validate extension (helps catch AVIF and other CMS-rejected types
        # with a clearer message before round-tripping to Xibo)
        safe_extensions = {
            'image': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'},
            'video': {'mp4', 'webm', 'mov', 'avi', 'mkv', 'mpg', 'mpeg'},
            'audio': {'mp3', 'ogg', 'wav', 'aac', 'm4a'},
        }
        ext = (self.file_name or '').lower().rsplit('.', 1)[-1] if '.' in (self.file_name or '') else ''
        if ext and ext in {'avif', 'heic', 'heif'}:
            raise UserError(_(
                "Xibo CMS typically does not enable the .%(ext)s extension by default. "
                "Either convert the file to PNG, JPEG or WebP, or enable the matching "
                "module in your Xibo CMS (Modules section) and add '%(ext)s' to its "
                "valid extensions list."
            ) % {'ext': ext})

        raw = base64.b64decode(self.file_data)
        mime, _enc = mimetypes.guess_type(self.file_name)
        files = {'files': (self.file_name, io.BytesIO(raw), mime or 'application/octet-stream')}
        data = {'name': self.name}
        if self.tags:
            data['tags'] = self.tags

        try:
            payload = self.server_id._request('POST', '/api/library', data=data, files=files)
        except Exception as e:
            self.write({'state': 'error', 'last_error': str(e)})
            raise

        files_resp = payload.get('files') or []
        if not files_resp:
            raise UserError(_("Xibo did not return a mediaId. Response: %s") % payload)
        first = files_resp[0]
        media_id = first.get('mediaId')
        # Detect Xibo soft errors (it returns 200 even when the file is rejected)
        if not media_id and first.get('error'):
            err_msg = first.get('error')
            self.write({'state': 'error', 'last_error': err_msg})
            raise UserError(_("Xibo rejected the file: %s") % err_msg)
        if not media_id:
            raise UserError(_("Xibo response missing mediaId: %s") % payload)

        if self.duration:
            self.server_id._request(
                'PUT', f'/api/library/{media_id}',
                json_body={'name': self.name, 'duration': self.duration},
                raise_on_error=False,
            )

        self.write({
            'xibo_media_id': media_id,
            'state': 'uploaded',
            'origin': 'odoo',
            'size_bytes': len(raw),
            'last_error': False,
        })
        self.message_post(body=_("Uploaded to Xibo as mediaId %s.") % media_id)

    def action_update_in_xibo(self):
        for rec in self:
            if not rec.xibo_media_id:
                raise UserError(_("Media not yet uploaded — use 'Upload' first."))
            rec.server_id._request(
                'PUT', f'/api/library/{rec.xibo_media_id}',
                json_body={
                    'name': rec.name,
                    'duration': rec.duration or 0,
                    'tags': rec.tags or '',
                },
            )
            rec.message_post(body=_("Metadata updated in Xibo."))
        return _success_reload(_("Metadata updated."))

    def action_delete_from_xibo(self):
        for rec in self:
            if rec.xibo_media_id:
                try:
                    rec.server_id._request('DELETE', f'/api/library/{rec.xibo_media_id}')
                except Exception as e:
                    rec.write({'state': 'error', 'last_error': str(e)})
                    raise
        self.unlink()
        return {'type': 'ir.actions.act_window_close'}

    def action_open_in_cms(self):
        self.ensure_one()
        if not self.xibo_media_id:
            return False
        return {
            'type': 'ir.actions.act_url',
            'url': f"{self.server_id.url}/library/view",
            'target': 'new',
        }

    def action_open_quick_display_wizard(self):
        """Open the wizard to broadcast this media to displays in one click."""
        self.ensure_one()
        if not self.xibo_media_id:
            raise UserError(_("Upload the media to Xibo first."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Quick Display'),
            'res_model': 'xibo.quick.display.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_media_id': self.id,
                'default_server_id': self.server_id.id,
            },
        }

    def unlink(self):
        for rec in self:
            if rec.xibo_media_id and rec.state == 'uploaded' and rec.origin == 'odoo':
                _logger.warning(
                    "Deleting xibo.media %s while Xibo mediaId %s still exists. "
                    "Use 'Delete from Xibo' to remove the remote copy too.",
                    rec.id, rec.xibo_media_id,
                )
        return super().unlink()
