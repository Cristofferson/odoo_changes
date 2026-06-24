# -*- coding: utf-8 -*-
from odoo import models, fields


class XiboDatasetRow(models.Model):
    _name = 'xibo.dataset.row'
    _description = 'Xibo DataSet Row (local trace)'
    _order = 'create_date desc'
    _rec_name = 'xibo_row_id'

    dataset_id = fields.Many2one('xibo.dataset', required=True, ondelete='cascade', index=True)
    server_id = fields.Many2one(related='dataset_id.server_id', store=True)
    xibo_row_id = fields.Integer(string='Xibo Row ID', readonly=True)
    payload = fields.Text(string='Values', readonly=True)
    company_id = fields.Many2one(related='dataset_id.company_id', store=True)
