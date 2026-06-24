# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    xibo_recommendation_tags = fields.Char(
        string='Xibo Recommendation Tags',
        help="Override the category-level tags for this specific product. "
             "Leave empty to inherit from the product category.",
    )

    def _xibo_effective_tags(self):
        """Resolve effective Xibo tags for this product: product override first,
        fallback to category. Returns a list of stripped lowercase tags.
        """
        self.ensure_one()
        raw = self.xibo_recommendation_tags or (self.categ_id.xibo_recommendation_tags if self.categ_id else '') or ''
        return [t.strip().lower() for t in raw.split(',') if t.strip()]


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _xibo_effective_tags(self):
        self.ensure_one()
        return self.product_tmpl_id._xibo_effective_tags()
