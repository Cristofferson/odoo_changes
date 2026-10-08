# -*- coding: utf-8 -*-
from odoo import models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def read_pos_data(self, data, config):
        # pos_restaurant always answers a synced order with its courses, but a POS that
        # is not a restaurant never loads restaurant.order.course: the POS then crashes
        # after the payment ("Cannot read properties of undefined (reading
        # 'triggerEvents')"). Only a restaurant POS gets them.
        result = super().read_pos_data(data, config)
        if config and not config.module_pos_restaurant:
            result.pop("restaurant.order.course", None)
        return result
