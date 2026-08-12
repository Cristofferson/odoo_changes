/** @odoo-module **/

/**
 * Auto-refresh for a content plan while the AI queue drains.
 *
 * Generation happens in a cron, so the form a user is staring at after
 * clicking "Generate" is a snapshot that never changes on its own — which
 * reads as "nothing happened". This widget reloads the record every few
 * seconds for exactly as long as the plan is generating, and stops the moment
 * it is not. It renders nothing.
 */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { Component, onWillDestroy } from "@odoo/owl";

const REFRESH_MS = 8000;

export class PlanAutoRefresh extends Component {
    static template = "xb_social_ai_planner.PlanAutoRefresh";
    static props = { ...standardFieldProps };

    setup() {
        this.timer = null;
        useRecordObserver((record) => {
            if (record.data[this.props.name]) {
                this.start();
            } else {
                this.stop();
            }
        });
        onWillDestroy(() => this.stop());
    }

    start() {
        if (this.timer) {
            return;
        }
        this.timer = setInterval(async () => {
            const record = this.props.record;
            // Never fight the user: reloading a form with unsaved edits would
            // throw their work away.
            if (record.dirty || record.isNew) {
                return;
            }
            await record.model.root.load();
        }, REFRESH_MS);
    }

    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }
}

export const planAutoRefresh = {
    component: PlanAutoRefresh,
    supportedTypes: ["boolean"],
};

registry.category("fields").add("xb_plan_autorefresh", planAutoRefresh);
