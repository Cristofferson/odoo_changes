# -*- coding: utf-8 -*-
import logging
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def _sms_available(env):
    return env["ir.module.module"].sudo().search_count(
        [("name", "=", "sms"), ("state", "=", "installed")]
    ) > 0


def _whatsapp_available(env):
    return env["ir.module.module"].sudo().search_count(
        [("name", "=", "whatsapp"), ("state", "=", "installed")]
    ) > 0


class XbWishSchedule(models.Model):
    """Communication schedule line attached to a Reminder Type.

    Mirrors the well-known ``event.mail`` pattern from the Events module:
    each line defines WHEN (interval + unit + reference point) and WHAT
    (channel + template) to send relative to the reminder date.
    """
    _name = "xb.wish.schedule"
    _description = "Special Date Communication Schedule"
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
    company_id = fields.Many2one(
        related="wish_type_id.company_id", store=True, readonly=True,
    )

    # ------------------------------------------------------------------
    # WHEN
    # ------------------------------------------------------------------
    interval_nbr = fields.Integer(string="Interval", default=1)
    interval_unit = fields.Selection(
        selection=[
            ("now", "Immediately"),
            ("hours", "Hours"),
            ("days", "Days"),
            ("weeks", "Weeks"),
            ("months", "Months"),
        ],
        string="Unit",
        default="days",
        required=True,
    )
    interval_type = fields.Selection(
        selection=[
            ("before_event", "Before the reminder date"),
            ("after_event", "After the reminder date"),
            ("on_event", "On the reminder date"),
        ],
        string="Trigger",
        default="before_event",
        required=True,
    )

    # ------------------------------------------------------------------
    # WHAT
    # ------------------------------------------------------------------
    channel = fields.Selection(
        selection="_get_channel_selection",
        string="Channel",
        default="mail",
        required=True,
    )
    mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Email Template",
        domain="[('model_id.model', '=', 'xb.wish.reminders')]",
    )
    sms_template_id = fields.Many2one(
        comodel_name="sms.template",
        string="SMS Template",
        domain="[('model', '=', 'xb.wish.reminders')]",
        ondelete="set null",
    )
    # whatsapp_template_id is added dynamically in
    # xb_wish_schedule_whatsapp.py if the whatsapp module is installed.

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    last_sent = fields.Datetime(string="Last Sent", readonly=True)
    sent_count = fields.Integer(string="Sent", readonly=True, default=0)
    note = fields.Char(string="Internal Note")

    # ------------------------------------------------------------------
    # Selection helper
    # ------------------------------------------------------------------
    @api.model
    def _get_channel_selection(self):
        sel = [("mail", "Email")]
        if _sms_available(self.env):
            sel.append(("sms", "SMS"))
        if _whatsapp_available(self.env):
            sel.append(("whatsapp", "WhatsApp"))
        return sel

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @api.constrains("channel", "mail_template_id", "sms_template_id")
    def _check_template(self):
        for line in self:
            if line.channel == "mail" and not line.mail_template_id:
                raise ValidationError(
                    _("Please pick an email template for line '%s'.") % (line.display_name,)
                )
            if line.channel == "sms" and not line.sms_template_id:
                raise ValidationError(
                    _("Please pick an SMS template for line '%s'.") % (line.display_name,)
                )
            if line.channel == "whatsapp" and not getattr(line, "whatsapp_template_id", False):
                raise ValidationError(
                    _("Please pick a WhatsApp template for line '%s'.") % (line.display_name,)
                )

    @api.constrains("interval_nbr", "interval_unit", "interval_type")
    def _check_interval(self):
        for line in self:
            if line.interval_unit != "now" and line.interval_nbr < 0:
                raise ValidationError(
                    _("Interval must be positive (or use 'Immediately').")
                )

    # ------------------------------------------------------------------
    # Public API used by the cron
    # ------------------------------------------------------------------
    def _matches_today(self, reminder, today=None):
        """Return True if this schedule line should fire today for the
        given reminder (a record of ``xb.wish.reminders``)."""
        self.ensure_one()
        if not self.active:
            return False
        today = today or fields.Date.context_today(self)
        target = self._compute_target_date(reminder, today=today)
        if not target:
            return False
        return target == today

    def _compute_target_date(self, reminder, today=None):
        """Compute the date on which this scheduled line should fire,
        taking the reminder's next occurrence as the anchor."""
        self.ensure_one()
        anchor = reminder._next_occurrence(today=today)
        if not anchor:
            return False
        if self.interval_unit == "now" or self.interval_type == "on_event":
            return anchor
        delta_kwargs = {self.interval_unit: self.interval_nbr}
        delta = relativedelta(**delta_kwargs)
        if self.interval_type == "before_event":
            return anchor - delta
        if self.interval_type == "after_event":
            return anchor + delta
        return anchor

    def _send(self, reminder):
        """Send this schedule line for ``reminder``. Errors are logged
        but never raised so the cron keeps processing other lines."""
        self.ensure_one()
        partner = reminder.partner_id
        if not partner:
            return False
        try:
            if self.channel == "mail":
                if not self.mail_template_id or not partner.email:
                    return False
                self.mail_template_id.sudo().send_mail(
                    reminder.id,
                    force_send=True,
                    email_values={
                        "email_to": partner.email,
                        "recipient_ids": [(6, 0, partner.ids)],
                    },
                )
            elif self.channel == "sms":
                if not self.sms_template_id or not partner.mobile and not partner.phone:
                    return False
                # _send_sms reads recipients from the record
                composer = self.env["sms.composer"].sudo().create({
                    "composition_mode": "comment",
                    "template_id": self.sms_template_id.id,
                    "res_model": "xb.wish.reminders",
                    "res_id": reminder.id,
                    "numbers": partner.mobile or partner.phone or "",
                })
                composer._action_send_sms()
            elif self.channel == "whatsapp":
                wa_template = getattr(self, "whatsapp_template_id", False)
                if not wa_template:
                    return False
                composer = self.env["whatsapp.composer"].sudo().create({
                    "wa_template_id": wa_template.id,
                    "res_model": "xb.wish.reminders",
                    "res_ids": str(reminder.id),
                    "phone": partner.mobile or partner.phone or "",
                })
                composer._send_whatsapp_template()
            else:
                return False
            self.sudo().write({
                "last_sent": fields.Datetime.now(),
                "sent_count": self.sent_count + 1,
            })
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "Special Dates schedule %s (channel=%s) failed: %s",
                self.id, self.channel, exc,
            )
            return False

    @api.depends("channel", "interval_nbr", "interval_unit", "interval_type")
    def _compute_display_name(self):
        labels = dict(self._fields["interval_type"].selection)
        units = dict(self._fields["interval_unit"].selection)
        chans = dict(self._fields["channel"].selection)
        for line in self:
            unit = units.get(line.interval_unit, line.interval_unit or "")
            ctype = labels.get(line.interval_type, line.interval_type or "")
            chan = chans.get(line.channel, line.channel or "")
            if line.interval_unit == "now":
                when = _("Immediately")
            else:
                when = "%s %s · %s" % (line.interval_nbr, unit, ctype)
            line.display_name = "%s — %s" % (chan, when)
