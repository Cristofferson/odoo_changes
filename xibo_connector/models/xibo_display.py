# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class XiboDisplay(models.Model):
    _name = 'xibo.display'
    _description = 'Xibo Display / Player'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Display Name', required=True, tracking=True)
    server_id = fields.Many2one('xibo.server', required=True, ondelete='cascade', tracking=True)
    xibo_display_id = fields.Integer(string='Xibo Display ID', readonly=True, copy=False)
    own_display_group_id = fields.Integer(
        string='Own Display Group ID', readonly=True, copy=False,
        help="Xibo creates a display-specific group per display, used as the XMR channel.",
    )
    license_code = fields.Char(string='License Code', readonly=True)
    logged_in = fields.Boolean(string='Online in Xibo', readonly=True)
    last_accessed = fields.Datetime(string='Last Accessed', readonly=True)
    client_type = fields.Char(string='Player Type', readonly=True)
    description = fields.Text()
    active = fields.Boolean(default=True, tracking=True)
    purpose = fields.Selection(
        [('reception', 'Reception / Welcome'),
         ('promo', 'Promotions'),
         ('info', 'Information / News'),
         ('mixed', 'Mixed Use')],
        default='mixed',
    )
    group_ids = fields.Many2many(
        'xibo.display.group', 'xibo_display_group_display_rel',
        'display_id', 'group_id', string='Groups',
    )
    company_id = fields.Many2one(related='server_id.company_id', store=True)

    _sql_constraints = [
        ('xibo_id_unique', 'unique(server_id, xibo_display_id)',
         'This Xibo display is already registered for this server.'),
    ]

    @api.model
    def _sync_from_server(self, server):
        payload = server._request('GET', '/api/display')
        if not isinstance(payload, list):
            return False
        existing = {d.xibo_display_id: d
                    for d in self.search([('server_id', '=', server.id)])}
        for entry in payload:
            xid = entry.get('displayId')
            if not xid:
                continue
            values = {
                'name': entry.get('display') or _('Unnamed display'),
                'server_id': server.id,
                'xibo_display_id': xid,
                'own_display_group_id': entry.get('displayGroupId') or 0,
                'license_code': entry.get('license'),
                'logged_in': bool(entry.get('loggedIn')),
                'client_type': entry.get('clientType'),
                'last_accessed': self._parse_xibo_dt(entry.get('lastAccessed')),
            }
            if xid in existing:
                existing[xid].write(values)
            else:
                self.create(values)
        _logger.info("Xibo: synced %s displays for %s", len(payload), server.name)
        return True

    @staticmethod
    def _parse_xibo_dt(value):
        if not value:
            return False
        try:
            return fields.Datetime.to_datetime(value)
        except Exception:
            return False

    def action_refresh(self):
        for srv in self.mapped('server_id'):
            self._sync_from_server(srv)
        return True

    def action_collect_now(self):
        for rec in self:
            if rec.own_display_group_id:
                rec.server_id._trigger_collect_now([rec.own_display_group_id])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Refresh sent"),
                'message': _("XMR collectNow dispatched to %s display(s).") % len(self),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_in_cms(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f"{self.server_id.url}/display/view",
            'target': 'new',
        }
