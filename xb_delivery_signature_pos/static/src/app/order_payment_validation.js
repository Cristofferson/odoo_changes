/** @odoo-module */
// XUBAX - Delivery Receipt Signature - POS Bridge
// After the order is validated and synced, optionally pop the signature pad.
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation() {
        const res = await super.afterOrderValidation(...arguments);
        if (this.pos.config.xb_capture_delivery_signature) {
            // The order is synced here, so it carries a server id we can write to.
            await this.pos.xbCaptureDeliverySignature(this.order);
        }
        return res;
    },
});
