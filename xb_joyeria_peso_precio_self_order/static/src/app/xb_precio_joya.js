/**
 * Joyas cotizadas por metal en el kiosco: el precio depende del oro del día y de las
 * opciones (metal, medida, piedra), y solo el servidor lo sabe calcular.
 * - Lista: «Desde» que mandó el servidor al cargar el kiosco (como en la página web).
 * - Ficha: se le pregunta al servidor cada vez que cambian las opciones.
 * - Carrito: el renglón entra con ese precio (el servidor lo vuelve a calcular al pedir).
 */
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { useState } from "@odoo/owl";
import { ProductPage } from "@pos_self_order/app/pages/product_page/product_page";
import { SelfOrder } from "@pos_self_order/app/services/self_order_service";

const esJoya = (tmpl) => Boolean(tmpl?.xb_precio_por_metal);

async function precioJoya(selfOrder, tmpl, ptavIds) {
    try {
        return await rpc("/pos-self-order/xb-precio-joya", {
            access_token: selfOrder.access_token,
            product_tmpl_id: tmpl.id,
            ptav_ids: ptavIds.map((id) => Number(id)),
        });
    } catch (e) {
        console.warn("xb_joyeria_peso_precio_self_order: sin precio", e);
        return false;
    }
}

patch(SelfOrder.prototype, {
    xbConImpuestos(tmpl, sinImpuestos) {
        const taxes = tmpl.getTaxDetails({ overridedValues: { price_unit: sinImpuestos, quantity: 1 } });
        return this.isTaxesIncludedInPrice() ? taxes.total_included : taxes.total_excluded;
    },
    getProductDisplayPrice(productTemplate, product) {
        const tmpl = product?.product_tmpl_id || productTemplate;
        if (esJoya(tmpl) && tmpl._xb_desde) {
            return this.xbConImpuestos(tmpl, tmpl._xb_desde);
        }
        return super.getProductDisplayPrice(...arguments);
    },
    async addToCart(productTemplate, qty, customer_note, selectedValues = {}, customValues = {}) {
        const antes = new Set(this.currentOrder.lines.map((l) => l.uuid));
        await super.addToCart(...arguments);
        if (!esJoya(productTemplate)) {
            return;
        }
        const ids = Array.isArray(selectedValues) ? selectedValues : Object.values(selectedValues).flat();
        const precio = await precioJoya(this, productTemplate, ids);
        if (!precio) {
            return;
        }
        const lineas = this.currentOrder.lines.filter(
            (l) => l.product_id?.product_tmpl_id?.id === productTemplate.id && !antes.has(l.uuid)
        );
        for (const l of lineas) {
            l.setUnitPrice(precio.sin);
            l.price_type = "manual";
        }
    },
});

patch(ProductPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.xb = useState({ clave: null, precio: null, cargando: false });
    },
    getProductPrice() {
        const tmpl = this.props.productTemplate;
        if (!esJoya(tmpl)) {
            return super.getProductPrice(...arguments);
        }
        const ids = this.getSelectedAttributesValues();
        const clave = ids.map(String).sort().join(",");
        if (clave !== this.xb.clave) {
            this.xb.clave = clave;
            this.xb.cargando = true;
            precioJoya(this.selfOrder, tmpl, ids).then((precio) => {
                if (this.xb.clave === clave) {
                    this.xb.precio = precio;
                    this.xb.cargando = false;
                }
            });
        }
        // Lo que falta por elegir el servidor lo completa con lo más económico: el precio
        // cambia opción por opción.
        const sin = this.xb.precio?.sin || tmpl._xb_desde || 0;
        return this.selfOrder.xbConImpuestos(tmpl, sin) * (this.state.qty || 1);
    },
});
