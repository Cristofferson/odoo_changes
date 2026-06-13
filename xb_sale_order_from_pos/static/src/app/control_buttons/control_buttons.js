/** @odoo-module **/
// XUBAX - Sales, Quotations & Layaway from POS (Phase 2 frontend)
// Original, clean-room implementation. Adds a control button to create a
// Quotation / Order / Layaway from the current POS cart by calling the backend
// method sale.order.xb_create_order_from_pos. It does NOT replace the native
// pos_sale loader button ("Quotation/Order").

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(ControlButtons.prototype, {
    /**
     * Build the order-type options offered to the cashier, honoring the per-POS
     * toggles. Each entry's `item` is the flag set sent to the backend.
     * - "Quotation"      iff xb_allow_quotation.
     * - xb_differentiate_order_layaway OFF -> single "Order / Layaway"
     *   (confirmed; advance is optional, added later via the native flow).
     * - xb_differentiate_order_layaway ON  -> "Order" (confirmed, no advance)
     *   and "Layaway" (confirmed, with advance).
     */
    xbGetOrderTypeOptions() {
        const config = this.pos.config;
        const options = [];

        if (config.xb_allow_quotation) {
            options.push({
                id: "quotation",
                label: _t("Quotation"),
                item: { type: "quotation", confirm: false, with_down_payment: false },
            });
        }

        if (config.xb_differentiate_order_layaway) {
            options.push({
                id: "order",
                label: _t("Order"),
                item: { type: "order", confirm: true, with_down_payment: false },
            });
            options.push({
                id: "layaway",
                label: _t("Layaway"),
                item: { type: "layaway", confirm: true, with_down_payment: true },
            });
        } else {
            options.push({
                id: "order_layaway",
                label: _t("Order / Layaway"),
                item: { type: "order_layaway", confirm: true, with_down_payment: false },
            });
        }

        // Honor xb_default_so_state by pre-highlighting the matching entry:
        // "draft" -> Quotation (if offered); "sale" -> first confirmed option.
        const wantDraft = config.xb_default_so_state === "draft";
        const firstConfirmed = options.find((o) => o.item.confirm);
        for (const opt of options) {
            opt.isSelected = wantDraft
                ? opt.id === "quotation"
                : opt === firstConfirmed;
        }
        if (!options.some((o) => o.isSelected) && options.length) {
            options[0].isSelected = true;
        }

        return options;
    },

    /**
     * Conservatively drop integration metadata from a POS line customer note.
     * In this deployment line.customer_note is auto-filled with bin/product tags
     * like "[B3] articulo_mb=3SJ041 solo_metal variante_unica". If the text starts
     * with a "[B<n>]" bin tag AND also carries one of the integration markers
     * (articulo_mb=, sintetica/sin_codigo, OBSERV:), it is pure metadata and we
     * return "". Otherwise the text is returned unchanged (no mixed-case trimming
     * in this pass), so genuine cashier notes pass through intact.
     */
    xbSanitizeCustomerNote(txt) {
        const text = txt || "";
        const hasBinTag = /^\s*\[B\d+\]/.test(text);
        const hasMarker =
            text.includes("articulo_mb=") ||
            text.includes("sintetica/sin_codigo") ||
            text.includes("OBSERV:");
        return hasBinTag && hasMarker ? "" : text;
    },

    /**
     * Build the backend payload from the current order, forcing the EXACT POS
     * taxes (already mapped by the fiscal position) for 1:1 parity. The POS line
     * stores the unmapped taxes, so we map them here exactly as the POS does.
     */
    xbBuildOrderPayload(order) {
        const fp = order.fiscal_position_id;
        const lines = order.getOrderlines().map((line) => {
            const baseTaxes = line.tax_ids || [];
            const mappedTaxes = fp ? fp.getTaxesAfterFiscalPosition(baseTaxes) : baseTaxes;
            return {
                product_id: line.product_id.id,
                qty: line.getQuantity(),
                // price_unit is tax-EXCLUDED in POS, same as sale.order.line.
                price_unit: line.price_unit,
                discount: line.getDiscount(),
                tax_ids: mappedTaxes.map((tax) => tax.id),
                // Per-line customer note: flatten via getStrNotes, then strip the
                // integration metadata ("[B<n>] articulo_mb=...") with the
                // conservative xbSanitizeCustomerNote(). The backend writes
                // xb_customer_note only when the result is non-empty.
                customer_note: this.xbSanitizeCustomerNote(
                    this.pos.getStrNotes(line.customer_note)
                ),
                // Per-line internal note: line.note is JSON [{text, colorIndex}],
                // flattened via the native getStrNotes helper. Unchanged.
                internal_note: this.pos.getStrNotes(line.note) || "",
            };
        });

        return {
            pos_config_id: this.pos.config.id,
            partner_id: order.getPartner().id,
            pricelist_id: order.pricelist_id ? order.pricelist_id.id : false,
            fiscal_position_id: fp ? fp.id : false,
            // POS order notes, read here synchronously like the rest of the
            // payload. The backend writes each to its SO field only when non-empty.
            // - general_customer_note is plain text -> sale.order.note.
            // - internal_note is stored as JSON [{text, colorIndex}]; we reuse the
            //   native store helper getStrNotes() to extract clean text (it parses
            //   the JSON / color tags exactly as the POS displays it) ->
            //   sale.order.internal_note.
            note: order.general_customer_note || "",
            internal_note: this.pos.getStrNotes(order.internal_note) || "",
            lines,
            // Live tax-included grand total. order.amount_total is only set in
            // setOrderPrices() (on push to backend), so it can be stale here; we
            // compute it the same way: currency.round(priceIncl).
            amount_total: order.currency.round(order.priceIncl),
        };
    },

    async xbClickCreateSaleOrder() {
        const order = this.pos.getOrder();
        if (!order) {
            return;
        }

        if (!order.getPartner()) {
            this.dialog.add(AlertDialog, {
                title: _t("Missing customer"),
                body: _t("Select a customer before creating the order."),
            });
            return;
        }

        if (!order.getOrderlines().length) {
            this.dialog.add(AlertDialog, {
                title: _t("Empty order"),
                body: _t("Add at least one product before creating the order."),
            });
            return;
        }

        // Bug 1 fix: read ALL reactive state synchronously and build a PLAIN
        // payload BEFORE opening any popup. Clicking our button inside the "More"
        // actions popup makes that popup close and DESTROY this component while we
        // are still awaiting the SelectionPopup below; past the await we must
        // touch only plain data + the POS store (never this.orm/this.dialog,
        // which are component-bound services).
        const basePayload = this.xbBuildOrderPayload(order);

        // Choose the order type. Skip the popup when there is a single option.
        const options = this.xbGetOrderTypeOptions();
        let choice;
        if (options.length === 1) {
            choice = options[0].item;
        } else {
            choice = await makeAwaitable(this.dialog, SelectionPopup, {
                title: _t("Create from POS"),
                list: options,
            });
            if (!choice) {
                return;
            }
        }

        // `choice` is a plain object; merge its flags into the plain payload and
        // hand off to the POS store, which outlives this (possibly already
        // destroyed) button component. Down-payment pre-check + orm.call +
        // notification all live there for the same lifecycle-safety reason.
        await this.pos.xbCreateOrderFromPos({
            ...basePayload,
            type: choice.type,
            confirm: choice.confirm,
            with_down_payment: choice.with_down_payment,
        });
    },
});

patch(PosStore.prototype, {
    /**
     * Create the Sale Order from a fully-plain POS payload. Deliberately lives on
     * the POS store, NOT on the ControlButtons component: the "More" actions popup
     * closes on click and destroys the button while this work is still async, so
     * running orm.call / notification / dialog on the component would raise
     * "Component is destroyed". The store outlives the POS session.
     *
     * @param {Object} payload Plain, already-serialized data (no reactive refs).
     */
    async xbCreateOrderFromPos(payload) {
        // Bug 2 fix: the down-payment product may have available_in_pos = false,
        // so it is NOT loaded as a resolved record in the frontend and
        // this.config.down_payment_product_id would read empty even when it is
        // set. Pre-check the RAW foreign-key id instead. The backend guard
        // (sale.order.xb_create_order_from_pos) remains the authority.
        if (payload.with_down_payment && !this.config.raw.down_payment_product_id) {
            this.dialog.add(AlertDialog, {
                title: _t("Down-payment product missing"),
                body: _t(
                    "To register a layaway advance, set the down-payment product first:\n" +
                        "Point of Sale ▸ Settings ▸ this POS ▸ Down Payment Product."
                ),
            });
            return;
        }

        try {
            const result = await this.env.services.orm.call(
                "sale.order",
                "xb_create_order_from_pos",
                [payload]
            );
            this.notification.add(_t("%s created from POS.", result.name), {
                type: "success",
            });
            // [Phase 3] Stash the SO totals + portal URL on the order uiState so the
            // receipt can show Total / Down payment / Balance and the online link,
            // even though this pos.order is NOT natively linked to the SO (we create
            // it directly in the backend, no sale_order_origin_id line).
            const createdOnOrder = this.getOrder();
            if (createdOnOrder) {
                createdOnOrder.uiState.xbSaleOrder = {
                    sale_order_id: result.sale_order_id,
                    name: result.name,
                    amount_total: result.amount_total,
                    amount_unpaid: result.amount_unpaid,
                    portal_url: result.portal_url,
                    partner_ref: result.partner_ref,
                    type: payload.type,
                };
                // Reuse the native receipt printer. Gated by the per-POS toggle
                // xb_autoprint_on_create (configurable, INDEPENDENT of
                // iface_print_auto). Awaited so the receipt renders from the INTACT
                // cart before any quotation discard below. The native ReceiptScreen
                // is intentionally not used: it is gated to finalized/synced orders,
                // which this unpaid cart is not.
                if (this.config.xb_autoprint_on_create) {
                    // Hardened: a receipt-render failure during autoprint must NEVER
                    // abort the flow or take down the POS. The Sale Order is already
                    // created; if the print fails we log it and carry on (the cashier
                    // can reprint). Catches both rejected promises and render errors
                    // surfaced through the print pipeline.
                    try {
                        await this.printReceipt({ order: createdOnOrder });
                    } catch (printErr) {
                        console.warn("[xb] autoprint failed (order already created):", printErr);
                    }
                }
            }
            // Discard the consumed cart for ALL three types and open a fresh empty
            // one (after the receipt has been printed above). Keeping the cart for
            // Order/Layaway double-charged when later adding the advance; the advance
            // is collected by recovering the SO via the native flow in Phase 4. We
            // DELETE the consumed order (native removeOrder, local-only) instead of
            // only addNewOrder(), otherwise it lingers as an accumulating floating
            // tab.
            const consumed = this.getOrder();
            this.addNewOrder();
            if (consumed) {
                this.removeOrder(consumed, false);
            }
            // Phase 4 will add: advance (down-payment) collection at the POS.
        } catch (error) {
            // UserError messages raised by the backend surface here.
            const message =
                error?.data?.message || error?.message || _t("Could not create the order.");
            this.dialog.add(AlertDialog, {
                title: _t("Could not create the order"),
                body: message,
            });
        }
    },
});
