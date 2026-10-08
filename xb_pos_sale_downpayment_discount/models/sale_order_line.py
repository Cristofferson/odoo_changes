# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    xb_pos_discount_line_id = fields.Many2one(
        "pos.order.line", string="Discount from POS line", index="btree_not_null",
        readonly=True, copy=False, ondelete="set null",
        help="The discounted down payment line of the POS ticket this discount comes from.",
    )
