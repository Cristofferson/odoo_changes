/**
 * Kiosco: el diamante natural elegido viaja al muro junto con el anillo.
 */
import { patch } from "@web/core/utils/patch";
import { ProductPage } from "@pos_self_order/app/pages/product_page/product_page";

patch(ProductPage.prototype, {
    get wallStoneId() {
        return this.xbdnNatural && this.xbdn?.elegido ? this.xbdn.elegido.id : null;
    },
});
