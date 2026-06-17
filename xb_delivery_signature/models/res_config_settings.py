# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Related fields bound to the current company. Standard Odoo pattern for
    # surfacing res.company options in the Settings screen (mirrors how the
    # native portal-confirmation flags are exposed).
    xb_delivery_signature_required = fields.Boolean(
        related="company_id.xb_delivery_signature_required", readonly=False
    )
    xb_delivery_signature_mandatory = fields.Boolean(
        related="company_id.xb_delivery_signature_mandatory", readonly=False
    )
    xb_delivery_signature_portal = fields.Boolean(
        related="company_id.xb_delivery_signature_portal", readonly=False
    )
    xb_delivery_signature_mirror_so = fields.Boolean(
        related="company_id.xb_delivery_signature_mirror_so", readonly=False
    )
    xb_delivery_signature_on_slip = fields.Boolean(
        related="company_id.xb_delivery_signature_on_slip", readonly=False
    )
