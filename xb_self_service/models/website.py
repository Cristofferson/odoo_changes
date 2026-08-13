# -*- coding: utf-8 -*-
from odoo import models, fields


class Website(models.Model):
    _inherit = 'website'

    self_service_enabled = fields.Boolean(
        string='Self-Service Reserve/Book', default=False,
        help="Show both call-to-action buttons on the cart so the customer can "
             "choose: reserve in store, or book an advisor.",
    )
    self_service_appointment_url = fields.Char(
        string='Advisor Booking URL', default='/appointment',
        help="Where the 'Book an advisor' button sends the customer.",
    )
    self_service_team_id = fields.Many2one(
        'crm.team', string='Reservations Sales Team',
        help="Optional: reservations are assigned to this sales team.",
    )
