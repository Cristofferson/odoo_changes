# -*- coding: utf-8 -*-
# XUBAX - Sales, Quotations & Layaway from POS
# Original, clean-room implementation. ALL ERP logic (taxes, fiscal position,
# down payment / advance) is based exclusively on native Odoo
# (point_of_sale, pos_sale, sale) plus original design.
from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, plaintext2html


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Marks (and classifies) a Sale Order created from the POS by this module.
    # Set by xb_create_order_from_pos. Drives: (a) suppressing the delivery on
    # confirmation, and (b) the mandatory layaway advance enforcement at the POS.
    xb_so_kind = fields.Selection(
        selection=[
            ("quotation", "Quotation"),
            ("order", "Order"),
            ("layaway", "Layaway"),
            ("order_layaway", "Order / Layaway"),
        ],
        string="POS document kind",
        copy=False,
        index=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        # Expose to the POS frontend (recovery/down-payment flow + receipt):
        #  - xb_so_kind: layaway advance enforcement + receipt type header.
        #  - state: the receipt title is by STATE, not the frozen kind (a confirmed
        #    quotation prints PEDIDO). pos_sale already loads 'state', kept explicit.
        #  - access_token: build the SO portal URL (payment QR) for recovered SOs,
        #    where xbCreateOrderFromPos's stashed portal_url is absent (Phase 3 receipt).
        return super()._load_pos_data_fields(config) + ["xb_so_kind", "state", "access_token"]

    def action_confirm(self):
        # Phase 4: never create a delivery when confirming OUR POS-originated orders
        # (decision: all of them). pos_sale confirms the SO when the advance/payment
        # is collected; we inject the native `skip_procurement` context for our SOs
        # so action_confirm sets state to 'sale' without launching the stock rule
        # (sale_stock.sale.order.line._action_launch_stock_rule short-circuits on it).
        ours = self.filtered(
            lambda o: o.xb_so_kind and not self.env.context.get("skip_procurement")
        )
        if ours:
            super(SaleOrder, ours.with_context(skip_procurement=True)).action_confirm()
        rest = self - ours
        return super(SaleOrder, rest).action_confirm() if rest else True

    @api.depends('transaction_ids.state', 'transaction_ids.amount', 'order_line', 'amount_total',
                 'order_line.invoice_lines.parent_state', 'order_line.invoice_lines.price_total',
                 'order_line.pos_order_line_ids')
    def _compute_amount_unpaid(self):
        for sale_order in self:
            invoices = sale_order.order_line.invoice_lines.move_id.filtered(lambda invoice: invoice.state in ('draft', 'posted'))
            total_invoices_paid = sum(invoices.mapped('amount_total'))
            # XB FIX: el nativo suma el amount_total ENTERO de cada pos.order ligado, contando
            # productos sueltos vendidos en el mismo ticket como anticipo del SO. Sumamos solo el
            # subtotal de las LÍNEAS ligadas (igual que _compute_amount_to_invoice / _compute_amount_invoiced).
            # Las líneas de reembolso (qty < 0) deben RESTAR su magnitud: lo normal es que ya traigan
            # subtotal negativo, pero una línea de reembolso mal formada puede guardar el subtotal en
            # positivo (el signo queda solo en qty) -> forzamos la contribución negativa por magnitud
            # para que neutralice bien el anticipo. Solo usa campos nativos de point_of_sale/pos_sale.
            total_pos_orders_paid = sum(
                -abs(pos_line.price_subtotal_incl) if pos_line.qty < 0 else pos_line.price_subtotal_incl
                for pos_line in sale_order.order_line.pos_order_line_ids
            )
            sale_order.amount_unpaid = max(sale_order.amount_total - total_invoices_paid - total_pos_orders_paid - sale_order.amount_paid, 0.0)

    @api.model
    def xb_create_order_from_pos(self, payload):
        """Create a Quotation / Sale Order / Layaway from the POS.

        Coexists with the native ``pos_sale`` loader; it does NOT replace it.

        Expected ``payload`` keys (sent by the POS frontend in Phase 2):
            pos_config_id (int)         Point of Sale that originates the order.
            partner_id (int)            Customer.
            pricelist_id (int|False)    Pricelist used in the POS session.
            fiscal_position_id (int|False)
                                        Fiscal position already applied in POS.
            confirm (bool)              True  -> confirm the SO (Order/Layaway),
                                        False -> leave as draft Quotation.
            with_down_payment (bool)    The cashier intends to collect an advance
                                        (Layaway / optional advance). Used only to
                                        validate the down-payment product up front.
            lines (list[dict])          Cart lines, each:
                product_id (int), qty (float), price_unit (float, tax-EXCLUDED),
                discount (float, %), tax_ids (list[int], already POS-mapped),
                name (str, optional).
            amount_total (float)        Cart grand total (tax INCLUDED), used to
                                        validate parity to the cent.
            note (str, optional)        POS general customer note (plain text);
                                        written to sale.order.note when non-empty.
            internal_note (str, opt.)   POS internal note, already flattened to
                                        clean text on the client (getStrNotes);
                                        written to sale.order.internal_note when
                                        non-empty and the field exists.
            type (str, optional)        Chosen kind: "quotation" / "order" /
                                        "layaway" / "order_layaway". Used only for
                                        the chatter origin log label.

        Returns a dict with the created order id/name/amounts and the configured
        down-payment product, so the frontend can register the advance reusing the
        native ``pos_sale`` down-payment flow (Opción A).
        """
        config = self.env["pos.config"].browse(payload.get("pos_config_id")).exists()
        if not config:
            raise UserError(_("The Point of Sale configuration was not found."))

        # Server-side guard: the feature must be enabled for this POS. The button
        # is already hidden when the toggle is off, but we never trust the client.
        if not config.xb_enable_sale_order:
            raise UserError(_(
                "Creating quotations / orders / layaways is disabled for this "
                "Point of Sale."
            ))

        partner_id = payload.get("partner_id")
        if not partner_id:
            raise UserError(_("Select a customer before creating the order."))

        raw_lines = payload.get("lines") or []
        if not raw_lines:
            raise UserError(_("Add at least one product before creating the order."))

        # --- Anticipo (Opción A): reuse the native pos_sale down-payment product.
        # We do NOT collect the advance here: the POS order does, through the
        # native down-payment product (pos.config.down_payment_product_id), which
        # natively links the advance to this SO when the pos.order is paid.
        # Here we only verify it is configured and, if not, surface a clear
        # message to the cashier instead of failing later (adjustment for A).
        down_payment_product = config.down_payment_product_id
        if payload.get("with_down_payment") and not down_payment_product:
            raise UserError(_(
                "To register a layaway advance you must configure the "
                "down-payment product first:\n"
                "Point of Sale ▸ Settings ▸ this POS ▸ Down Payment Product."
            ))

        order_env = self.with_company(config.company_id).sudo()

        # --- Fiscalidad: force the EXACT POS taxes on every line for 1:1 parity.
        # The taxes in line['tax_ids'] are ALREADY mapped by the POS fiscal
        # position, so we set them explicitly and let the explicit value win over
        # the computed default. Passing them inside the same create() call is what
        # prevents the fiscal position from being applied a SECOND time on
        # already-mapped lines (adjustment "a").
        line_cmds = []
        for raw in raw_lines:
            vals = {
                "product_id": raw["product_id"],
                "product_uom_qty": raw.get("qty", 0.0),
                "price_unit": raw.get("price_unit", 0.0),
                "discount": raw.get("discount", 0.0),
                "tax_ids": [Command.set(raw.get("tax_ids") or [])],
            }
            if raw.get("name"):
                vals["name"] = raw["name"]
            # Per-line POS notes -> dedicated Text fields, each only when non-empty.
            # The POS currently sends only internal_note; the per-line customer note
            # is not captured (it is auto-filled with product/bin metadata in this
            # deployment), but we read both keys so the field is ready if it is
            # enabled later.
            line_customer_note = (raw.get("customer_note") or "").strip()
            if line_customer_note:
                vals["xb_customer_note"] = line_customer_note
            line_internal_note = (raw.get("internal_note") or "").strip()
            if line_internal_note:
                vals["xb_internal_note"] = line_internal_note
            line_cmds.append(Command.create(vals))

        order_vals = {
            "partner_id": partner_id,
            "order_line": line_cmds,
        }
        if payload.get("pricelist_id"):
            order_vals["pricelist_id"] = payload["pricelist_id"]
        # Kept on the header for traceability / downstream invoicing. Because the
        # line taxes above are explicit, setting it in the SAME create() does not
        # remap them now (it would only remap on a later recompute).
        if payload.get("fiscal_position_id"):
            order_vals["fiscal_position_id"] = payload["fiscal_position_id"]
        # Customer reference: carry the partner code (partner.ref, e.g. "A006461")
        # into the SO "Customer Reference" so it prints on the receipt and is visible
        # in the backend. Only when the partner actually has a ref.
        partner = self.env["res.partner"].browse(partner_id)
        if partner.ref:
            order_vals["client_order_ref"] = partner.ref
        # Phase 4: classify/mark this SO so we can suppress its delivery on confirm
        # and enforce the layaway advance at the POS.
        if payload.get("type"):
            order_vals["xb_so_kind"] = payload["type"]
        # Map the POS order notes to their SO fields. Both sale.order.note and
        # sale.order.internal_note are Html fields here (internal_note comes from
        # sale_subscription), so plaintext2html keeps line breaks and escapes the
        # text. Each is set only when non-empty, so an empty note never overwrites
        # anything. internal_note is guarded by a field-existence check so the
        # module stays installable where sale_subscription is absent.
        note = (payload.get("note") or "").strip()
        if note:
            order_vals["note"] = plaintext2html(note)
        internal_note = (payload.get("internal_note") or "").strip()
        if internal_note and "internal_note" in self._fields:
            order_vals["internal_note"] = plaintext2html(internal_note)

        order = order_env.create(order_vals)

        # Defensive reconciliation: guarantee the stored line taxes are exactly
        # the POS ones, even if a compute tried to remap them. Writing an explicit
        # value here sticks (no dependency changes afterwards to trigger a remap).
        for line, raw in zip(order.order_line, raw_lines):
            wanted = set(raw.get("tax_ids") or [])
            if set(line.tax_ids.ids) != wanted:
                line.tax_ids = [Command.set(list(wanted))]

        # --- Fiscalidad (adjustment "b"): validate price with/without VAT by
        # comparing the grand total against the POS cart total, to the cent.
        # We validate on the DRAFT order and confirm only if it matches (no
        # confirm-then-revert). The UserError aborts the transaction (rolling back
        # the draft order) and acts as a guardrail for now.
        cart_total = payload.get("amount_total")
        if cart_total is not None:
            rounding = order.currency_id.rounding
            if float_compare(order.amount_total, cart_total, precision_rounding=rounding) != 0:
                raise UserError(_(
                    "The order total (%(so)s) does not match the POS cart total "
                    "(%(cart)s). Check whether prices are tax-included or "
                    "tax-excluded for this Point of Sale.",
                    so=order.amount_total, cart=cart_total,
                ))

        # All three types (Quotation / Order / Layaway) are created as a 'sent'
        # quotation. We do NOT confirm here: action_confirm() triggers premature
        # delivery ("Entrega 1"). Confirmation is deferred to the payment / advance
        # collection in Phase 4. action_quotation_sent only flips draft -> sent, so
        # the order is portal-visible and payable online right away.
        #
        # payload["confirm"] is intentionally NOT consumed at creation anymore; it is
        # kept as the Phase 4 hook (Order/Layaway will confirm when the advance/
        # payment is collected).
        order.action_quotation_sent()

        # Chatter origin legend: log an internal note (log note, mt_note) recording
        # that this SO was created from the POS, with the chosen kind, the POS name
        # and the cashier (self.env.user, since this orm.call runs as the cashier).
        type_labels = {
            "quotation": _("Quotation"),
            "order": _("Order"),
            "layaway": _("Layaway"),
            "order_layaway": _("Order / Layaway"),
        }
        type_label = type_labels.get(payload.get("type")) or _("Order")
        body = Markup(
            "<p>🧾 <b>%(title)s</b></p>"
            "<ul>"
            "<li><b>%(type_lbl)s</b> %(type_val)s</li>"
            "<li><b>%(pos_lbl)s</b> %(pos_val)s</li>"
            "<li><b>%(cashier_lbl)s</b> %(cashier_val)s</li>"
            "</ul>"
        ) % {
            "title": _("Created from the Point of Sale"),
            "type_lbl": _("Type:"),
            "type_val": type_label,
            "pos_lbl": _("Point of Sale:"),
            "pos_val": config.name,
            "cashier_lbl": _("Cashier:"),
            "cashier_val": self.env.user.name,
        }
        order.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note")

        # Portal: build the ABSOLUTE URL so the POS receipt can show the online link
        # + QR (review / pay / settle online). get_portal_url() ensures the access
        # token itself (it calls _portal_ensure_token internally), which also sets it
        # on the SO — the receipt's fallback path loads that token to build the QR.
        portal_url = order.get_base_url() + order.get_portal_url()

        return {
            "sale_order_id": order.id,
            "name": order.name,
            "state": order.state,
            "amount_untaxed": order.amount_untaxed,
            "amount_tax": order.amount_tax,
            "amount_total": order.amount_total,
            "amount_unpaid": order.amount_unpaid,
            "portal_url": portal_url,
            "partner_ref": partner.ref or "",
            "down_payment_product_id": down_payment_product.id or False,
        }
