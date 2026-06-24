# -*- coding: utf-8 -*-
from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    self_service_reserved = fields.Boolean(
        string='Reserved via Self-Service', default=False, copy=False,
        help="Set when the customer reserved this selection from the store's "
             "self-service (videowall/web). A salesperson closes it at the counter.",
    )
