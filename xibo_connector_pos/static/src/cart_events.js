/** @odoo-module **/
/**
 * Xibo Connector — POS cart event hooks
 *
 * Patches PosStore.addLineToCurrentOrder which is the canonical entry point
 * for adding lines to the current order on all modern Odoo POS versions.
 * Falls back gracefully if the method does not exist by being a no-op.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { rpc } from "@web/core/network/rpc";

function _notify(config, payload) {
    try {
        if (!config || !config.id) return;
        if (!config.xibo_server_id) return;
        if (!config.xibo_customer_display_enabled && !config.xibo_reco_enabled) return;
        rpc("/web/dataset/call_kw/pos.config/xibo_notify_cart_event", {
            model: "pos.config",
            method: "xibo_notify_cart_event",
            args: [[config.id], payload],
            kwargs: {},
        }).catch((err) => {
            console.warn("[xibo_connector_pos] RPC failed:", err);
        });
    } catch (err) {
        console.warn("[xibo_connector_pos] notify error:", err);
    }
}

function _cartCount(order) {
    if (!order) return 0;
    try {
        if (order.lines && Array.isArray(order.lines)) return order.lines.length;
        if (typeof order.get_orderlines === "function") return order.get_orderlines().length;
        if (order.orderlines && order.orderlines.length !== undefined) return order.orderlines.length;
    } catch (err) {}
    return 0;
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        // Force the cashier's device_uuid (used by the Customer Display
        // websocket bus) to the stable UUID we own and configured in the
        // Xibo Webpage widget. This way the cashier publishes events on
        // the same channel that the external Xibo screen is subscribed
        // to, regardless of which browser or session the cashier uses.
        try {
            const xiboUuid = this.config?.xibo_customer_display_device_uuid;
            if (xiboUuid && this.config?.xibo_customer_display_enabled) {
                const current = localStorage.getItem("device_uuid");
                if (current !== xiboUuid) {
                    localStorage.setItem("device_uuid", xiboUuid);
                    console.log("[xibo_connector_pos] device_uuid set to:", xiboUuid);
                }
            }
        } catch (err) {
            console.warn("[xibo_connector_pos] device_uuid sync error:", err);
        }
    },

    async addLineToCurrentOrder(vals, opts = {}, configure = true) {
        const line = await super.addLineToCurrentOrder(...arguments);
        try {
            const config = this.config;
            const order = (typeof this.get_order === "function") ? this.get_order() : this.currentOrder;
            const product = line?.product_id || (typeof line?.get_product === "function" ? line.get_product() : null);
            _notify(config, {
                config_id: config?.id,
                event: "add",
                product_id: product?.id || false,
                product_name: product?.display_name || product?.name || "",
                price: line?.price_unit || (typeof line?.get_unit_price === "function" ? line.get_unit_price() : 0),
                quantity: line?.qty || (typeof line?.get_quantity === "function" ? line.get_quantity() : 1),
                cart_count: _cartCount(order),
            });
        } catch (err) {
            console.warn("[xibo_connector_pos] add-hook error:", err);
        }
        return line;
    },

    addNewOrder() {
        const result = super.addNewOrder(...arguments);
        try {
            _notify(this.config, {
                config_id: this.config?.id,
                event: "clear",
                cart_count: 0,
            });
        } catch (err) {
            console.warn("[xibo_connector_pos] new-order hook error:", err);
        }
        return result;
    },
});
