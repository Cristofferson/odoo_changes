/**
 * Joyas cotizadas por metal: el TPV no puede calcular su precio (depende del oro del
 * día y de la lista de materiales), así que al agregarlas al ticket se le pide al
 * servidor con la combinación elegida y la lista de precios de la orden.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const res = await super.addLineToOrder(...arguments);
        try {
            const line = order.getSelectedOrderline();
            const tmpl = line?.product_id?.product_tmpl_id;
            if (line && tmpl?.xb_precio_por_metal && line.price_type !== "manual") {
                const ids = [
                    ...(line.product_id.product_template_attribute_value_ids || []).map((v) => v.id),
                    ...(line.attribute_value_ids || []).map((v) => v.id),
                ];
                const precio = await this.data.call("product.product", "xb_pos_precio_metal",
                    [[line.product_id.id], ids, order.pricelist_id?.id || false]);
                if (precio) {
                    line.setUnitPrice(precio);
                    line.price_type = "manual";
                }
            }
        } catch (e) {
            console.warn("xb_joyeria_peso_precio: no se pudo obtener el precio", e);
        }
        return res;
    },
});
