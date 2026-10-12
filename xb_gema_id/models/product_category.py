from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    xb_gema_id = fields.Boolean(
        "Assign gem ID",
        help="New products of this category tracked by serial number get the "
             "next gem ID and their folder in the cloud.",
    )
