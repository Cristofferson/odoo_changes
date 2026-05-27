# -*- coding: utf-8 -*-
from odoo import fields, models


class XbWishSchedule(models.Model):
    _inherit = "xb.wish.schedule"

    whatsapp_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="WhatsApp Template",
        domain="[('model', '=', 'xb.wish.reminders')]",
        ondelete="set null",
    )
