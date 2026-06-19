from odoo import fields, models

# Registra el tamano fisico de la etiqueta Diamond Papers (3-1/8" x 2").
# Se hace de forma defensiva por si alguna version de stock usa este dict.
from odoo.addons.stock.wizard import product_label_layout as _stock_pll

_stock_pll.ZPL_FORMAT_SIZE.setdefault("diamond_papers", (3.125, 2.0))


class ProductLabelLayout(models.TransientModel):
    _inherit = "product.label.layout"

    # 'jewelry' (Joyeria) ya existe de forma nativa en stock.
    # Aqui solo agregamos la nueva opcion "Diamond Papers" al desplegable "Plantilla ZPL".
    zpl_template = fields.Selection(
        selection_add=[("diamond_papers", "Diamond Papers")],
        ondelete={"diamond_papers": "set default"},
    )
