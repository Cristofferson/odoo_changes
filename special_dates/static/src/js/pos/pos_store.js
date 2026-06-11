/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { PartnerReminderPopup } from "./partner_reminder_popup";
import { TodayRemindersPopup } from "./today_reminders_popup";
import { CaptureSpecialDatePopup } from "./capture_special_date_popup";

/*
 * Special Dates patches the POS store WITHOUT touching how data is
 * loaded. Everything is fetched via RPC after the POS is initialised.
 *
 * Behaviours:
 *   1. On session open: show a popup listing every customer with a
 *      special date today.
 *   2. While the session stays open, re-show that popup every N hours.
 *   3. When a product whose POS category triggers capture is added to
 *      the order, prompt the cashier to register a special date for
 *      the customer.
 *   4. If a customer is later assigned to an order that has pending
 *      captures, the popup is shown then.
 *   5. Before paying, any pending captures are surfaced one more time.
 */

/**
 * Return ISO 'YYYY-MM-DD' string for the next Saturday strictly after
 * today. If today is Saturday, returns Saturday of the following week
 * (today + 7 days).
 */
function nextSaturdayIso() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dow = today.getDay(); // 0=Sun ... 6=Sat
    let daysAhead = (6 - dow + 7) % 7;
    if (daysAhead === 0) daysAhead = 7;
    const out = new Date(today);
    out.setDate(today.getDate() + daysAhead);
    const yyyy = out.getFullYear();
    const mm = String(out.getMonth() + 1).padStart(2, "0");
    const dd = String(out.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);

        // ===== Today welcome popup (existing behaviour) =====
        this._xbTodayTimer = null;
        this._xbInitTodayPopup().catch((err) => {
            console.warn("[special_dates] today init failed:", err);
        });

        // ===== Capture-at-POS config =====
        // Map<pos_category_id, {wish_type_id, wish_type_name, wish_type_icon}>
        this._xbCaptureConfig = new Map();
        // Map<order.uuid, Set<wish_type_id>> -- pending captures per order
        this._xbPendingCaptures = new Map();
        // Map<"orderUuid:wishTypeId", "dismissed"> -- user explicitly opted out
        this._xbDismissedCaptures = new Set();
        this._xbLoadCaptureConfig().catch((err) => {
            console.warn("[special_dates] capture config load failed:", err);
        });
    },

    // ------------------------------------------------------------------
    // Today welcome popup (unchanged)
    // ------------------------------------------------------------------
    async _xbInitTodayPopup() {
        await this._xbShowTodayIfAny();
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
        if (typeof data.interval_hours === "number") {
            this._xbInterval = data.interval_hours;
        }
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

    // ------------------------------------------------------------------
    // Per-partner celebration popup (unchanged)
    // ------------------------------------------------------------------
    async setPartnerToCurrentOrder(partner, ...args) {
        const result = await super.setPartnerToCurrentOrder(partner, ...args);
        this._xbCheckPartnerReminders(partner).catch((err) => {
            console.warn("[special_dates] partner check failed:", err);
        });
        // If this order has pending captures from earlier product additions,
        // now is the time to surface them.
        this._xbDrainPendingCaptures().catch((err) => {
            console.warn("[special_dates] drain pending failed:", err);
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

    // ------------------------------------------------------------------
    // Capture-at-POS
    // ------------------------------------------------------------------

    /** Fetch the category -> wish-type mapping once at startup. */
    async _xbLoadCaptureConfig() {
        let rows;
        try {
            rows = await this.env.services.orm.call(
                "xb.wish.reminders",
                "get_pos_capture_config",
                []
            );
        } catch (err) {
            console.warn("[special_dates] capture config rpc failed:", err);
            return;
        }
        if (!Array.isArray(rows)) return;
        for (const row of rows) {
            this._xbCaptureConfig.set(row.pos_category_id, {
                wish_type_id: row.wish_type_id,
                wish_type_name: row.wish_type_name,
                wish_type_icon: row.wish_type_icon || "🎉",
            });
        }
        console.info(
            "[special_dates] capture config loaded:",
            this._xbCaptureConfig.size,
            "trigger categories"
        );
    },

    /**
     * Look up which capture (if any) is triggered by the POS categories
     * of the given product. Returns the first match or null.
     * `product` is a product record from the POS data.
     */
    _xbCaptureForProduct(product) {
        if (!product) return null;
        if (!this._xbCaptureConfig || this._xbCaptureConfig.size === 0) {
            return null;
        }
        // Different POS data shapes -- be defensive.
        let catIds = [];
        if (Array.isArray(product.pos_categ_ids)) {
            catIds = product.pos_categ_ids
                .map((c) => (typeof c === "object" ? c.id : c))
                .filter(Boolean);
        } else if (product.pos_categ_id) {
            const c = product.pos_categ_id;
            catIds = [typeof c === "object" ? c.id : c];
        }
        for (const id of catIds) {
            const cfg = this._xbCaptureConfig.get(id);
            if (cfg) return cfg;
        }
        return null;
    },

    /**
     * Override addLineToOrder so we can detect when a product belonging
     * to a trigger category is added.
     *
     * Odoo 19's signature: addLineToOrder(vals, order, opts)
     * (we just forward all args to super).
     */
    async addLineToOrder(...args) {
        const line = await super.addLineToOrder(...args);
        try {
            // Resolve the product from the returned line if possible.
            const product = line && line.product_id ? line.product_id : null;
            const cfg = this._xbCaptureForProduct(product);
            if (cfg) {
                const order = this.get_order ? this.get_order() : this.getOrder?.();
                this._xbRegisterPending(order, cfg);
                // If there's a partner already, try to show now.
                const partner =
                    order && (order.get_partner?.() || order.partner_id);
                if (partner && partner.id) {
                    this._xbMaybeShowCapture(order, partner, cfg).catch((err) => {
                        console.warn("[special_dates] capture show failed:", err);
                    });
                }
            }
        } catch (err) {
            console.warn("[special_dates] capture detect failed:", err);
        }
        return line;
    },

    /** Mark wish_type as pending capture for this order. */
    _xbRegisterPending(order, cfg) {
        if (!order || !cfg) return;
        const key = order.uuid || order.name || "";
        if (!key) return;
        // Skip if user explicitly dismissed it.
        if (this._xbDismissedCaptures.has(`${key}:${cfg.wish_type_id}`)) {
            return;
        }
        let set = this._xbPendingCaptures.get(key);
        if (!set) {
            set = new Set();
            this._xbPendingCaptures.set(key, set);
        }
        set.add(cfg.wish_type_id);
    },

    /**
     * Show the capture popup if (a) the partner doesn't already have a
     * matching reminder in the next 90 days and (b) the user hasn't
     * dismissed this capture already.
     */
    async _xbMaybeShowCapture(order, partner, cfg) {
        if (!order || !partner || !cfg) return;
        const orderKey = order.uuid || order.name || "";
        const dismissKey = `${orderKey}:${cfg.wish_type_id}`;
        if (this._xbDismissedCaptures.has(dismissKey)) {
            return;
        }
        // Anti-duplicate: ask the backend if this partner already has a
        // matching reminder in the next 90 days.
        let exists;
        try {
            exists = await this.env.services.orm.call(
                "xb.wish.reminders",
                "check_existing_for_capture",
                [partner.id, cfg.wish_type_id]
            );
        } catch (err) {
            console.warn("[special_dates] dupe-check failed:", err);
            exists = false;
        }
        if (exists) {
            // Silently clear the pending entry.
            this._xbClearPending(order, cfg.wish_type_id);
            return;
        }

        const partnerName = partner.name || partner.display_name || "";
        const orderRef = order.name || order.uuid || "";

        const self = this;
        const onConfirm = async (dateIso) => {
            const result = await self.env.services.orm.call(
                "xb.wish.reminders",
                "create_from_pos",
                [partner.id, cfg.wish_type_id, dateIso, orderRef]
            );
            if (result && result.error) {
                throw new Error(result.error);
            }
            self._xbClearPending(order, cfg.wish_type_id);
            if (self.env.services.notification) {
                self.env.services.notification.add(
                    `${cfg.wish_type_icon || "🎉"} ${cfg.wish_type_name} saved`,
                    { type: "success" }
                );
            }
        };
        const onLater = () => {
            // Keep pending; don't dismiss. Will reappear at payment time.
        };
        const onDismiss = () => {
            self._xbDismissedCaptures.add(dismissKey);
            self._xbClearPending(order, cfg.wish_type_id);
        };

        this.dialog.add(CaptureSpecialDatePopup, {
            partnerName,
            wishTypeName: cfg.wish_type_name,
            wishTypeIcon: cfg.wish_type_icon || "🎉",
            defaultDate: nextSaturdayIso(),
            onConfirm,
            onLater,
            onDismiss,
        });
    },

    _xbClearPending(order, wishTypeId) {
        if (!order) return;
        const key = order.uuid || order.name || "";
        const set = this._xbPendingCaptures.get(key);
        if (!set) return;
        set.delete(wishTypeId);
        if (set.size === 0) {
            this._xbPendingCaptures.delete(key);
        }
    },

    /**
     * If the current order has any pending captures (typically because
     * the partner was just assigned), surface them now.
     */
    async _xbDrainPendingCaptures() {
        const order = this.get_order ? this.get_order() : this.getOrder?.();
        if (!order) return;
        const key = order.uuid || order.name || "";
        const set = this._xbPendingCaptures.get(key);
        if (!set || set.size === 0) return;

        const partner = order.get_partner?.() || order.partner_id;
        if (!partner || !partner.id) return;

        const wishTypeIds = Array.from(set);
        for (const wid of wishTypeIds) {
            // Find the cfg by wish_type_id.
            let cfg = null;
            for (const v of this._xbCaptureConfig.values()) {
                if (v.wish_type_id === wid) {
                    cfg = v;
                    break;
                }
            }
            if (cfg) {
                // Wait for each popup sequentially to avoid stacking.
                try {
                    await this._xbMaybeShowCapture(order, partner, cfg);
                } catch (err) {
                    console.warn("[special_dates] drain show failed:", err);
                }
            }
        }
    },

    /**
     * Before paying: surface any still-pending captures one more time.
     * We hook into pay() (Odoo 19 POS uses this as the validate trigger).
     */
    async pay(...args) {
        try {
            await this._xbDrainPendingCaptures();
        } catch (err) {
            console.warn("[special_dates] pre-pay drain failed:", err);
        }
        return super.pay(...args);
    },
});
