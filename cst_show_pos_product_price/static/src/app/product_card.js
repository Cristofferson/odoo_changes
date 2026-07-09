/** @odoo-module **/

import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { formatCurrency } from "@web/core/currency";

patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
    },

    get formattedPrice() {
        const product = this.props.product;
        if (!product || !this.pos) {
            return "";
        }
        // Odoo 19: show the price the current order's pricelist resolves for
        // this product. We call ProductTemplateAccounting.getPrice(pricelist, 1)
        // — the same routine pos.order.line uses — which returns a plain number,
        // so there is NO tax-helper / reactive computation to escape this
        // try/catch (an earlier version used getTaxDetails(), which threw a
        // "currency_id of undefined" during render on databases that have
        // pricelists). This matches the vendor's pre-tax display style but is
        // pricelist-aware instead of the raw base price (lst_price).
        try {
            const config = this.pos.config;
            if (!config || !config.currency_id) {
                return "";
            }
            const order = this.pos.getOrder?.();
            const pricelist = order?.pricelist_id || config.pricelist_id || false;
            const price = product.getPrice(pricelist, 1);
            let formatted = formatCurrency(price, config.currency_id.id);
            if (product.to_weight && product.uom_id?.name) {
                formatted = `${formatted}/${product.uom_id.name}`;
            }
            return formatted;
        } catch (e) {
            return "";
        }
    },
});
