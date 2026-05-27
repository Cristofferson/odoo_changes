/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

/*
 * Popup that shows ALL customers with a special date today.
 * Opens automatically when the POS session starts AND every N hours
 * while the session stays open. The cashier can close it; it will
 * re-appear automatically after the interval.
 */
export class TodayRemindersPopup extends Component {
    static template = "special_dates.TodayRemindersPopup";
    static components = { Dialog };
    static props = {
        count: { type: Number, optional: true },
        items: { type: Array },
        close: Function,
    };
    static defaultProps = { count: 0 };

    setup() {
        this.state = useState({ search: "" });
    }

    get title() {
        if (this.props.count === 0) {
            return _t("🎉 Special dates today");
        }
        if (this.props.count === 1) {
            return _t("🎉 1 customer celebrating today");
        }
        return _t("🎉 %s customers celebrating today", this.props.count);
    }

    get filteredItems() {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) return this.props.items;
        return this.props.items.filter((it) =>
            (it.partner_name || "").toLowerCase().includes(q)
        );
    }

    onClose() {
        this.props.close();
    }
}
