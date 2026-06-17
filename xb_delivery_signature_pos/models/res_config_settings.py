# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_xb_capture_delivery_signature = fields.Boolean(
        related="pos_config_id.xb_capture_delivery_signature", readonly=False
    )
    pos_xb_delivery_signature_on_receipt = fields.Boolean(
        related="pos_config_id.xb_delivery_signature_on_receipt", readonly=False
    )
