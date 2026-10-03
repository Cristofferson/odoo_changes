/** «Ficha de la pieza»: repinta peso y metal fino al cambiar metal, ancho o medida.
 *  (El JS de stij_website usaba el widget viejo de Odoo ≤17 y ni siquiera se cargaba.) */
import { patch } from "@web/core/utils/patch";
import { WebsiteSale } from "@website_sale/interactions/website_sale";

patch(WebsiteSale.prototype, {
    _onChangeCombination(ev, parent, combination) {
        super._onChangeCombination(...arguments);
        for (const [id, key] of [["dmn_peso", "dmn_peso"], ["dmn_fino", "dmn_fino"], ["dmn_stones", "dmn_stones"]]) {
            const el = document.getElementById(id);
            if (el && combination[key]) {
                el.textContent = combination[key];
            }
        }
        // Piedras y diamantes de la combinación elegida (cambian con la piedra central)
        const gem = document.getElementById("xb_gemas");
        if (gem && combination.xb_gemas !== undefined) {
            gem.textContent = combination.xb_gemas || "";
            gem.closest("li")?.classList.toggle("d-none", !combination.xb_gemas);
        }
        const ul = document.getElementById("xb_diamantes");
        if (ul && combination.xb_diamantes !== undefined) {
            ul.replaceChildren(...(combination.xb_diamantes || []).map((txt) => {
                const li = document.createElement("li");
                li.textContent = txt;
                return li;
            }));
            ul.closest("li")?.classList.toggle("d-none", !(combination.xb_diamantes || []).length);
        }
    },
});
