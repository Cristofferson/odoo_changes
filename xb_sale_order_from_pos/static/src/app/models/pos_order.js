/** @odoo-module **/
// XUBAX - Sales, Quotations & Layaway from POS (Phase 3 - display only)
// Exposes the linked Sale Order totals to the receipt. Clean-room, native-only.

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    /**
     * Return { name, total, paid, balance, portalUrl } for the Sale Order this POS
     * order relates to, or null when there is none.
     * - Primary source: the uiState stash written by xbCreateOrderFromPos when the
     *   SO was created from this cart (carries the portal URL too).
     * - Fallback: the SO natively linked to a line via sale_order_origin_id, whose
     *   amount_total / amount_unpaid are loaded client-side by pos_sale. The portal
     *   URL is not loaded in this path, so portalUrl is null there.
     * paid = total - balance (balance is sale.order.amount_unpaid, clamped >= 0).
     */
    xbGetSaleOrderTotals() {
        const stash = this.uiState?.xbSaleOrder;
        let data = null;
        if (stash) {
            data = {
                name: stash.name,
                total: stash.amount_total,
                balance: stash.amount_unpaid,
                portalUrl: stash.portal_url || null,
                type: stash.type || null,
                state: stash.state || null,
                partnerRef: stash.partner_ref || null,
            };
        } else {
            const so = this.lines?.find((l) => l.sale_order_origin_id)
                ?.sale_order_origin_id;
            if (so) {
                // so.amount_unpaid is FRESH (post-payment): pos.order.sync_from_ui
                // injects the recomputed linked SO into the sync response, so the SO
                // model is updated before the receipt renders. Use it directly — no
                // projection. The old `amount_unpaid - priceIncl` over-subtracted loose
                // products sold in the same ticket (Bug A) and double-subtracted on
                // reprint once amount_unpaid was fresh (Bug B). The backend balance is
                // the source of truth.
                // Build the SO portal URL from its access_token (the stash's
                // portal_url is only present on creation). Use config._base_url, the
                // same base the native ticket QR uses, for the payment QR on
                // recovered SOs.
                const baseUrl = this.config?._base_url || "";
                const portalUrl = so.access_token
                    ? `${baseUrl}/my/orders/${so.id}?access_token=${so.access_token}`
                    : null;
                data = {
                    name: so.name,
                    total: so.amount_total,
                    balance: Math.max(so.amount_unpaid || 0, 0),
                    portalUrl,
                    type: so.xb_so_kind || null,
                    state: so.state || null,
                    partnerRef: null,
                };
            }
        }
        if (!data) {
            return null;
        }
        // Fallback for the customer reference: the loaded partner, if it carries one.
        if (!data.partnerRef) {
            data.partnerRef = this.getPartner()?.ref || null;
        }
        return { ...data, paid: data.total - data.balance };
    },
});
