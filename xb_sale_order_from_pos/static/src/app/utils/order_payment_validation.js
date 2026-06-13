/** @odoo-module **/
// XUBAX - Sales, Quotations & Layaway from POS (Phase 4)
// Payment-validation guards for our POS-originated sale orders. Clean-room,
// native-only: reuses the native down-payment / settle flow and only adds guards.

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    async askBeforeValidation() {
        // Guard 1 — a LAYAWAY must collect SOME advance to be confirmed: block when a
        // down-payment line links to a layaway SO but nothing is being collected
        // (priceIncl <= 0). Order = optional advance (0 allowed); Quotation = full.
        const layawayLine = this.order
            .getOrderlines()
            .find((l) => l.sale_order_origin_id?.xb_so_kind === "layaway");
        if (layawayLine && this.order.priceIncl <= 0) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Advance required"),
                body: _t("This layaway requires an advance."),
            });
            return false;
        }

        // Guard 2 — when SETTLING one of our SOs (the order carries its product
        // lines, not just an advance), the amount being collected for that SO must
        // equal its real balance (sale.order.amount_unpaid, the source of truth from
        // actual payments) to the cent. Defense for the multi-advance settle edge
        // cases (an advance still uninvoiced, a re-settle, ...). Scoped to each SO's
        // own portion = sum of its lines' priceIncl (credits are negative).
        const dpId = this.pos.config.raw?.down_payment_product_id;
        if (dpId) {
            const bySo = new Map();
            for (const l of this.order.getOrderlines()) {
                const so = l.sale_order_origin_id;
                if (!so?.xb_so_kind) {
                    continue;
                }
                (bySo.get(so) || bySo.set(so, []).get(so)).push(l);
            }
            for (const [so, lines] of bySo) {
                const isSettle = lines.some((l) => l.product_id.id !== dpId);
                if (!isSettle) {
                    continue; // pure (partial) down payment, not a settle
                }
                const portion = lines.reduce((s, l) => s + (l.priceIncl || 0), 0);
                if (Math.abs(portion - so.amount_unpaid) > 0.01) {
                    this.pos.dialog.add(AlertDialog, {
                        title: _t("Balance mismatch"),
                        body: _t(
                            "The amount to settle for %s (%s) does not match its balance (%s). Reload the order and try again.",
                            so.name,
                            this.pos.env.utils.formatCurrency(portion),
                            this.pos.env.utils.formatCurrency(so.amount_unpaid)
                        ),
                    });
                    return false;
                }
            }
        }

        return super.askBeforeValidation();
    },
});
