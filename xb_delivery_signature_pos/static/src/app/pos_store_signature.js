/** @odoo-module */
// XUBAX - Delivery Receipt Signature - POS Bridge
// Heavy/async work lives on the PosStore (it outlives the validation component):
// open the signature popup and persist the result on the synced pos.order.
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { _t } from "@web/core/l10n/translation";
import { DeliverySignaturePopup } from "@xb_delivery_signature_pos/app/signature_popup/signature_popup";

patch(PosStore.prototype, {
    async xbCaptureDeliverySignature(order) {
        const partnerName = order.getPartnerName?.() || order.getPartner?.()?.name || "";
        const payload = await makeAwaitable(this.dialog, DeliverySignaturePopup, {
            title: _t("Delivery receipt signature"),
            defaultName: partnerName,
        });
        if (!payload || !payload.signature) {
            return; // customer skipped / closed
        }
        // Stash the full data URL on the order so the receipt template can render
        // it (the auto-print happens right after this, in super.afterOrderValidation).
        order.uiState.xbDeliverySignature = {
            image: "data:image/png;base64," + payload.signature,
            name: payload.name || partnerName || "",
        };
        // After sync the local record carries the real database id.
        const orderId = typeof order.id === "number" && order.id > 0 ? order.id : false;
        if (!orderId) {
            return;
        }
        try {
            await this.env.services.orm.call(
                "pos.order",
                "xb_set_delivery_signature",
                [[orderId], payload.signature, payload.name]
            );
        } catch {
            this.env.services.notification.add(
                _t("Could not save the delivery signature."),
                { type: "warning" }
            );
        }
    },
});
