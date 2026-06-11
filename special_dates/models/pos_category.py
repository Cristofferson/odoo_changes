# -*- coding: utf-8 -*-
from odoo import fields, models


class PosCategory(models.Model):
    _inherit = "pos.category"

    xb_triggers_wish_type_id = fields.Many2one(
        comodel_name="xb.wish.type",
        string="Triggers Reminder Type",
        domain=[("xb_pos_auto_capture", "=", True), ("active", "=", True)],
        help="When products of this POS category are added to a POS order, "
             "the cashier will be prompted to register a special date of "
             "this type for the customer (e.g. wedding rings -> wedding "
             "anniversary). Leave empty to disable the auto-capture flow "
             "for this category.",
    )
