/**
 * Cotización desde el kiosco: el cliente deja su nombre y celular y se lleva la
 * cotización impresa (en la impresora del kiosco) y/o la recibe por WhatsApp. Se crea
 * igual que las cotizaciones de la caja.
 */
import { Component, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { useSelfOrder } from "@pos_self_order/app/services/self_order_service";
import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";

export class XbQuoteTicket extends Component {
    static template = "xb_self_order_quotation.Ticket";
    static props = { src: String };
}

export class XbQuoteDialog extends Component {
    static template = "xb_self_order_quotation.Dialog";
    static props = { modo: String, close: Function };

    setup() {
        this.selfOrder = useSelfOrder();
        this.router = useService("router");
        const modos = this.selfOrder.config._xb_quotation || {};
        this.modos = modos;
        this.state = useState({
            name: "",
            phone: "",
            privacy: false,
            print: this.props.modo === "print" && modos.print,
            whatsapp: this.props.modo === "whatsapp" && modos.whatsapp,
            sending: false,
            error: "",
            done: null,
        });
    }

    get digits() {
        return (this.state.phone || "").replace(/\D/g, "");
    }

    get canSend() {
        const s = this.state;
        return (
            !s.sending && s.privacy && s.name.trim().length >= 2 && this.digits.length === 10 &&
            (s.print || s.whatsapp)
        );
    }

    lines() {
        return this.selfOrder.currentOrder.lines
            .filter((l) => !l.combo_parent_id && l.product_id?.product_tmpl_id)
            .map((l) => ({
                template_id: l.product_id.product_tmpl_id.id,
                ptav_ids: [
                    ...(l.product_id.product_template_attribute_value_ids || []),
                    ...(l.attribute_value_ids || []),
                ].map((v) => v.id),
                qty: l.qty,
            }));
    }

    async send() {
        if (!this.canSend) {
            return;
        }
        const s = this.state;
        s.sending = true;
        s.error = "";
        try {
            const res = await rpc("/xb_kiosk/quotation", {
                access_token: this.selfOrder.access_token,
                name: s.name,
                phone: this.digits,
                lines: this.lines(),
                send_whatsapp: s.whatsapp,
            });
            if (!res?.ok) {
                s.error = res?.error || _t("The quotation could not be made. Please ask at the counter.");
                return;
            }
            let impresa = false;
            if (s.print && res.image) {
                try {
                    // A printer that does not answer must not leave the customer waiting.
                    const limite = new Promise((resolve) => setTimeout(() => resolve(false), 20000));
                    impresa = Boolean(
                        await Promise.race([
                            this.selfOrder.printer.print(XbQuoteTicket, {
                                src: "data:image/jpeg;base64," + res.image,
                            }),
                            limite,
                        ])
                    );
                } catch {
                    impresa = false;
                }
            }
            s.done = {
                name: res.name,
                customer: res.customer.split(" ")[0],
                whatsapp: res.whatsapp === true,
                whatsappFailed: s.whatsapp && res.whatsapp !== true,
                printed: s.print && impresa,
                printFailed: s.print && !impresa,
            };
        } catch {
            s.error = _t("The quotation could not be made. Please ask at the counter.");
        } finally {
            s.sending = false;
        }
    }

    finish() {
        this.selfOrder.cancelOrder();
        this.props.close();
        this.router.navigate("default");
    }
}

patch(CartPage.prototype, {
    get xbQuotation() {
        const modos = this.selfOrder.config._xb_quotation || {};
        return modos.print || modos.whatsapp ? modos : null;
    },
    xbQuote(modo) {
        this.dialog.add(XbQuoteDialog, { modo });
    },
});
