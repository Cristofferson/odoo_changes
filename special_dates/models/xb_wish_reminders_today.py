# -*- coding: utf-8 -*-
from odoo import fields, models


class XbWishRemindersToday(models.Model):
    _name = "xb.wish.reminders.today"
    _description = "Today's Special Dates"
    _order = "id desc"

    wish_type = fields.Many2one(
        comodel_name="xb.wish.type", string="Reminder Type"
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner", string="Customer / Contact"
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    date = fields.Date(string="Reminder Date")
    period_type = fields.Selection(
        selection=[
            ("day", "Day of the Week"),
            ("no_of_day", "Every N Days"),
            ("year", "Every Year (anniversary)"),
        ],
        string="Period",
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
        string="Day",
    )
    no_of_day = fields.Integer(string="Number of Days")
    last_wished_date = fields.Date(string="Last Sent", readonly=True)
