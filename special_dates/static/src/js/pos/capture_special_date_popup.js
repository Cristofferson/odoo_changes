/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

/**
 * Capture Special Date popup.
 *
 * Shown to the cashier when a product whose POS category triggers a
 * special-date capture is added to the order AND the order has a
 * customer assigned.
 *
 * Props expected:
 *   partnerName  - display name of the customer
 *   wishTypeName - e.g. "Aniversario de bodas"
 *   wishTypeIcon - emoji shown in the popup
 *   defaultDate  - ISO 'YYYY-MM-DD' string (next Saturday)
 *   onConfirm(date) - async fn called with the chosen date if user accepts
 *   onLater()       - fn called if user clicks "Later" (keeps pending)
 *   onDismiss()     - fn called if user clicks "Doesn't apply" (clears pending)
 */
export class CaptureSpecialDatePopup extends Component {
    static template = "special_dates.CaptureSpecialDatePopup";
    static components = { Dialog };
    static props = {
        partnerName: String,
        wishTypeName: String,
        wishTypeIcon: String,
        defaultDate: String,
        onConfirm: Function,
        onLater: Function,
        onDismiss: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            date: this.props.defaultDate,
            busy: false,
        });
        this.notification = useService("notification");
    }

    /** Formatted version of the chosen date for display purposes. */
    get formattedDate() {
        if (!this.state.date) return "";
        try {
            const d = new Date(this.state.date + "T00:00:00");
            return d.toLocaleDateString(undefined, {
                weekday: "long",
                year: "numeric",
                month: "long",
                day: "numeric",
            });
        } catch (e) {
            return this.state.date;
        }
    }

    onDateChange(ev) {
        this.state.date = ev.target.value;
    }

    async onClickConfirm() {
        if (this.state.busy) return;
        if (!this.state.date) {
            this.notification.add(_t("Please pick a date."), { type: "warning" });
            return;
        }
        this.state.busy = true;
        try {
            await this.props.onConfirm(this.state.date);
        } catch (err) {
            console.warn("[special_dates] capture confirm failed:", err);
            this.notification.add(
                _t("Could not save the reminder. Please try again."),
                { type: "danger" }
            );
            this.state.busy = false;
            return;
        }
        this.props.close();
    }

    onClickLater() {
        this.props.onLater();
        this.props.close();
    }

    onClickDismiss() {
        this.props.onDismiss();
        this.props.close();
    }
}
