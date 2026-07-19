from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    xb_es_intencion = fields.Boolean(
        string='Es intención de misa',
        help='Al venderlo en el POS se pedirá la misa, el tipo de intención '
             'y los nombres; al cobrar se crea la intención pagada.')

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ['xb_es_intencion']
