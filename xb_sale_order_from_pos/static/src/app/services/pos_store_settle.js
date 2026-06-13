/** @odoo-module **/
// XUBAX - Sales, Quotations & Layaway from POS (Phase 4)
// Close the SO balance to EXACTLY amount_unpaid when settling, absorbing the
// per-tax-group rounding cent of the down-payment credits. Clean-room, native-only.

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    /**
     * After the native Settle builds the cart, our SO's portion total can land ~1¢
     * off sale.order.amount_unpaid (the source of truth) due to per-tax-group IVA
     * rounding when the down-payment credits net against the products. Reconcile it:
     *
     *   delta = amount_unpaid - portion
     *   |delta| <= 0.02:
     *     Option 1: shift the last 0%-IVA down-payment CREDIT line by delta. The 16%
     *               group is NOT touched (IVA stays exact); only a 0% base moves.
     *     Option 2 (no 0% credit line): add a 0%-IVA "rounding" line for delta using
     *               config.xb_rounding_product_id (which must carry a valid SAT
     *               ClaveProdServ for the CFDI to stamp).
     * Only the POS cart is changed: the SO's is_downpayment lines, qty_invoiced and
     * any account.move are untouched.
     */
    async settleSO(sale_order, orderFiscalPos) {
        await super.settleSO(...arguments);
        if (!sale_order?.xb_so_kind) {
            return;
        }
        const order = this.getOrder();
        const ourLines = order
            .getOrderlines()
            .filter((l) => l.sale_order_origin_id?.id === sale_order.id);
        if (!ourLines.length) {
            return;
        }
        const portion = ourLines.reduce((s, l) => s + (l.priceIncl || 0), 0);
        const delta = this.currency.round(sale_order.amount_unpaid - portion);
        if (delta === 0 || Math.abs(delta) > 0.02) {
            return; // nothing to reconcile, or a real (non-rounding) mismatch -> guard handles it
        }

        const dpId = this.config.raw?.down_payment_product_id;
        const isZeroRate = (l) => (l.tax_ids || []).every((t) => t.amount === 0);

        // Option 1: absorb into the last 0%-rate down-payment credit line.
        const zeroCredit = ourLines
            .filter((l) => l.product_id.id === dpId && isZeroRate(l))
            .at(-1);
        if (zeroCredit) {
            // Credit qty is -1 and 0% IVA, so priceIncl = -price_unit. Lowering the
            // unit price by delta raises priceIncl (and the order total) by delta.
            zeroCredit.setUnitPrice(zeroCredit.price_unit - delta);
            return;
        }

        // Option 2 (fallback) is OPT-IN: only when the merchant configured a
        // rounding product (0% IVA + valid SAT ClaveProdServ). If none, silently
        // tolerate the rounding cent — the guard's 0.01 tolerance lets the settle
        // pass and the SO stays ~1c open by the merchant's choice (no extra line).
        let roundingProduct = this.config.xb_rounding_product_id;
        if (!roundingProduct && this.config.raw?.xb_rounding_product_id) {
            await this.data.read("product.product", [this.config.raw.xb_rounding_product_id]);
            roundingProduct = this.config.xb_rounding_product_id;
        }
        if (!roundingProduct) {
            return;
        }
        await this.addLineToCurrentOrder(
            {
                product_id: roundingProduct,
                product_tmpl_id: roundingProduct.product_tmpl_id,
                qty: 1,
                price_unit: delta,
                price_type: "automatic",
                sale_order_origin_id: sale_order,
            },
            {},
            false
        );
    },
});
