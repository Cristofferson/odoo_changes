# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class XiboMediaUploadWizard(models.TransientModel):
    _name = 'xibo.media.upload.wizard'
    _description = 'Bulk Upload to Xibo'

    server_id = fields.Many2one('xibo.server', string='Server', required=True)
    line_ids = fields.One2many('xibo.media.upload.wizard.line', 'wizard_id', string='Files')
    default_duration = fields.Integer(string='Default Duration (s)', default=10)
    default_tags = fields.Char(string='Default Tags')

    def action_do_upload(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Add at least one file."))
        Media = self.env['xibo.media']
        created = self.env['xibo.media']
        for line in self.line_ids:
            media = Media.create({
                'name': line.name or line.file_name,
                'file_data': line.file_data,
                'file_name': line.file_name,
                'duration': self.default_duration,
                'tags': self.default_tags,
                'server_id': self.server_id.id,
            })
            media.action_upload_to_xibo()
            created |= media
        return {
            'type': 'ir.actions.act_window',
            'name': _('Uploaded Media'),
            'res_model': 'xibo.media',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }


class XiboMediaUploadWizardLine(models.TransientModel):
    _name = 'xibo.media.upload.wizard.line'
    _description = 'Bulk Upload Line'

    wizard_id = fields.Many2one('xibo.media.upload.wizard', required=True, ondelete='cascade')
    name = fields.Char(string='Display Name')
    file_data = fields.Binary(required=True)
    file_name = fields.Char(required=True)
