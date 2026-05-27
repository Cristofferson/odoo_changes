# -*- coding: utf-8 -*-
import logging
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class XbWishActivity(models.Model):
    """Activity to be automatically scheduled when a reminder fires.

    For each Reminder Type the user can configure one or several
    activities (Call, Email, To-do, custom...) that will be created on
    the responsible user the day of the event, with native Odoo
    notifications (bell + "My Activities" dashboard).
    """
    _name = "xb.wish.activity"
    _description = "Special Date Auto-Activity"
    _order = "wish_type_id, sequence, id"

    wish_type_id = fields.Many2one(
        comodel_name="xb.wish.type",
        string="Reminder Type",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    activity_type_id = fields.Many2one(
        comodel_name="mail.activity.type",
        string="Activity Type",
        required=True,
        ondelete="restrict",
        help="Any activity type (Call, Email, To-do, Meeting, ...).",
    )
    summary = fields.Char(
        string="Summary",
        translate=True,
        help="Short title for the activity. If empty, the activity type name is used.",
    )
    note = fields.Html(
        string="Note",
        translate=True,
        help="HTML description shown inside the activity card.",
    )
    user_field = fields.Selection(
        selection=[
            ("salesperson", "Customer's Salesperson"),
            ("creator", "Creator of the reminder"),
            ("fixed", "Always this user"),
            ("current", "User running the cron"),
        ],
        string="Assign To",
        default="salesperson",
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Fixed User",
        help="Used only when 'Assign To' is set to 'Always this user'.",
    )
    delay_count = fields.Integer(
        string="Schedule Offset",
        default=0,
        help="Number of days relative to the reminder date.",
    )
    delay_direction = fields.Selection(
        selection=[
            ("before", "Before"),
            ("on", "On the day"),
            ("after", "After"),
        ],
        string="Direction",
        default="on",
        required=True,
    )

    # ------------------------------------------------------------------
    # Public API used by the cron
    # ------------------------------------------------------------------
    def _matches_today(self, reminder, today=None):
        self.ensure_one()
        if not self.active:
            return False
        today = today or fields.Date.context_today(self)
        target = self._compute_target_date(reminder, today=today)
        return target == today

    def _compute_target_date(self, reminder, today=None):
        self.ensure_one()
        anchor = reminder._next_occurrence(today=today)
        if not anchor:
            return False
        if self.delay_direction == "on" or self.delay_count == 0:
            return anchor
        delta = relativedelta(days=abs(self.delay_count))
        if self.delay_direction == "before":
            return anchor - delta
        return anchor + delta

    def _resolve_user(self, reminder):
        self.ensure_one()
        if self.user_field == "fixed":
            return self.user_id
        if self.user_field == "creator":
            return reminder.create_uid or self.env.user
        if self.user_field == "current":
            return self.env.user
        # salesperson
        partner = reminder.partner_id
        if partner and partner.user_id:
            return partner.user_id
        return self.env.user

    def _schedule(self, reminder):
        """Create the mail.activity record on the partner."""
        self.ensure_one()
        partner = reminder.partner_id
        if not partner:
            return False
        user = self._resolve_user(reminder)
        if not user:
            return False
        try:
            date_deadline = self._compute_target_date(reminder) or fields.Date.context_today(self)
            self.env["mail.activity"].sudo().create({
                "activity_type_id": self.activity_type_id.id,
                "summary": self.summary or self.activity_type_id.name,
                "note": self.note or False,
                "date_deadline": date_deadline,
                "user_id": user.id,
                "res_model_id": self.env["ir.model"]._get("res.partner").id,
                "res_model": "res.partner",
                "res_id": partner.id,
            })
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Special Dates auto-activity %s failed: %s", self.id, exc
            )
            return False

    @api.depends("activity_type_id", "summary", "delay_count", "delay_direction")
    def _compute_display_name(self):
        for rec in self:
            atype = rec.activity_type_id.name or "?"
            base = rec.summary or atype
            if rec.delay_direction == "on":
                when = _("on the day")
            else:
                when = "%s d %s" % (abs(rec.delay_count), rec.delay_direction)
            rec.display_name = "%s · %s" % (base, when)
