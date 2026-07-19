/** @odoo-module **/
// XUBAX Gestión Parroquial — POS
// Al agregar al carrito un producto marcado como intención, pide misa, tipo
// y nombres; guarda los datos en la línea y un resumen como nota de cliente
// (visible en pantalla y en el ticket).

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { IntencionPopup } from "@xb_parroquia_pos/app/popups/intencion_popup";

patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        let template = vals.product_tmpl_id;
        if (typeof template === "number") {
            template = this.data.models["product.template"].get(template);
            vals = { ...vals, product_tmpl_id: template };
        }

        if (template?.xb_es_intencion && !vals.intencion_nombres) {
            const celebraciones =
                this.data.models["parroquia.celebracion"]?.getAll() || [];
            if (!celebraciones.length) {
                this.dialog.add(AlertDialog, {
                    title: _t("Sin misas agendadas"),
                    body: _t(
                        "No hay celebraciones próximas agendadas. Capture " +
                        "primero la misa en la aplicación Parroquia."
                    ),
                });
                return;
            }
            const payload = await makeAwaitable(this.dialog, IntencionPopup, {
                celebraciones: celebraciones.map((c) => ({
                    id: c.id,
                    label: c.etiqueta_pos,
                })),
            });
            if (!payload) {
                return;
            }
            vals = {
                ...vals,
                intencion_celebracion_id:
                    this.data.models["parroquia.celebracion"].get(
                        payload.celebracionId
                    ),
                intencion_tipo: payload.tipo,
                intencion_nombres: payload.nombres,
                customer_note: `${payload.celebracionLabel}\n${payload.tipoLabel}: ${payload.nombres}`,
            };
            opts = { ...opts, merge: false };
        }

        return super.addLineToOrder(vals, order, opts, configure);
    },
});
