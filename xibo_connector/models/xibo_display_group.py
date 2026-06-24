# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class XiboDisplayGroup(models.Model):
    _name = 'xibo.display.group'
    _description = 'Xibo Display Group'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Group Name', required=True, tracking=True)
    server_id = fields.Many2one('xibo.server', required=True, ondelete='cascade', tracking=True)
    xibo_display_group_id = fields.Integer(string='Xibo Display Group ID', readonly=True, copy=False)
    description = fields.Text()
    is_display_specific = fields.Boolean(string='Display-Specific Group', readonly=True)
    active = fields.Boolean(default=True, tracking=True)
    company_id = fields.Many2one(related='server_id.company_id', store=True)
    display_ids = fields.Many2many(
        'xibo.display', 'xibo_display_group_display_rel',
        'group_id', 'display_id', string='Displays',
    )

    _sql_constraints = [
        ('xibo_id_unique', 'unique(server_id, xibo_display_group_id)',
         'This Xibo display group is already registered for this server.'),
    ]

    @api.model
    def _sync_from_server(self, server):
        payload = server._request('GET', '/api/displaygroup')
        if not isinstance(payload, list):
            return False
        existing = {g.xibo_display_group_id: g
                    for g in self.search([('server_id', '=', server.id)])}
        for entry in payload:
            xid = entry.get('displayGroupId')
            if not xid:
                continue
            values = {
                'name': entry.get('displayGroup') or _('Unnamed group'),
                'server_id': server.id,
                'xibo_display_group_id': xid,
                'description': entry.get('description'),
                'is_display_specific': bool(entry.get('isDisplaySpecific')),
            }
            if xid in existing:
                existing[xid].write(values)
            else:
                self.create(values)
        _logger.info("Xibo: synced %s display groups for %s", len(payload), server.name)
        return True

    def action_collect_now(self):
        for rec in self:
            if rec.xibo_display_group_id:
                rec.server_id._trigger_collect_now([rec.xibo_display_group_id])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Refresh sent"),
                'message': _("XMR collectNow dispatched."),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_in_cms(self):
        self.ensure_one()
        if not self.xibo_display_group_id:
            return False
        return {
            'type': 'ir.actions.act_url',
            'url': f"{self.server_id.url}/displaygroup/view",
            'target': 'new',
        }
