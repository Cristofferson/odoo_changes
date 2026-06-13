# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Related fields bound to the currently selected Point of Sale (pos_config_id).
    # This is the standard Odoo pattern for surfacing pos.config options in the
    # Settings > Point of Sale screen.
    pos_xb_enable_sale_order = fields.Boolean(
        related="pos_config_id.xb_enable_sale_order", readonly=False
    )
    pos_xb_allow_quotation = fields.Boolean(
        related="pos_config_id.xb_allow_quotation", readonly=False
    )
    pos_xb_differentiate_order_layaway = fields.Boolean(
        related="pos_config_id.xb_differentiate_order_layaway", readonly=False
    )
    pos_xb_default_so_state = fields.Selection(
        related="pos_config_id.xb_default_so_state", readonly=False
    )
    pos_xb_show_order_balance = fields.Boolean(
        related="pos_config_id.xb_show_order_balance", readonly=False
    )
    pos_xb_enrich_receipt = fields.Boolean(
        related="pos_config_id.xb_enrich_receipt", readonly=False
    )
    pos_xb_show_partner_ref = fields.Boolean(
        related="pos_config_id.xb_show_partner_ref", readonly=False
    )
    pos_xb_autoprint_on_create = fields.Boolean(
        related="pos_config_id.xb_autoprint_on_create", readonly=False
    )
    pos_xb_show_portal_link = fields.Boolean(
        related="pos_config_id.xb_show_portal_link", readonly=False
    )
    pos_xb_autofactura_qr_paid_only = fields.Boolean(
        related="pos_config_id.xb_autofactura_qr_paid_only", readonly=False
    )
    pos_xb_rounding_product_id = fields.Many2one(
        related="pos_config_id.xb_rounding_product_id", readonly=False
    )
