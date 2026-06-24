# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class XiboDataset(models.Model):
    _name = 'xibo.dataset'
    _description = 'Xibo DataSet'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    server_id = fields.Many2one('xibo.server', required=True, ondelete='cascade', tracking=True)
    xibo_dataset_id = fields.Integer(string='Xibo DataSet ID', readonly=True, copy=False)
    code = fields.Char(string='Code',
                       help="Optional short code used by add-on modules to find this dataset.")
    description = fields.Text()
    active = fields.Boolean(default=True)
    column_ids = fields.One2many('xibo.dataset.column', 'dataset_id', string='Columns')
    row_count = fields.Integer(compute='_compute_row_count')
    company_id = fields.Many2one(related='server_id.company_id', store=True)

    _sql_constraints = [
        ('xibo_id_unique', 'unique(server_id, xibo_dataset_id)',
         'This DataSet is already registered for this server.'),
    ]

    @api.depends()
    def _compute_row_count(self):
        for rec in self:
            rec.row_count = self.env['xibo.dataset.row'].search_count([('dataset_id', '=', rec.id)])

    @api.model
    def _sync_from_server(self, server):
        payload = server._request('GET', '/api/dataset')
        if not isinstance(payload, list):
            return False
        existing = {ds.xibo_dataset_id: ds for ds in self.search([('server_id', '=', server.id)])}
        for entry in payload:
            xid = entry.get('dataSetId')
            if not xid:
                continue
            values = {
                'name': entry.get('dataSet') or _('Unnamed dataset'),
                'server_id': server.id,
                'xibo_dataset_id': xid,
                'description': entry.get('description'),
            }
            ds = existing.get(xid)
            if ds:
                ds.write(values)
            else:
                ds = self.create(values)
            self.env['xibo.dataset.column']._sync_columns(ds)
        _logger.info("Xibo: synced %s datasets for %s", len(payload), server.name)
        return True

    def action_sync_columns(self):
        for rec in self:
            self.env['xibo.dataset.column']._sync_columns(rec)
        return True

    def push_row(self, values_by_column_code, trigger_collect_now_for=None):
        """Append a row to this DataSet on Xibo."""
        self.ensure_one()
        if not self.xibo_dataset_id:
            raise UserError(_("DataSet '%s' has no Xibo ID. Sync first.") % self.name)
        columns = {c.code or c.heading: c for c in self.column_ids}
        if not columns:
            self.action_sync_columns()
            columns = {c.code or c.heading: c for c in self.column_ids}

        body = {}
        for code, value in values_by_column_code.items():
            col = columns.get(code)
            if not col:
                _logger.warning("DataSet '%s' has no column '%s' — skipping.", self.name, code)
                continue
            body[f"dataSetColumnId_{col.xibo_dataset_column_id}"] = value

        if not body:
            raise UserError(_("No matching columns to write into DataSet '%s'.") % self.name)

        resp = self.server_id._request(
            'POST', f'/api/dataset/data/{self.xibo_dataset_id}',
            data=body,
        )
        local_row = self.env['xibo.dataset.row'].create({
            'dataset_id': self.id,
            'xibo_row_id': resp.get('id') if isinstance(resp, dict) else False,
            'payload': str(values_by_column_code),
        })

        if trigger_collect_now_for:
            self.server_id._trigger_collect_now(trigger_collect_now_for)
        return local_row

    def purge_old_rows(self, keep_last_n=50):
        self.ensure_one()
        if not self.xibo_dataset_id:
            return False
        rows = self.server_id._request('GET', f'/api/dataset/data/{self.xibo_dataset_id}',
                                        raise_on_error=False)
        if not isinstance(rows, list):
            return False
        if len(rows) <= keep_last_n:
            return False
        to_delete = rows[:-keep_last_n]
        for row in to_delete:
            rid = row.get('id')
            if rid:
                self.server_id._request(
                    'DELETE', f'/api/dataset/data/{self.xibo_dataset_id}/{rid}',
                    raise_on_error=False,
                )
        return len(to_delete)

    def action_view_rows(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rows of %s') % self.name,
            'res_model': 'xibo.dataset.row',
            'view_mode': 'list',
            'domain': [('dataset_id', '=', self.id)],
        }

    def action_open_in_cms(self):
        self.ensure_one()
        if not self.xibo_dataset_id:
            return False
        return {
            'type': 'ir.actions.act_url',
            'url': f"{self.server_id.url}/dataset/view",
            'target': 'new',
        }
