# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class XbWishType(models.Model):
    _name = "xb.wish.type"
    _description = "Special Date Type"
    _order = "name"

    @api.model
    def _register_hook(self):
        """Auto-reload Spanish translations every time the module is
        loaded (install, upgrade, or server restart).

        This makes the module behave correctly for end users: they
        install/upgrade and translations appear without any manual
        step. The check is cheap (single sudo flag in DB) and the
        TranslationImporter is idempotent."""
        res = super()._register_hook()
        try:
            from odoo import api as _api
            from odoo.modules import get_module_path
            from odoo.tools.translate import TranslationImporter

            with self.env.registry.cursor() as cr:
                env = _api.Environment(cr, 1, {})  # 1 = SUPERUSER_ID
                module_path = get_module_path("special_dates")
                if not module_path:
                    return res
                lang_obj = env["res.lang"].with_context(active_test=False)
                target_langs = []
                for code in ("es_MX", "es"):
                    lang = lang_obj.search([("code", "=", code)], limit=1)
                    if not lang:
                        continue
                    if not lang.active:
                        lang.sudo().active = True
                    target_langs.append(code)
                if not target_langs:
                    return res
                importer = TranslationImporter(cr, verbose=False)
                loaded = 0
                for code in target_langs:
                    po_path = "%s/i18n/%s.po" % (module_path, code)
                    import os as _os
                    if _os.path.exists(po_path):
                        importer.load_file(po_path, code)
                        loaded += 1
                if loaded:
                    importer.save(overwrite=True)
                    import logging as _l
                    _l.getLogger(__name__).info(
                        "[special_dates] _register_hook: reloaded %d "
                        ".po file(s) with overwrite=True", loaded
                    )
        except Exception:  # noqa: BLE001
            # Never let the translation reload block module loading.
            pass
        return res

    name = fields.Char(string="Name", required=True, translate=True)
    active = fields.Boolean(string="Active", default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
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
        string="Default Day",
    )
    no_of_day = fields.Integer(string="Default Number of Days")
    date = fields.Date(string="Default Date")
    color = fields.Integer(string="Color Index")
    show_in_pos = fields.Boolean(
        string="Show Popup in Point of Sale",
        default=True,
        help="When enabled, this reminder type can trigger a celebratory "
             "popup in the Point of Sale on its date. Uncheck to silence "
             "this type from the POS without disabling it for emails, SMS, "
             "or auto-activities.",
    )
    icon = fields.Selection(
        selection=[
            ("🎉", "🎉 Celebration"),
            ("🎂", "🎂 Birthday"),
            ("🎁", "🎁 Gift"),
            ("💍", "💍 Wedding / Engagement"),
            ("💕", "💕 Love / Anniversary"),
            ("❤️", "❤️ Heart"),
            ("🌹", "🌹 Rose"),
            ("🥂", "🥂 Cheers"),
            ("🍾", "🍾 Champagne"),
            ("🎊", "🎊 Confetti"),
            ("🎈", "🎈 Balloon"),
            ("🌟", "🌟 Star"),
            ("⭐", "⭐ Star (yellow)"),
            ("✨", "✨ Sparkles"),
            ("🏆", "🏆 Trophy"),
            ("🥇", "🥇 Gold Medal"),
            ("👶", "👶 Baby"),
            ("👰", "👰 Bride"),
            ("🤵", "🤵 Groom"),
            ("🎓", "🎓 Graduation"),
            ("📅", "📅 Calendar"),
            ("🗓️", "🗓️ Date"),
            ("☀️", "☀️ Sun"),
            ("🌙", "🌙 Moon"),
            ("🎄", "🎄 Christmas"),
            ("🦃", "🦃 Thanksgiving"),
            ("👑", "👑 Crown"),
            ("💎", "💎 Diamond"),
            ("🔔", "🔔 Bell"),
            ("⏰", "⏰ Reminder"),
        ],
        string="Icon",
        default="🎉",
        required=True,
        help="Emoji shown in the POS popup. Choose from the list.",
    )

    xb_pos_auto_capture = fields.Boolean(
        string="Capture at Point of Sale",
        default=False,
        help="When enabled, this Reminder Type can be captured at the "
             "Point of Sale: when a cashier sells a product whose POS "
             "category triggers this type, a popup asks to register the "
             "special date for the customer. Independent of "
             "'Show Popup in Point of Sale' (which controls the day-of "
             "celebratory popup).",
    )

    schedule_ids = fields.One2many(
        comodel_name="xb.wish.schedule",
        inverse_name="wish_type_id",
        string="Communications",
        copy=True,
    )
    schedule_count = fields.Integer(
        string="# Schedules", compute="_compute_schedule_count",
    )

    activity_ids = fields.One2many(
        comodel_name="xb.wish.activity",
        inverse_name="wish_type_id",
        string="Auto-Activities",
        copy=True,
        help="Activities (Call, Email, To-Do, ...) automatically "
             "created on the customer's record when this date arrives.",
    )
    activity_count = fields.Integer(
        string="# Activities", compute="_compute_activity_count",
    )

    @api.depends("schedule_ids")
    def _compute_schedule_count(self):
        for rec in self:
            rec.schedule_count = len(rec.schedule_ids)

    @api.depends("activity_ids")
    def _compute_activity_count(self):
        for rec in self:
            rec.activity_count = len(rec.activity_ids)

    @api.constrains("no_of_day")
    def _check_no_of_day(self):
        for rec in self:
            if rec.no_of_day and rec.no_of_day <= 0:
                raise ValidationError(
                    _("Number of days must be a positive integer.")
                )

    # ------------------------------------------------------------------
    # Manual trigger - useful for testing without waiting for the cron
    # ------------------------------------------------------------------
    def action_run_now(self):
        """Force the daily reminder cron to run now. Sends emails/SMS
        and creates activities for any reminder due today. Visible to
        managers as a button on the Reminder Type form."""
        self.env["xb.wish.reminders"].sudo().cron_send_date_reminders()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Special Dates"),
                "message": _("Daily reminders processed. Check the chatter "
                             "of due reminders to see what was sent."),
                "type": "success",
                "sticky": False,
            },
        }
