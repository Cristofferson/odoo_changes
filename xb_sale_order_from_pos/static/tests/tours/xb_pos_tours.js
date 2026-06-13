/** @odoo-module **/
// XUBAX - POS tour: create Quotation / Order / Layaway from the cart.
// Exercises the custom "Create Order" control button and the three options of
// the SelectionPopup, asserting the success notification for each flow.
// NOTE: uses demo data; it does NOT cover real fiscal positions or tax-included
// pricing (that parity is verified manually on a production copy).

import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as Notification from "@point_of_sale/../tests/generic_helpers/notification_util";
import { registry } from "@web/core/registry";

// Pick an order type from the custom SelectionPopup ("Create from POS").
function selectOrderType(label) {
    return {
        content: `select order type '${label}'`,
        trigger: `.selection-item:contains("${label}")`,
        run: "click",
    };
}

// One full cycle: add a product, set a customer, open the custom button and
// pick the given order type, then assert the success notification.
function createFromPos(product, partner, orderType) {
    return [
        ProductScreen.addOrderline(product, 1),
        ProductScreen.clickCustomer(partner),
        ...ProductScreen.clickControlButton("Create Order"),
        selectOrderType(orderType),
        Notification.has("created from POS", "success"),
    ].flat();
}

registry.category("web_tour.tours").add("XbCreateOrderFlows", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),

            // Flow 1: Cotización (draft sale order).
            createFromPos("Wall Shelf Unit", "Partner Test 1", "Quotation"),

            // Flow 2: Pedido (confirmed, no advance).
            Chrome.createFloatingOrder(),
            createFromPos("Wall Shelf Unit", "Partner Test 1", "Order"),

            // Flow 3: Apartado (confirmed, with advance — needs down-payment product).
            Chrome.createFloatingOrder(),
            createFromPos("Wall Shelf Unit", "Partner Test 1", "Layaway"),
        ].flat(),
});
