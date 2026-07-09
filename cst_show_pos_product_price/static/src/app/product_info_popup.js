/** @odoo-module **/

import { ProductInfoPopup } from "@point_of_sale/app/components/popups/product_info_popup/product_info_popup";
import { patch } from "@web/core/utils/patch";

patch(ProductInfoPopup.prototype, {
    get vatLabel() {
        // Odoo core reuses res.country.vat_label (="RFC" for Mexico, meant to
        // label a partner's tax-id field) as the label for the sale's tax
        // amount here, which reads as nonsense next to a $ tax amount.
        return "IVA";
    },
});
