# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    xibo_recommendation_tags = fields.Char(
        string='Xibo Recommendation Tags',
        help="Comma-separated tags. When a product of this category is added to the POS cart, "
             "Xibo media files matching ANY of these tags are shown on the configured screens. "
             "Example: tv,electronics,accessories. "
             "Individual products can override this in their own Sales tab.",
    )
