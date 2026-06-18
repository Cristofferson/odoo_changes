/** @odoo-module */
// XUBAX - Delivery Receipt Signature - POS Bridge
// A POS popup wrapping the native NameAndSignature pad. Used with
// makeAwaitable: confirm() resolves the awaitable with {name, signature}
// (base64 without the data-URL prefix, like portal.SignatureForm does);
// closing without confirming resolves undefined.
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { NameAndSignature } from "@web/core/signature/name_and_signature";
import { _t } from "@web/core/l10n/translation";

export class DeliverySignaturePopup extends Component {
    static template = "xb_delivery_signature_pos.DeliverySignaturePopup";
    static components = { Dialog, NameAndSignature };
    static props = {
        title: { type: String, optional: true },
        defaultName: { type: String, optional: true },
        getPayload: { type: Function },
        close: { type: Function },
    };
    static defaultProps = {
        title: _t("Delivery receipt signature"),
        defaultName: "",
    };

    setup() {
        // The state object NameAndSignature populates with the canvas accessors.
        this.signature = useState({
            name: this.props.defaultName,
            getSignatureImage: () => "",
            resetSignature: () => {},
        });
    }

    get nameAndSignatureProps() {
        // mode "draw" forces the hand-drawing pad by default (finger/stylus),
        // even though the customer's name is prefilled on the record/receipt.
        return { signature: this.signature, signatureType: "signature", mode: "draw" };
    }

    confirm() {
        const dataUrl = this.signature.getSignatureImage();
        const signature = dataUrl ? dataUrl.split(",")[1] : "";
        this.props.getPayload({ name: this.signature.name, signature });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
