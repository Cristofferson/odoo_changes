/**
 * Joyas de catálogo (xb_precio_por_metal): se hacen sobre pedido, así que al venderlas todavía no
 * existe la pieza ni su número de serie; la serie nace en la orden de fabricación. La caja no la pide
 * al agregar la joya, no deja la cantidad en 0 por no tenerla y no avisa de «series faltantes» al cobrar.
 *
 * La ventana de opciones muestra el precio real de la combinación elegida (lo calcula el servidor:
 * metal del día + lista de materiales), en vez de $0.00.
 */
import { patch } from "@web/core/utils/patch";
import { useEffect, useState } from "@odoo/owl";
import { ProductTemplate } from "@point_of_sale/app/models/product_template";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { ProductConfiguratorPopup } from "@point_of_sale/app/components/popups/product_configurator_popup/product_configurator_popup";

const esJoyaSobrePedido = (tmpl) => Boolean(tmpl?.xb_precio_por_metal);

patch(ProductTemplate.prototype, {
    isTracked() {
        return esJoyaSobrePedido(this) ? false : super.isTracked(...arguments);
    },
});

patch(PosOrderline.prototype, {
    setPackLotLines({ modifiedPackLotLines, newPackLotLines, setQuantity = true }) {
        const sinSeries = !Object.keys(modifiedPackLotLines || {}).length && !(newPackLotLines || []).length;
        if (esJoyaSobrePedido(this.product_id?.product_tmpl_id) && sinSeries) {
            return;
        }
        return super.setPackLotLines(...arguments);
    },
    hasValidProductLot() {
        return esJoyaSobrePedido(this.product_id?.product_tmpl_id) || super.hasValidProductLot(...arguments);
    },
});

patch(ProductConfiguratorPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.xb = useState({ precio: null });
        if (!esJoyaSobrePedido(this.props.productTemplate)) {
            return;
        }
        useEffect(
            (clave) => {
                const ids = this.selectedValues.map((v) => v.id);
                const pricelist = this.pos.getOrder()?.pricelist_id || this.pos.config.pricelist_id;
                this.xb.precio = null;
                this.pos.data
                    .call("product.template", "xb_pos_precio_combinacion", [this.props.productTemplate.id, ids, pricelist?.id || false])
                    .then((r) => {
                        if (clave === this.selectedValues.map((v) => v.id).join(",")) {
                            this.xb.precio = r ? r.con : null;
                        }
                    })
                    .catch(() => {});
            },
            () => [this.selectedValues.map((v) => v.id).join(",")]
        );
    },
    get title() {
        if (esJoyaSobrePedido(this.props.productTemplate)) {
            const precio = this.xb?.precio;
            return `${this.props.productTemplate.display_name} | ${
                precio === null || precio === undefined ? "…" : this.env.utils.formatCurrency(precio)
            }`;
        }
        return super.title;
    },
});
