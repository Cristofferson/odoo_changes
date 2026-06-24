# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class XiboQuickDisplayWizard(models.TransientModel):
    _name = 'xibo.quick.display.wizard'
    _description = 'Quick Display Wizard'

    media_id = fields.Many2one('xibo.media', string='Media', required=True)
    server_id = fields.Many2one('xibo.server', string='Server', required=True)
    layout_name = fields.Char(
        string='Layout Name', required=True,
        default=lambda self: _('Quick Display'),
    )
    display_ids = fields.Many2many(
        'xibo.display', string='Displays',
        domain="[('server_id', '=', server_id)]",
    )
    display_group_ids = fields.Many2many(
        'xibo.display.group', string='Display Groups',
        domain="[('server_id', '=', server_id)]",
    )
    duration_seconds = fields.Integer(string='Show For (s)', default=30)
    display_mode = fields.Selection(
        [('overlay', 'Overlay popup'),
         ('fullscreen', 'Full-screen')],
        default='overlay', required=True,
    )
    show_until = fields.Datetime(
        string='Until',
        default=lambda self: fields.Datetime.now() + timedelta(hours=1),
        required=True,
    )
    instant_push = fields.Boolean(default=True, string='Push Now')

    resolution_id = fields.Integer(
        string='Resolution ID', default=1,
        help="Xibo resolutionId. In most installs: 1 = HD 1920x1080 landscape.",
    )

    @api.onchange('media_id')
    def _onchange_media_id(self):
        if self.media_id:
            self.server_id = self.media_id.server_id
            if self.media_id.duration:
                self.duration_seconds = self.media_id.duration

    def action_create_and_broadcast(self):
        self.ensure_one()
        if not self.media_id.xibo_media_id:
            raise UserError(_("The selected media is not uploaded to Xibo yet."))
        if not (self.display_ids or self.display_group_ids):
            raise UserError(_("Select at least one display or display group."))

        # 1) Create a simple layout in Xibo with the image full-screen
        layout = self.env['xibo.layout']._create_simple_image_layout(
            self.server_id, self.media_id,
            self.layout_name, resolution_id=self.resolution_id,
        )

        # 2) Broadcast it
        broadcast = self.env['xibo.broadcast'].quick_send(
            server=self.server_id,
            mode=self.display_mode,
            layout=layout,
            displays=self.display_ids,
            display_groups=self.display_group_ids,
            duration=self.duration_seconds,
            instant=self.instant_push,
            origin=('xibo.media', self.media_id.id,
                    _("Quick Display of '%s'") % self.media_id.name),
            name=_("Quick: %s") % self.media_id.name,
        )
        # Adjust to_dt to user's chosen end
        broadcast.write({'to_dt': self.show_until})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Broadcast'),
            'res_model': 'xibo.broadcast',
            'view_mode': 'form',
            'res_id': broadcast.id,
            'target': 'current',
        }
