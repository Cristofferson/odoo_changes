/** @odoo-module **/
// XUBAX Gestión Parroquial — POS
// Diálogo de captura de intención: misa + tipo + nombres.

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export const TIPOS_INTENCION = [
    { id: "destacada", label: _t("Intención destacada") },
    { id: "vivos", label: _t("Vivos") },
    { id: "salud", label: _t("Por la salud de") },
    { id: "familias", label: _t("Familias") },
    { id: "difuntos", label: _t("Difuntos") },
    { id: "desaparecidos", label: _t("Desaparecidos") },
    { id: "otros", label: _t("Otros") },
];

export class IntencionPopup extends Component {
    static template = "xb_parroquia_pos.IntencionPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        celebraciones: Array, // [{id, label}]
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Intención de misa"),
    };

    setup() {
        this.tipos = TIPOS_INTENCION;
        this.state = useState({
            celebracionId: this.props.celebraciones[0]?.id || false,
            tipo: "difuntos",
            nombres: "",
        });
    }

    get puedeConfirmar() {
        return Boolean(this.state.celebracionId && this.state.nombres.trim());
    }

    confirm() {
        if (!this.puedeConfirmar) {
            return;
        }
        const celebracion = this.props.celebraciones.find(
            (c) => c.id === Number(this.state.celebracionId)
        );
        const tipo = this.tipos.find((t) => t.id === this.state.tipo);
        this.props.getPayload({
            celebracionId: Number(this.state.celebracionId),
            celebracionLabel: celebracion ? celebracion.label : "",
            tipo: this.state.tipo,
            tipoLabel: tipo ? tipo.label : "",
            nombres: this.state.nombres.trim(),
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
