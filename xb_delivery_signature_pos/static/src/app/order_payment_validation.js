/** @odoo-module */
// XUBAX - Delivery Receipt Signature - POS Bridge
// After the order is validated and synced, optionally pop the signature pad.
import { patch } from "@web/core/utils/patch";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation() {
        // Capture BEFORE super so the signature is stashed on the order in time
        // for the auto-print + receipt screen. The order is already synced here
        // (afterOrderValidation runs after syncAllOrders), so it carries a
        // server id we can write to.
        if (this.pos.config.xb_capture_delivery_signature) {
            await this.pos.xbCaptureDeliverySignature(this.order);
        }
        return super.afterOrderValidation(...arguments);
    },
});
