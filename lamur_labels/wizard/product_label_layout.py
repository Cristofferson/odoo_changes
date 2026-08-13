from odoo import fields, models

# Tamaño físico de la etiqueta mariposa, en pulgadas (ancho x alto).
# 711 x 136 dots @ 203 dpi = 3.50" x 0.67" = 89 x 17 mm.
LAMUR_FORMAT_SIZE = (3.50, 0.67)


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    zpl_template = fields.Selection(
        selection_add=[('lamur', 'LAMUR (Mariposa 89 x 17 mm)')],
        ondelete={'lamur': 'set default'},
    )
