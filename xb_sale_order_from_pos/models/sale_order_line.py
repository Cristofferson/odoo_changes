# -*- coding: utf-8 -*-
# XUBAX - Sales, Quotations & Layaway from POS
# Original, clean-room implementation.
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Per-line notes carried over from the POS cart line. Kept as separate Text
    # fields (not the native sale.order.line.name/description) so they do not
    # disturb the printed line description and can be shown only in the expanded
    # line form. Populated by sale.order.xb_create_order_from_pos, each only when
    # the POS line actually carries that note.
    xb_customer_note = fields.Text(
        string="POS Customer Note",
        help="Customer note typed on the originating POS cart line "
        "(pos.order.line.customer_note).",
    )
    xb_internal_note = fields.Text(
        string="POS Internal Note",
        help="Internal note typed on the originating POS cart line "
        "(pos.order.line.note), flattened to clean text on the client.",
    )
