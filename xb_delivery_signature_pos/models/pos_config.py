# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    # Per-POS toggle. pos.config loads ALL its fields to the frontend (the
    # load mixin returns [] -> read([]) reads everything), so this is available
    # as config.xb_capture_delivery_signature in the POS without any loader
    # override.
    xb_capture_delivery_signature = fields.Boolean(
        string="Capture delivery signature at POS",
        help="Pop up a signature pad right after the order is validated so the "
             "customer signs the reception on the cashier's device.",
    )
    xb_delivery_signature_on_receipt = fields.Boolean(
        string="Print signature on the POS receipt",
        default=True,
        help="Show the captured signature on the POS receipt/ticket.",
    )
