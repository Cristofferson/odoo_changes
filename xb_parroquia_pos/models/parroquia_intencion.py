from odoo import fields, models


class ParroquiaIntencion(models.Model):
    _inherit = 'parroquia.intencion'

    pos_order_line_id = fields.Many2one(
        'pos.order.line', string='Línea de venta POS', readonly=True,
        help='Línea del ticket con la que se cobró esta intención.')
