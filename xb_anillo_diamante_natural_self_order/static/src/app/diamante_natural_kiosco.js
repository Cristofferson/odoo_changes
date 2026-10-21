/**
 * Kiosco: al elegir «Diamante natural» en un anillo, el cliente escoge el diamante (cualquier forma).
 * La selección muestra montadura + diamante; sin diamante no se agrega. Al agregar entran el
 * anillo (cantidad 1) y el diamante; el servidor rechaza un pedido con un anillo sin su diamante.
 */
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { useState } from "@odoo/owl";
import { ProductPage } from "@pos_self_order/app/pages/product_page/product_page";

const NATURAL = "Diamante natural";
const POR_PAGINA = 12;
const RANGOS = [
    { id: "", nombre: "Todos" },
    { id: "0-0.3", nombre: "Hasta 0.29 ct", min: 0, max: 0.3 },
    { id: "0.3-0.5", nombre: "0.30 a 0.49 ct", min: 0.3, max: 0.5 },
    { id: "0.5-1", nombre: "0.50 a 0.99 ct", min: 0.5, max: 1 },
    { id: "1-2", nombre: "1.00 a 1.99 ct", min: 1, max: 2 },
    { id: "2-", nombre: "2.00 ct o más", min: 2, max: 1e9 },
];

patch(ProductPage.prototype, {
    setup() {
        super.setup(...arguments);
        this.xbdn = useState({ datos: null, cargando: false, error: false, elegido: null, forma: "", rango: "", mostrar: POR_PAGINA });
        this.xbdnRangos = RANGOS;
    },

    get xbdnNatural() {
        if (!this.props.productTemplate?.xb_precio_por_metal) {
            return false;
        }
        const ptavs = this.selfOrder.models["product.template.attribute.value"];
        const natural = this.getSelectedAttributesValues().some((id) => {
            const v = ptavs.get(Number(id));
            return v?.name === NATURAL && v.attribute_id?.name === "Piedra";
        });
        if (natural && !this.xbdn.datos && !this.xbdn.cargando) {
            // Fuera del render: aquí solo se lee el estado.
            Promise.resolve().then(() => this.xbdnCargar());
        }
        return natural;
    },

    xbdnCargar() {
        if (this.xbdn.datos || this.xbdn.cargando) {
            return;
        }
        this.xbdn.cargando = true;
        rpc("/pos-self-order/xb-diamantes-naturales", { access_token: this.selfOrder.access_token })
            .then((res) => {
                // Solo los que el kiosco tiene cargados se pueden agregar al pedido.
                const tmpls = this.selfOrder.models["product.template"];
                res.diamantes = res.diamantes.filter((d) => tmpls.get(d.tmpl_id));
                this.xbdn.datos = res;
            })
            .catch(() => (this.xbdn.error = true))
            .finally(() => (this.xbdn.cargando = false));
    },

    get xbdnLista() {
        if (!this.xbdn.datos) {
            return [];
        }
        const rango = RANGOS.find((r) => r.id === this.xbdn.rango);
        return this.xbdn.datos.diamantes.filter(
            (d) => (!this.xbdn.forma || d.forma === this.xbdn.forma)
                && (!rango || !rango.id || (d.quilates >= rango.min && d.quilates < rango.max))
        );
    },

    xbdnFiltrar(campo, valor) {
        this.xbdn[campo] = valor;
        this.xbdn.mostrar = POR_PAGINA;
    },

    xbdnElegir(d) {
        this.xbdn.elegido = d;
    },

    xbdnTexto(d) {
        return [d.forma, d.quilates ? d.quilates.toFixed(2) + " ct" : ""].filter(Boolean).join(" · ");
    },

    xbdnSpecs(d) {
        return [d.color && "Color " + d.color, d.pureza && "Pureza " + d.pureza, d.corte && "Corte " + d.corte]
            .filter(Boolean).join(" · ");
    },

    isAddToCartEnabled() {
        return super.isAddToCartEnabled() && (!this.xbdnNatural || Boolean(this.xbdn.elegido));
    },

    getProductPrice() {
        const precio = super.getProductPrice(...arguments);
        if (this.xbdnNatural && this.xbdn.elegido) {
            // Cada anillo con diamante natural es pieza única: montadura + diamante, una vez.
            return precio / (this.state.qty || 1) + this.xbdn.elegido.precio;
        }
        return precio;
    },

    addToCart() {
        const gema = this.xbdnNatural ? this.xbdn.elegido : null;
        if (!this.isAddToCartEnabled()) {
            return;
        }
        if (!gema) {
            return super.addToCart(...arguments);
        }
        const tmplGema = this.selfOrder.models["product.template"].get(gema.tmpl_id);
        this.state.qty = 1;
        super.addToCart(...arguments);
        this.selfOrder.addToCart(tmplGema, 1, "Diamante para " + this.props.productTemplate.name, {}, {});
    },
});
