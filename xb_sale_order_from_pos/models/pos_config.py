# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    xb_rounding_product_id = fields.Many2one(
        "product.product",
        string="Settle rounding product",
        help="Fallback used when settling a sale order whose down payments cannot "
             "absorb the per-tax rounding cent in a 0% line (e.g. an all-16% order). "
             "Should be a 0% IVA service product with a valid SAT ClaveProdServ so "
             "the CFDI stamps.",
    )

    def _get_special_products(self):
        # Register our settle rounding product as a POS special product so its
        # product.template is force-loaded to the frontend even when the merchant
        # keeps it available_in_pos=False (it is added programmatically for the
        # Option 2 settle, never sold from the product list). Without it, restoring a
        # saved order holding a rounding line would leave product_tmpl_id (hence
        # uom_id) unresolved and crash the POS on reload. Mirrors pos_sale's
        # down_payment_product pattern, referencing the field directly: the force-load
        # that matters (product.template._load_pos_data) calls this on a single config,
        # so self.xb_rounding_product_id resolves there.
        products = super()._get_special_products()
        if self.xb_rounding_product_id:
            products |= self.xb_rounding_product_id
        return products

    # --- Main toggle: enables the whole feature set for this POS ---
    xb_enable_sale_order = fields.Boolean(
        string="Create Sale Order / Quotation",
        help="Allow creating quotations, sale orders and layaways (apartados) "
             "from this Point of Sale.",
    )

    # --- Sub-toggles (only relevant when the main toggle is on) ---
    # NOTE on POS loading: pos.config does not restrict its loaded fields
    # (pos.load.mixin._load_pos_data_fields returns [] and read([]) reads ALL
    # fields). So every xb_* field below — and the native pos_sale
    # down_payment_product_id — is automatically available in the POS frontend as
    # config.<field>. No _load_pos_data_fields override is needed here.
    xb_allow_quotation = fields.Boolean(
        string="Allow quotations",
        help="Let the cashier create the order as a draft quotation that the "
             "customer can complete online or recover in-store.",
    )
    xb_differentiate_order_layaway = fields.Boolean(
        string="Differentiate Order and Layaway",
        help="OFF (default): the POS shows a single \"Order / Layaway\" action "
             "— a confirmed sale order with an optional advance (down payment).\n"
             "ON: the POS shows two separate actions — \"Order\" (confirmed, no "
             "advance) and \"Layaway\" (confirmed, with advance).\n"
             "\"Quotation\" is offered separately according to \"Allow "
             "quotations\".",
    )
    xb_default_so_state = fields.Selection(
        selection=[
            ("draft", "Quotation"),
            ("sale", "Confirmed order"),
        ],
        string="Default state",
        default="draft",
        help="Pre-selects which document type is highlighted by default in the POS "
             "create dialog: a draft Quotation, or a Sale Order / Layaway. It only "
             "sets the default choice — nothing is confirmed on creation (the order "
             "is confirmed natively when its payment is collected).",
    )
    xb_show_order_balance = fields.Boolean(
        string="Show total & pending balance",
        help="Display the order total and pending balance next to the order "
             "reference in the POS order panel.",
    )
    xb_enrich_receipt = fields.Boolean(
        string="Detailed order receipt",
        help="Add the order's product detail, total and pending balance to the "
             "printed receipt.",
    )
    xb_show_partner_ref = fields.Boolean(
        string="Show customer reference",
        help="Show the customer's reference code before their name.",
    )
    xb_autoprint_on_create = fields.Boolean(
        string="Auto-print receipt on create",
        help="Automatically print the order receipt right after creating the "
             "quotation / sale order / layaway from the POS.",
    )
    xb_show_portal_link = fields.Boolean(
        string="Show online portal link on receipt",
        help="Add the order's online portal link (with access token) and a short "
             "instruction to the receipt, so the customer can review, add advances "
             "or settle the order online. Requires Online Payment and payment "
             "providers to be configured.",
    )
    xb_autofactura_qr_paid_only = fields.Boolean(
        string="Self-invoice QR only when settled",
        default=True,
        help="Controls the native self-invoice (\"Need an invoice?\") QR on receipts "
             "linked to a Sale Order.\n"
             "Enabled (default): the self-invoice QR appears only when the balance is "
             "0 (settlement / fully-paid ticket), avoiding a double QR alongside the "
             "online payment QR on advance tickets.\n"
             "Disabled: the self-invoice QR appears on every ticket where it applies "
             "(native behaviour), for merchants that invoice each ticket. The online "
             "payment QR is independent (balance > 0 + 'Show online portal link').",
    )
