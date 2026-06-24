# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class XiboDatasetColumn(models.Model):
    _name = 'xibo.dataset.column'
    _description = 'Xibo DataSet Column'
    _order = 'sequence, heading'

    dataset_id = fields.Many2one('xibo.dataset', required=True, ondelete='cascade')
    server_id = fields.Many2one(related='dataset_id.server_id', store=True)
    xibo_dataset_column_id = fields.Integer(string='Xibo Column ID', readonly=True)
    heading = fields.Char(string='Heading', required=True)
    code = fields.Char(string='Code',
                       help="Programmatic identifier. Defaults to the heading if empty.")
    data_type = fields.Selection(
        [('string', 'String'), ('number', 'Number'), ('date', 'Date'),
         ('external_image', 'External Image'), ('library_image', 'Library Image'), ('html', 'HTML')],
        default='string',
    )
    sequence = fields.Integer(default=10)
    list_content = fields.Char(string='List Values')

    _sql_constraints = [
        ('xibo_id_unique', 'unique(dataset_id, xibo_dataset_column_id)',
         'This column is already mapped.'),
    ]

    @api.model
    def _sync_columns(self, dataset):
        if not dataset.xibo_dataset_id:
            return False
        payload = dataset.server_id._request(
            'GET', f'/api/dataset/{dataset.xibo_dataset_id}/column',
            raise_on_error=False,
        )
        if not isinstance(payload, list):
            return False
        existing = {c.xibo_dataset_column_id: c for c in dataset.column_ids}
        type_map = {1: 'string', 2: 'number', 3: 'date', 4: 'external_image',
                    5: 'library_image', 6: 'html'}
        for entry in payload:
            xid = entry.get('dataSetColumnId')
            if not xid:
                continue
            values = {
                'dataset_id': dataset.id,
                'xibo_dataset_column_id': xid,
                'heading': entry.get('heading') or 'col',
                'data_type': type_map.get(entry.get('dataTypeId'), 'string'),
                'sequence': entry.get('columnOrder') or 10,
                'list_content': entry.get('listContent'),
            }
            if xid in existing:
                existing[xid].write(values)
            else:
                self.create(values)
        _logger.info("Xibo: synced %s columns for dataset %s", len(payload), dataset.name)
        return True
