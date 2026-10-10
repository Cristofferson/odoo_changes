/**
 * Botones del kiosco con palabras de joyería: en la lista no se paga, se ve la selección;
 * en el carrito el pedido va a la caja para pagarse en mostrador.
 */
import { patch } from "@web/core/utils/patch";
import { OrderWidget } from "@pos_self_order/app/components/order_widget/order_widget";

patch(OrderWidget.prototype, {
    get buttonToShow() {
        const res = super.buttonToShow;
        const page = this.router.activeSlot;
        if (page === "product_list") {
            return { ...res, label: "Ver mi selección" };
        }
        if (page === "cart") {
            return { ...res, label: "Pagar en mostrador" };
        }
        return res;
    },
});
