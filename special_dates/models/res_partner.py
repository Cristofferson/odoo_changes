# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    xb_wish_line = fields.One2many(
        comodel_name="xb.wish.reminders",
        inverse_name="partner_id",
        string="Special Dates",
    )
    xb_wish_count = fields.Integer(
        string="Special Dates Count",
        compute="_compute_xb_wish_count",
    )

    @api.depends("xb_wish_line")
    def _compute_xb_wish_count(self):
        for partner in self:
            partner.xb_wish_count = len(partner.xb_wish_line)

    # ------------------------------------------------------------------
    # POS popup helper - called via RPC, NOT loaded with partner data
    # ------------------------------------------------------------------
    def _get_due_pos_reminders(self, today=None):
        """Return reminder records of `self` that are due TODAY and whose
        type is flagged as `show_in_pos`. Used by the in-cashier popup."""
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        due = []
        for line in self.xb_wish_line:
            if not line.active or not line.wish_type:
                continue
            if not line.wish_type.show_in_pos:
                continue
            occ = line._next_occurrence(today=today)
            if occ == today:
                due.append({
                    "id": line.id,
                    "wish_type_name": line.wish_type.name,
                    "icon": line.wish_type.icon or "🎉",
                    "note": line.note or "",
                })
        return due

    def get_pos_reminder_data(self):
        """RPC-callable: returns due-today reminders for this partner."""
        self.ensure_one()
        return self._get_due_pos_reminders()

    @api.model
    def get_today_pos_reminders(self):
        """RPC: list of every partner with a special date due today.
        Used by the POS welcome popup. Also returns the popup interval
        configured for periodic re-display.

        Returns:
            {
              "date": "YYYY-MM-DD",
              "count": int,
              "items": [{partner_id, partner_name, image_128, reminders}],
              "interval_hours": int
            }
        """
        today = fields.Date.context_today(self)
        # Iterate over ALL active reminders and group by partner.
        # We do NOT filter the partners up-front by their wish_type's
        # show_in_pos flag because the structure of the search domain
        # was misleading - each pair of conditions must match the SAME
        # line, but Odoo's auto-join doesn't always honour that.
        Reminders = self.env["xb.wish.reminders"].sudo()
        all_reminders = Reminders.search([("active", "=", True)])
        _logger.info(
            "[special_dates] get_today_pos_reminders: today=%s scanning %d reminders",
            today, len(all_reminders)
        )
        by_partner = {}
        for reminder in all_reminders:
            wtype = reminder.wish_type
            if not wtype or not wtype.show_in_pos:
                continue
            try:
                nxt = reminder._next_occurrence(today=today)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "[special_dates] _next_occurrence failed for %s: %s",
                    reminder.id, exc
                )
                continue
            if not nxt or nxt != today:
                continue
            partner = reminder.partner_id
            if not partner:
                continue
            entry = by_partner.setdefault(partner.id, {
                "partner_id": partner.id,
                "partner_name": partner.display_name,
                "image_128": "/web/image/res.partner/%s/image_128" % partner.id,
                "reminders": [],
            })
            entry["reminders"].append({
                "id": reminder.id,
                "wish_type_name": wtype.name,
                "icon": wtype.icon or "🎉",
                "note": "",
            })
        result = sorted(
            by_partner.values(),
            key=lambda r: (r["partner_name"] or "").lower(),
        )
        _logger.info(
            "[special_dates] get_today_pos_reminders: matched %d partners",
            len(result)
        )
        ICP = self.env["ir.config_parameter"].sudo()
        try:
            interval = int(
                ICP.get_param("special_dates.pos_popup_interval_hours", "3")
            )
        except (TypeError, ValueError):
            interval = 3
        if interval < 0:
            interval = 0
        return {
            "date": today.isoformat(),
            "count": len(result),
            "items": result,
            "interval_hours": interval,
        }
