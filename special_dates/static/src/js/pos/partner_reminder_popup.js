/** @odoo-module **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class PartnerReminderPopup extends Component {
    static template = "special_dates.PartnerReminderPopup";
    static components = { Dialog };
    static props = {
        partnerName: { type: String, optional: true },
        reminders: { type: Array },
        close: Function,
    };

    get title() {
        return _t("🎉 Special Date Today!");
    }

    onClose() {
        this.props.close();
    }
}
