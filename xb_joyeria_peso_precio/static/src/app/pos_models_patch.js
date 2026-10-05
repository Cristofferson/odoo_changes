/**
 * - «Pieza a la medida por gramo»: la tarjeta y la ventana de opciones muestran el precio real
 *   (metal del día + mano de obra) que el servidor calculó al abrir la caja, en vez del costo de la
 *   mano de obra sola. Sin variante (tarjeta) se muestra el precio más bajo.
 * - Las opciones de cada atributo salen en el orden configurado en Odoo, no en el orden de carga.
 */
import { patch } from "@web/core/utils/patch";
import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { ProductTemplateAttributeLine } from "@point_of_sale/app/models/product_template_attribute_line";

patch(ProductTemplate.prototype, {
    getPrice(pricelist, quantity, price_extra = 0, recurring = false, variant = false) {
        const tmpl = variant?.product_tmpl_id || this;
        const mapa = tmpl.xb_por_gramo && pricelist && tmpl.xb_precios_gramo?.[String(pricelist.id)];
        if (mapa) {
            const precio = variant ? mapa[String(variant.id)] : mapa.min;
            if (precio !== undefined && precio !== null) {
                return precio;
            }
        }
        return super.getPrice(...arguments);
    },
});

patch(ProductTemplateAttributeLine.prototype, {
    values() {
        const vals = super.values();
        if (!vals?.length || !vals.some((v) => v.xb_secuencia !== undefined)) {
            return vals;
        }
        return [...vals].sort((a, b) => (a.xb_secuencia || 0) - (b.xb_secuencia || 0) || a.id - b.id);
    },
});
