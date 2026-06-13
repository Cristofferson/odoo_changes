/** @odoo-module **/
// XUBAX - Sales, Quotations & Layaway from POS (Phase 3 - display only)
// Adds the Sale Order totals + portal QR to the native OrderReceipt. Clean-room.

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

patch(OrderReceipt.prototype, {
    // Sale Order totals for this receipt's order, or null. Read by the template.
    get xbSaleOrder() {
        return this.order.xbGetSaleOrderTotals?.() || null;
    },
    // Big localized type header at the top of the receipt (null if no SO / type).
    // Title is by STATE, not the frozen kind: a quotation already confirmed (state
    // 'sale') prints PEDIDO; only a draft/sent quotation prints COTIZACIÓN. Order and
    // Layaway always print their own word. Strings -> COTIZACIÓN/PEDIDO/APARTADO via po.
    get xbTypeHeader() {
        const so = this.xbSaleOrder;
        if (!so?.type) {
            return null;
        }
        let key = so.type;
        if (key === "quotation") {
            key = so.state === "sale" ? "order" : "quotation";
        }
        const labels = {
            quotation: _t("QUOTATION"),
            order: _t("ORDER"),
            layaway: _t("LAYAWAY"),
            order_layaway: _t("ORDER / LAYAWAY"),
        };
        return labels[key] || null;
    },
    // (h) Component breakdown for the advance ticket: the recovered Sale Order's own
    // PRODUCT lines (name, qty, total) — NOT down_payment_details. Excludes the
    // down-payment section/lines (is_downpayment) and any non-product line (no
    // product_id). [{ product_uom_qty, product_name, total }] or null. The template
    // shows it only on the advance ticket (balance > 0); on a settle it is hidden.
    get xbSaleDetails() {
        const so = this.order.lines?.find((l) => l.sale_order_origin_id)
            ?.sale_order_origin_id;
        const lines = (so?.order_line || []).filter(
            (l) => !l.is_downpayment && l.product_id
        );
        return lines.length
            ? lines.map((l) => ({
                  product_uom_qty: l.product_uom_qty,
                  product_name: l.product_id.display_name || l.display_name || "",
                  total: this.formatCurrency(l.price_total),
              }))
            : null;
    },
    // (PRIORITY) Cash-rounding display that always balances. The native "Rounding" +
    // "To Pay" block hides whenever there is change (order.appliedRounding becomes 0 for
    // any overpayment beyond a rounding unit), so the ticket can't reconcile. Compute
    // the rounding from the TOTAL itself (independent of what was tendered) and show it
    // whenever cash rounding applies. Guarantees: Total + Rounding = To Pay; and since
    // the native change is asymmetric (collectible up, change down), Cash - To Pay =
    // Change. The native change line is untouched.
    get xbRoundedTotal() {
        const o = this.order;
        const rm =
            o.config?.cash_rounding && o.orderIsRounded ? o.config.rounding_method : null;
        return rm ? rm.asymmetricRound(o.priceIncl) : null;
    },
    get xbRoundingAmount() {
        const rt = this.xbRoundedTotal;
        return rt === null ? 0 : this.order.currency.round(rt - this.order.priceIncl);
    },
    get xbShowRounding() {
        return this.xbRoundedTotal !== null && this.xbRoundingAmount !== 0;
    },
    // (i) Footer RFC = the fiscal ENTITY's RFC the CFDI issues under: the company's
    // own, or for a branch without one, the parent's (res.company.xb_cfdi_emisor_rfc,
    // computed exactly like l10n_mx_edi's issuer). Falls back to the native behaviour.
    get vatText() {
        const rfc = this.order.company?.xb_cfdi_emisor_rfc;
        if (!rfc) {
            return super.vatText;
        }
        const vatLabel = this.order.company.country_id?.vat_label;
        return vatLabel
            ? _t("%(vatLabel)s: %(vatId)s", { vatLabel, vatId: rfc })
            : _t("Tax ID: %(vatId)s", { vatId: rfc });
    },
    // Self-invoice ("Need an invoice?") QR gating, configurable per POS via
    // xb_autofactura_qr_paid_only. When ON (default), hide the native self-invoice QR
    // while a Sale Order balance is still pending (advance ticket) — the payment QR is
    // shown there instead, avoiding a double QR; it still shows on settle/paid tickets
    // and on normal POS sales (no SO). When OFF, never hide (native behaviour).
    get xbHideAutofacturaQr() {
        if (!this.order.config?.xb_autofactura_qr_paid_only) {
            return false;
        }
        const so = this.xbSaleOrder;
        return Boolean(so && so.balance > 0);
    },
    // Reuse the native QR helper to render the SO online portal link as a QR.
    // Hardened: a QR-generation failure must NEVER crash the receipt render (which
    // would take down the whole POS during autoprint). On error, log and omit the QR.
    xbPortalQrCode(url) {
        if (!url) {
            return null;
        }
        try {
            return generateQRCodeDataUrl(url);
        } catch (e) {
            console.warn("[xb] payment QR generation failed:", e, url);
            return null;
        }
    },
});
