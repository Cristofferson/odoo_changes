# -*- coding: utf-8 -*-
from odoo import models, fields


class Website(models.Model):
    _inherit = 'website'

    self_service_enabled = fields.Boolean(
        string='Self-Service Reserve/Book', default=False,
        help="Show the reserve / book-an-advisor call-to-action on the cart, "
             "routed by the value threshold below.",
    )
    self_service_threshold = fields.Float(
        string='Assisted-Sale Threshold', default=5000.0,
        help="Basket totals at or above this amount route the customer to book "
             "an advisor instead of reserving. Below it, they can reserve for "
             "counter pickup.",
    )
    self_service_appointment_url = fields.Char(
        string='Advisor Booking URL', default='/appointment',
        help="Where the 'Book an advisor' button sends the customer.",
    )
    self_service_team_id = fields.Many2one(
        'crm.team', string='Reservations Sales Team',
        help="Optional: reservations are assigned to this sales team.",
    )
