# -*- coding: utf-8 -*-
# XUBAX - Sales, Quotations & Layaway from POS
# Original, clean-room implementation. Native-only logic.
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def sync_from_ui(self, *args, **kwargs):
        # Round-trip (Bug A/B + receipt title): inject the FRESH linked Sale Orders
        # (amount_unpaid + state, recomputed by super() as the down payment / settle was
        # applied) into the sync response. The frontend (pos_store.syncAllOrders ->
        # data.missingRecursive -> models.loadConnectedData) updates the EXISTING SO
        # models by id, so the receipt reads the post-payment amount_unpaid DIRECTLY on
        # the initial print, not only after a reload — which lets the getter use
        # so.amount_unpaid as-is (no `amount_unpaid - priceIncl` projection, which
        # over-counted loose products and double-subtracted on reprint). Scoped to orders
        # that link a SO -> normal POS sales inject nothing. Keeps the native signature/
        # decorator and forwards *args/**kwargs verbatim. Best-effort: never break sync.
        data = super().sync_from_ui(*args, **kwargs)
        try:
            synced = self.browse([r["id"] for r in (data.get("pos.order") or []) if r.get("id")])
            linked_sos = synced.lines.sale_order_origin_id
            if linked_sos:
                so_fields = linked_sos._load_pos_data_fields(synced.config_id[:1].id)
                data.setdefault("sale.order", [])
                seen = {r.get("id") for r in data["sale.order"]}
                data["sale.order"].extend(
                    rec for rec in linked_sos.read(so_fields, load=False) if rec["id"] not in seen
                )
        except Exception as ex:  # noqa: BLE001
            _logger.warning("xb sale.order round-trip error: %s", ex)
        return data

    def _xb_has_our_so(self):
        """True if any of these orders is linked to one of our SOs (xb_so_kind set)."""
        return any(
            line.sale_order_origin_id.xb_so_kind
            for line in self.lines
            if line.sale_order_origin_id
        )

    def _xb_is_mx(self):
        """True when the order's company files taxes in Mexico, i.e. the Mexican
        localization is actually in effect. Keyed on the FISCAL country
        (account_fiscal_country_id) exactly like l10n_mx_edi resolves a move's
        country_code -- NOT on res.company.country_id, which can be MX while the
        company still runs a generic chart. Every CFDI/SAT touchpoint below is gated
        on this, so on a non-Mexican company they stay dormant and the invoice keeps
        pure native behaviour. l10n_mx_edi is a hard dependency but inert here."""
        company = self.company_id
        return (company.account_fiscal_country_id.code or company.country_id.code) == "MX"

    def _create_invoice(self, move_vals):
        # Exact CFDI for our flow (continuation of the invoice_cash_rounding_id drop
        # in _prepare_invoice_vals). When the order was paid in CASH and config cash
        # rounding is on, the native _create_invoice adds a rounding line to make the
        # invoice equal the cash TENDERED (which differs from the exact amount by the
        # change rounding). That line references invoice_cash_rounding_id -> now empty
        # -> account_id null -> CheckViolation. We keep the CFDI at the exact amount;
        # the cash-tendering difference is a POS cash matter, not a fiscal one. Mask
        # config.cash_rounding only for the native creation (no commit happens here,
        # so the masked value never persists). Ordinary POS invoices are untouched.
        # MX-only: dropping the rounding from the CFDI is a Mexican fiscal requirement;
        # outside Mexico (_xb_is_mx() False) we never mask, so the invoice keeps the
        # native cash-rounding behaviour.
        if not (self._xb_has_our_so() and self.config_id.cash_rounding and self._xb_is_mx()):
            return super()._create_invoice(move_vals)
        config = self.config_id
        keep = config.cash_rounding
        config.cash_rounding = False
        try:
            return super()._create_invoice(move_vals)
        finally:
            config.cash_rounding = keep

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        # Branch fix: attribute the POS invoice to the ORDER's company (e.g. the
        # Anello branch), not the shared invoice journal's company (the principal).
        # The native vals omit company_id, so account.move._compute_company_id
        # defaults it to journal.company_id._accessible_branches()[:1] -> the root
        # company. The branch then loses its identity: the move (and its CFDI/RFC)
        # is issued under the principal, and the branch income account does not
        # resolve ("Falta la cuenta requerida"). Set it explicitly so the move keeps
        # the order's company (the journal's company is a parent, so it is kept).
        vals["company_id"] = self.company_id.id
        # Exact CFDI for our flow: drop the POS cash rounding from the invoice.
        # Cash rounding (e.g. "10 Centavos", add_invoice_line) exists to give change
        # on cash payments; it must NOT alter the fiscal document, which has to mirror
        # the exact amount. Left in, account.move's cash-rounding recomputation adds a
        # +-rounding line to the move total, distorting the CFDI and stacking on top of
        # our 1-cent settle reconciliation (Option 1/2). Scoped to our orders only;
        # ordinary POS invoices keep the native behaviour.
        #
        # Mexican CFDI touchpoints below are DORMANT outside Mexico: l10n_mx_edi is a
        # hard dependency but inert unless the company files taxes in MX. On a non-MX
        # company this whole block is skipped -> the invoice keeps native cash rounding
        # and no SAT forma de pago is written (the field stays empty, no error).
        if self._xb_has_our_so() and self._xb_is_mx():
            vals["invoice_cash_rounding_id"] = False
            # FormaPago: report on the CFDI how the order was actually paid, mapped
            # from the dominant POS payment method (cash 01, transfer 03, credit 04,
            # debit 28...). Without l10n_mx_edi_pos the move would otherwise fall back
            # to the journal/partner default. Skipped when none of the methods carry
            # a SAT mapping or the partner already pins its own forma de pago.
            payments = self.payment_ids.filtered(
                lambda p: p.payment_method_id.l10n_mx_edi_payment_method_id
            )
            if payments and not self.partner_id.l10n_mx_edi_payment_method_id:
                dominant = max(payments, key=lambda p: abs(p.amount))
                vals["l10n_mx_edi_payment_method_id"] = (
                    dominant.payment_method_id.l10n_mx_edi_payment_method_id.id
                )
        return vals
