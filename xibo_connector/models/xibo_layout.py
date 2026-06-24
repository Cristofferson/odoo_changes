# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class XiboLayout(models.Model):
    _name = 'xibo.layout'
    _description = 'Xibo Layout'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    server_id = fields.Many2one('xibo.server', required=True, ondelete='cascade', tracking=True)
    xibo_layout_id = fields.Integer(string='Xibo Layout ID', readonly=True, copy=False)
    xibo_campaign_id = fields.Integer(
        string='Xibo Campaign ID', readonly=True, copy=False,
        help="In Xibo, layouts are scheduled via their campaign id.",
    )
    description = fields.Text(readonly=True)
    is_overlay = fields.Boolean(
        string='Overlay-Capable',
        help="Mark layouts you designed as overlays (small region with transparent background).",
    )
    duration = fields.Integer(string='Default Duration (s)', default=10)
    tags = fields.Char(readonly=True)
    width = fields.Integer(readonly=True)
    height = fields.Integer(readonly=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(related='server_id.company_id', store=True)

    _sql_constraints = [
        ('xibo_id_unique', 'unique(server_id, xibo_layout_id)',
         'This layout is already registered for this server.'),
    ]

    @api.model
    def _sync_from_server(self, server):
        payload = server._request('GET', '/api/layout')
        if not isinstance(payload, list):
            return False
        existing = {l.xibo_layout_id: l for l in self.search([('server_id', '=', server.id)])}
        for entry in payload:
            xid = entry.get('layoutId')
            if not xid:
                continue
            values = {
                'name': entry.get('layout') or _('Unnamed layout'),
                'server_id': server.id,
                'xibo_layout_id': xid,
                'xibo_campaign_id': entry.get('campaignId') or 0,
                'description': entry.get('description'),
                'duration': entry.get('duration') or 10,
                'tags': entry.get('tags'),
                'width': entry.get('width') or 0,
                'height': entry.get('height') or 0,
            }
            if xid in existing:
                existing[xid].write(values)
            else:
                self.create(values)
        _logger.info("Xibo: synced %s layouts for %s", len(payload), server.name)
        return True

    def action_open_in_cms(self):
        self.ensure_one()
        if not self.xibo_layout_id:
            return False
        return {
            'type': 'ir.actions.act_url',
            'url': f"{self.server_id.url}/layout/designer/{self.xibo_layout_id}",
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # Layout creation from Quick Display
    # -------------------------------------------------------------------------
    @api.model
    def _create_simple_image_layout(self, server, media, name, resolution_id=1):
        """Create a minimalist Xibo layout containing a single full-screen
        image widget for the given media. Returns the new xibo.layout record.

        :param server: xibo.server record
        :param media: xibo.media record (must have xibo_media_id set)
        :param name: layout name in Xibo
        :param resolution_id: Xibo resolutionId (1 = HD 1920x1080 in most installs)
        """
        if not (media and media.xibo_media_id):
            raise UserError(_("Media must already be uploaded to Xibo first."))

        # 1) Create the layout
        layout_resp = server._request('POST', '/api/layout', data={
            'name': name,
            'description': _('Auto-created by Odoo Xibo Connector'),
            'resolutionId': resolution_id,
        })
        layout_id = layout_resp.get('layoutId')
        if not layout_id:
            raise UserError(_("Xibo did not return a layoutId. Response: %s") % layout_resp)
        campaign_id = layout_resp.get('campaignId') or 0

        # 2) Get the first region (Xibo creates a default one)
        layout_detail = server._request('GET', f'/api/layout',
                                        params={'layoutId': layout_id, 'embed': 'regions,playlists,widgets'})
        region_id = None
        playlist_id = None
        if isinstance(layout_detail, list) and layout_detail:
            regions = layout_detail[0].get('regions') or []
            if regions:
                region_id = regions[0].get('regionId')
                # The playlist is inside the region
                pls = regions[0].get('regionPlaylist') or regions[0].get('playlists') or []
                if isinstance(pls, list) and pls:
                    playlist_id = pls[0].get('playlistId')
                elif isinstance(pls, dict):
                    playlist_id = pls.get('playlistId')

        if not playlist_id and region_id:
            # Fall back: query region's playlist
            try:
                region_data = server._request('GET', f'/api/region/{region_id}', raise_on_error=False)
                if isinstance(region_data, dict):
                    pls = region_data.get('regionPlaylist') or {}
                    playlist_id = pls.get('playlistId')
            except Exception:
                pass

        if not playlist_id:
            raise UserError(_("Could not locate the default playlist for the new layout. "
                              "You may need to edit it manually in Xibo."))

        # 3) Add the image widget pointing to our media
        server._request('POST', f'/api/playlist/widget/image/{playlist_id}',
                        data={
                            'mediaId[]': [media.xibo_media_id],
                            'duration': media.duration or 10,
                            'useDuration': 1,
                        })

        # 4) Checkout & Publish so it becomes schedulable
        try:
            server._request('PUT', f'/api/layout/checkout/{layout_id}', raise_on_error=False)
        except Exception:
            pass
        publish_resp = server._request('PUT', f'/api/layout/publish/{layout_id}',
                                       data={'publishNow': 1}, raise_on_error=False)
        if isinstance(publish_resp, dict) and publish_resp.get('layoutId'):
            # After publish Xibo returns a new layoutId (a draft is replaced)
            final_layout_id = publish_resp.get('layoutId')
            final_campaign_id = publish_resp.get('campaignId') or campaign_id
        else:
            final_layout_id = layout_id
            final_campaign_id = campaign_id

        # 5) Mirror in Odoo
        new_layout = self.create({
            'name': name,
            'server_id': server.id,
            'xibo_layout_id': final_layout_id,
            'xibo_campaign_id': final_campaign_id,
            'duration': media.duration or 10,
            'description': _('Auto-created from media "%s"') % media.name,
        })
        return new_layout
