/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { PartnerReminderPopup } from "./partner_reminder_popup";
import { TodayRemindersPopup } from "./today_reminders_popup";

/*
 * Special Dates patches the POS store WITHOUT touching how data is
 * loaded. Everything is fetched via RPC after the POS is initialised.
 *
 * Two behaviours:
 *   1. On session open: show a popup listing every customer with a
 *      special date today. If no one is celebrating, show nothing.
 *   2. While the session stays open, re-show that popup every N
 *      hours (configured via the special_dates.pos_popup_interval_hours
 *      system parameter, default 3).
 *
 * Per-customer popup (when the cashier sets a partner on the order)
 * still works as before - through setPartnerToCurrentOrder.
 */
patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        // Kick off the welcome popup logic without blocking startup.
        this._xbTodayTimer = null;
        this._xbInitTodayPopup().catch((err) => {
            console.warn("[special_dates] today init failed:", err);
        });
    },

    async _xbInitTodayPopup() {
        // First fetch + show.
        await this._xbShowTodayIfAny();
        // Schedule the periodic re-show.
        if (this._xbInterval && this._xbInterval > 0) {
            const ms = this._xbInterval * 60 * 60 * 1000;
            this._xbTodayTimer = setInterval(() => {
                this._xbShowTodayIfAny().catch((err) => {
                    console.warn("[special_dates] periodic show failed:", err);
                });
            }, ms);
        }
    },

    async _xbShowTodayIfAny() {
        let data;
        try {
            data = await this.env.services.orm.call(
                "res.partner",
                "get_today_pos_reminders",
                []
            );
        } catch (err) {
            console.warn("[special_dates] today fetch failed:", err);
            return;
        }
        // Cache the interval for the periodic timer setup.
        if (typeof data.interval_hours === "number") {
            this._xbInterval = data.interval_hours;
        }
        // Don't open the popup if there is nothing to show.
        if (!data || !data.count) {
            return;
        }
        try {
            this.dialog.add(TodayRemindersPopup, {
                count: data.count,
                items: data.items,
            });
        } catch (err) {
            console.warn("[special_dates] popup open failed:", err);
        }
    },

    /**
     * Cashier selected a customer on the current order.
     * If the customer has a special date today, show a single-customer
     * celebration popup.
     */
    async setPartnerToCurrentOrder(partner, ...args) {
        const result = await super.setPartnerToCurrentOrder(partner, ...args);
        this._xbCheckPartnerReminders(partner).catch((err) => {
            console.warn("[special_dates] partner check failed:", err);
        });
        return result;
    },

    async _xbCheckPartnerReminders(partner) {
        if (!partner || !partner.id) return;
        let reminders = [];
        try {
            reminders = await this.env.services.orm.call(
                "res.partner",
                "get_pos_reminder_data",
                [[partner.id]]
            );
        } catch (err) {
            console.warn("[special_dates] reminders fetch failed:", err);
            return;
        }
        if (Array.isArray(reminders) && reminders.length > 0) {
            this.dialog.add(PartnerReminderPopup, {
                partnerName: partner.name || "",
                reminders: reminders,
            });
        }
    },
});
