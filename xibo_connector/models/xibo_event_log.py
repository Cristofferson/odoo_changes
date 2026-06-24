# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import models, fields, api


class XiboEventLog(models.Model):
    _name = 'xibo.event.log'
    _description = 'Xibo API Event Log'
    _order = 'create_date desc'
    _rec_name = 'endpoint'

    server_id = fields.Many2one('xibo.server', string='Server', ondelete='cascade', index=True)
    method = fields.Char(string='HTTP Method')
    endpoint = fields.Char(string='Endpoint')
    status_code = fields.Integer(string='Status')
    success = fields.Boolean(string='Success')
    duration_ms = fields.Integer(string='Duration (ms)')
    request_summary = fields.Text(string='Request')
    response_summary = fields.Text(string='Response')
    error_message = fields.Text(string='Error')
    company_id = fields.Many2one(related='server_id.company_id', store=True)

    @api.model
    def _prune(self, days=30):
        """Drop entries older than ``days`` days."""
        cutoff = fields.Datetime.now() - timedelta(days=days)
        old = self.search([('create_date', '<', cutoff)])
        count = len(old)
        old.unlink()
        return count
