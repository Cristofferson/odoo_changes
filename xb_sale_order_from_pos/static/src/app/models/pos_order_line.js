/** @odoo-module **/
// XUBAX - Sales, Quotations & Layaway from POS (Phase 4)
// Fix the Settle of OUR sale orders (xb_so_kind) when they carry MULTIPLE partial
// advances. Clean-room, native-only.

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

patch(PosOrderline.prototype, {
    /**
     * On Settle, the native setQuantityFromSOL sets the cart qty of a down-payment
     * (service) line on a CONFIRMED SO from `qty_to_invoice`. The native multi
     * down-payment flow leaves that field inconsistent: only the latest advance
     * stays at -1; earlier advances become 0 -> they do NOT deduct -> the customer
     * is over-charged. (Confirmed native limitation, see pos_sale TODO.)
     *
     * For OUR sale orders, route the down-payment CREDIT lines through the qty
     * formula `product_uom_qty - max(qty_delivered, qty_invoiced)`, which yields -1
     * per real advance (product_uom_qty = 0, qty_invoiced = 1). So EVERY advance
     * deducts and the settle charge equals sale.order.amount_unpaid, for any number
     * of partial advances. We only change the POS cart quantity here: the SO's
     * is_downpayment lines, their qty_invoiced and any account.move are untouched.
     */
    async setQuantityFromSOL(saleOrderLine) {
        if (this.sale_order_origin_id?.xb_so_kind && saleOrderLine.is_downpayment) {
            this.setQuantity(
                saleOrderLine.product_uom_qty -
                    Math.max(saleOrderLine.qty_delivered, saleOrderLine.qty_invoiced)
            );
            return;
        }
        return super.setQuantityFromSOL(...arguments);
    },
});
