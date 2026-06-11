# -*- coding: utf-8 -*-
import logging
from datetime import date as _date
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class XbWishReminders(models.Model):
    _name = "xb.wish.reminders"
    _description = "Special Date Reminder"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "display_name"
    _order = "date desc, id desc"

    wish_type = fields.Many2one(
        comodel_name="xb.wish.type",
        string="Reminder Type",
        required=True,
        ondelete="restrict",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer / Contact",
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
    )
    date = fields.Date(string="Reminder Date")
    period_type = fields.Selection(
        selection=[
            ("day", "Day of the Week"),
            ("no_of_day", "Every N Days"),
            ("year", "Every Year (anniversary)"),
        ],
        default="year",
        string="Period",
        required=True,
    )
    day_type = fields.Selection(
        selection=[
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        default="0",
        string="Day",
    )
    no_of_day = fields.Integer(string="Number of Days")
    last_wished_date = fields.Date(string="Last Sent", readonly=True)
    active = fields.Boolean(string="Active", default=True)
    display_name = fields.Char(
        string="Display Name", compute="_compute_display_name", store=True
    )
    is_due_today = fields.Boolean(
        string="Due Today",
        compute="_compute_is_due_today",
        search="_search_is_due_today",
        help="True when this reminder's next occurrence is today.",
    )
    next_occurrence_date = fields.Date(
        string="Next Occurrence",
        compute="_compute_next_occurrence_date",
        help="The next date on which this reminder will trigger. "
             "For yearly anniversaries, this is the upcoming birthday/anniversary.",
    )

    def _compute_next_occurrence_date(self):
        """Visible field for the user: the next FUTURE occurrence.
        If the reminder is due today, this returns next year's date
        (not today). For the internal cron logic we keep using
        _next_occurrence directly, which returns today if due today.
        """
        today = fields.Date.context_today(self)
        for rec in self:
            try:
                nxt = rec._next_occurrence(today=today)
                if nxt and nxt == today:
                    # Get the occurrence AFTER today.
                    tomorrow = today + relativedelta(days=1)
                    nxt = rec._next_occurrence(today=tomorrow)
                rec.next_occurrence_date = nxt if nxt else False
            except Exception:  # noqa: BLE001
                rec.next_occurrence_date = False

    # --- Today's communication status -----------------------------------
    today_comm_total = fields.Integer(
        string="Communications Today",
        compute="_compute_today_status",
        help="How many scheduled communications (Email/SMS/WhatsApp) "
             "this reminder has for today.",
    )
    today_comm_sent = fields.Integer(
        string="Communications Sent",
        compute="_compute_today_status",
        help="How many of today's scheduled communications have already been sent.",
    )
    today_comm_status = fields.Char(
        string="Comms Status",
        compute="_compute_today_status",
        help="Quick summary: ✓ all sent · ⏳ pending · — none scheduled.",
    )

    # --- Today's activity status ----------------------------------------
    today_activity_total = fields.Integer(
        string="Activities Today",
        compute="_compute_today_status",
        help="How many auto-activities this reminder has scheduled for today.",
    )
    today_activity_done = fields.Integer(
        string="Activities Done",
        compute="_compute_today_status",
        help="How many of today's auto-activities have been marked as done.",
    )
    today_activity_status = fields.Char(
        string="Activities Status",
        compute="_compute_today_status",
        help="Quick summary of today's auto-activities.",
    )

    def _compute_today_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            comm_total = 0
            comm_sent = 0
            act_total = 0
            act_done = 0
            wtype = rec.wish_type
            if wtype:
                # --- Communications scheduled for today ---
                for line in wtype.schedule_ids.filtered("active"):
                    if line._matches_today(rec, today=today):
                        comm_total += 1
                        # Was it sent today?
                        if line.last_sent and \
                                fields.Datetime.context_timestamp(line, line.last_sent).date() == today:
                            comm_sent += 1
                # --- Auto-activities pinned to this reminder ---
                acts = self.env["mail.activity"].sudo().search([
                    ("res_model", "=", "xb.wish.reminders"),
                    ("res_id", "=", rec.id),
                ])
                done_acts = self.env["mail.message"].sudo().search([
                    ("model", "=", "xb.wish.reminders"),
                    ("res_id", "=", rec.id),
                    ("mail_activity_type_id", "!=", False),
                    ("date", ">=", fields.Datetime.to_string(
                        fields.Datetime.now().replace(hour=0, minute=0, second=0)
                    )),
                ])
                # We approximate planned-for-today activities by counting
                # any open activity due today or earlier (overdue) plus
                # completed-today entries from the chatter.
                for a in acts:
                    if a.date_deadline and a.date_deadline <= today:
                        act_total += 1
                act_total += len(done_acts)
                act_done = len(done_acts)

            rec.today_comm_total = comm_total
            rec.today_comm_sent = comm_sent
            if comm_total == 0:
                rec.today_comm_status = "—"
            elif comm_sent >= comm_total:
                rec.today_comm_status = "✓ %d/%d sent" % (comm_sent, comm_total)
            else:
                rec.today_comm_status = "⏳ %d/%d sent" % (comm_sent, comm_total)

            rec.today_activity_total = act_total
            rec.today_activity_done = act_done
            if act_total == 0:
                rec.today_activity_status = "—"
            elif act_done >= act_total:
                rec.today_activity_status = "✓ %d/%d done" % (act_done, act_total)
            else:
                rec.today_activity_status = "⏳ %d/%d done" % (act_done, act_total)

    def _compute_is_due_today(self):
        today = fields.Date.context_today(self)
        _logger.info("[special_dates] _compute_is_due_today called, today=%s, records=%s", today, self.ids)
        for rec in self:
            try:
                nxt = rec._next_occurrence(today=today)
                rec.is_due_today = bool(nxt) and nxt == today
                _logger.info(
                    "[special_dates]   rec %s: date=%s period=%s nxt=%s is_due=%s",
                    rec.id, rec.date, rec.period_type, nxt, rec.is_due_today
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("[special_dates] compute_is_due_today failed for %s: %s", rec.id, exc)
                rec.is_due_today = False

    def _search_is_due_today(self, operator, value):
        """Search method for the computed boolean.
        Materialises all active candidates and filters in Python.
        """
        today = fields.Date.context_today(self)
        _logger.info(
            "[special_dates] _search_is_due_today called: operator=%r value=%r today=%s",
            operator, value, today
        )
        candidates = self.sudo().with_context(
            active_test=False
        ).search([("active", "=", True)])
        _logger.info("[special_dates]   candidates count=%s ids=%s", len(candidates), candidates.ids)
        matched_ids = []
        for rec in candidates:
            try:
                nxt = rec._next_occurrence(today=today)
                if nxt and nxt == today:
                    matched_ids.append(rec.id)
                    _logger.info(
                        "[special_dates]   MATCH rec %s: date=%s nxt=%s",
                        rec.id, rec.date, nxt
                    )
                else:
                    _logger.info(
                        "[special_dates]   no-match rec %s: date=%s period=%s nxt=%s (today=%s)",
                        rec.id, rec.date, rec.period_type, nxt, today
                    )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("[special_dates] search loop failed for %s: %s", rec.id, exc)
                continue
        is_true_match = (operator in ("=", "==") and bool(value)) or \
                        (operator in ("!=",) and not bool(value))
        _logger.info(
            "[special_dates]   returning matched_ids=%s (is_true_match=%s)",
            matched_ids, is_true_match
        )
        if is_true_match:
            return [("id", "in", matched_ids)]
        return [("id", "not in", matched_ids)]

    @api.model
    def action_open_today_reminders(self):
        """Server-action entry: build a plain id-list domain in Python
        and open the standard list view filtered to today's due
        reminders. Avoids relying on a computed-search round-trip."""
        today = fields.Date.context_today(self)
        matched_ids = []
        for rec in self.sudo().search([("active", "=", True)]):
            try:
                nxt = rec._next_occurrence(today=today)
                if nxt and nxt == today:
                    matched_ids.append(rec.id)
            except Exception:  # noqa: BLE001
                continue
        _logger.info(
            "[special_dates] action_open_today_reminders: today=%s matched=%s",
            today, matched_ids
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Today's Reminders"),
            "res_model": "xb.wish.reminders",
            "view_mode": "list,form",
            "domain": [("id", "in", matched_ids)],
            "context": {"create": False},
            "target": "current",
        }

    @api.depends("wish_type", "partner_id")
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.wish_type:
                parts.append(rec.wish_type.name)
            if rec.partner_id:
                parts.append(rec.partner_id.display_name)
            rec.display_name = " - ".join(parts) or _("New Reminder")

    @api.onchange("wish_type")
    def _onchange_wish_type(self):
        if self.wish_type:
            self.period_type = self.wish_type.period_type
            self.day_type = self.wish_type.day_type
            self.no_of_day = self.wish_type.no_of_day
            self.date = self.wish_type.date

    # ------------------------------------------------------------------
    # Date arithmetic
    # ------------------------------------------------------------------
    def _next_occurrence(self, today=None):
        """Return the *next* date on which this reminder occurs, or
        today if it falls today. Used as the anchor for schedule lines
        and auto-activities.
        """
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        if self.period_type == "year":
            if not self.date:
                return False
            try:
                this_year = _date(today.year, self.date.month, self.date.day)
            except ValueError:
                # e.g. Feb 29 on non-leap years -> shift to Feb 28
                this_year = _date(today.year, self.date.month, 28)
            if this_year >= today:
                return this_year
            try:
                return _date(today.year + 1, self.date.month, self.date.day)
            except ValueError:
                return _date(today.year + 1, self.date.month, 28)
        if self.period_type == "day":
            if self.day_type in (False, None):
                return False
            try:
                target = int(self.day_type)
            except (TypeError, ValueError):
                return False
            offset = (target - today.weekday()) % 7
            return today + relativedelta(days=offset)
        if self.period_type == "no_of_day":
            if not self.no_of_day:
                return False
            if not self.last_wished_date:
                return today
            nxt = self.last_wished_date + relativedelta(days=self.no_of_day)
            if nxt < today:
                return today
            return nxt
        return False

    def _is_due_today(self, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        nxt = self._next_occurrence(today=today)
        return bool(nxt) and nxt == today

    # ------------------------------------------------------------------
    # Cron entry-point
    # ------------------------------------------------------------------
    @api.model
    def cron_send_date_reminders(self):
        """Process schedule lines and auto-activities for every active
        reminder. A schedule fires on its computed target date; an
        auto-activity is created when its offset lands today.
        Also rebuilds the "today" board for due reminders.
        """
        today_model = self.env["xb.wish.reminders.today"].sudo()
        today_model.search([]).unlink()
        today = fields.Date.context_today(self)
        reminders = self.sudo().search([("active", "=", True)])

        for reminder in reminders:
            try:
                wtype = reminder.wish_type
                if not wtype:
                    continue
                fired_any = False
                # --- Schedule lines (channels) ----------------------
                for line in wtype.schedule_ids.filtered("active"):
                    if line._matches_today(reminder, today=today):
                        if line._send(reminder):
                            fired_any = True
                # --- Auto-activities --------------------------------
                for act in wtype.activity_ids.filtered("active"):
                    if act._matches_today(reminder, today=today):
                        act._schedule(reminder)
                        fired_any = True
                # --- "today" board mirror ---------------------------
                if reminder._is_due_today(today=today):
                    reminder.last_wished_date = today
                    today_model.create({
                        "wish_type": wtype.id,
                        "partner_id": reminder.partner_id.id or False,
                        "date": reminder.date or False,
                        "period_type": reminder.period_type,
                        "day_type": reminder.day_type,
                        "no_of_day": reminder.no_of_day,
                        "company_id": reminder.company_id.id,
                    })
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Special Dates reminder %s failed: %s", reminder.id, exc
                )
        return True

    # ------------------------------------------------------------------
    # POS integration - RPC endpoints
    # ------------------------------------------------------------------
    @api.model
    def get_pos_capture_config(self):
        """Return the list of POS categories that trigger special date
        capture, paired with their target wish type.

        Called once by the POS frontend at session load. The shape:
            [
                {
                    "pos_category_id": 12,
                    "wish_type_id": 1,
                    "wish_type_name": "Aniversario de bodas",
                    "wish_type_icon": "💕",
                },
                ...
            ]
        """
        cats = self.env["pos.category"].sudo().search([
            ("xb_triggers_wish_type_id", "!=", False),
            ("xb_triggers_wish_type_id.active", "=", True),
            ("xb_triggers_wish_type_id.xb_pos_auto_capture", "=", True),
        ])
        result = []
        for cat in cats:
            wt = cat.xb_triggers_wish_type_id
            result.append({
                "pos_category_id": cat.id,
                "wish_type_id": wt.id,
                "wish_type_name": wt.name,
                "wish_type_icon": wt.icon or "🎉",
            })
        return result

    @api.model
    def check_existing_for_capture(self, partner_id, wish_type_id):
        """Anti-duplicate check used by the POS popup.

        Returns True if the customer ALREADY has an active reminder of
        this wish type whose date falls within the next 90 days. In that
        case the POS frontend will skip showing the capture popup.

        Returns False if the popup should be shown (no clash).
        """
        if not partner_id or not wish_type_id:
            return False
        today = fields.Date.context_today(self)
        horizon = today + relativedelta(days=90)
        existing = self.sudo().search([
            ("partner_id", "=", partner_id),
            ("wish_type", "=", wish_type_id),
            ("active", "=", True),
            ("date", ">=", today),
            ("date", "<=", horizon),
        ], limit=1)
        return bool(existing)

    @api.model
    def create_from_pos(self, partner_id, wish_type_id, event_date,
                       pos_order_ref=None):
        """Create a reminder from the POS capture popup.

        Inherits period_type and other defaults from the wish type.
        Adds a chatter message linking back to the POS order.

        Args:
            partner_id (int): res.partner.id of the customer.
            wish_type_id (int): xb.wish.type.id to use.
            event_date (str): ISO date 'YYYY-MM-DD' of the event.
            pos_order_ref (str, optional): POS order reference for audit.

        Returns:
            dict with id and display_name of the created record, or
            {"error": "..."} if validation fails.
        """
        if not partner_id or not wish_type_id or not event_date:
            return {"error": _("Missing required data.")}

        wish_type = self.env["xb.wish.type"].sudo().browse(wish_type_id)
        if not wish_type.exists():
            return {"error": _("Reminder type not found.")}

        partner = self.env["res.partner"].sudo().browse(partner_id)
        if not partner.exists():
            return {"error": _("Customer not found.")}

        # Safety: re-run the duplicate check server-side so the frontend
        # can't bypass it by sending a stale state.
        if self.check_existing_for_capture(partner_id, wish_type_id):
            return {
                "skipped": True,
                "reason": _(
                    "%(partner)s already has an active %(type)s reminder "
                    "within the next 90 days."
                ) % {"partner": partner.display_name, "type": wish_type.name},
            }

        vals = {
            "wish_type": wish_type.id,
            "partner_id": partner.id,
            "date": event_date,
            "period_type": wish_type.period_type,
            "active": True,
        }
        # Inherit weekday / N-days defaults from the wish type when relevant.
        if wish_type.period_type == "day" and wish_type.day_type:
            vals["day_type"] = wish_type.day_type
        if wish_type.period_type == "no_of_day" and wish_type.no_of_day:
            vals["no_of_day"] = wish_type.no_of_day

        reminder = self.sudo().create(vals)

        # Audit trail in the chatter
        ref_txt = " %s" % pos_order_ref if pos_order_ref else ""
        reminder.message_post(
            body=_(
                "Reminder created from Point of Sale%(ref)s by %(user)s."
            ) % {"ref": ref_txt, "user": self.env.user.display_name},
            subtype_xmlid="mail.mt_note",
        )

        return {
            "id": reminder.id,
            "display_name": reminder.display_name,
            "wish_type_name": wish_type.name,
            "wish_type_icon": wish_type.icon or "🎉",
            "date": event_date,
        }
