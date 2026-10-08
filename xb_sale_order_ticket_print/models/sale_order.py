# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _xb_quotation_image_values(self):
        values = super()._xb_quotation_image_values()
        # Printed from Sales, the ticket can be of a confirmed order too: it is titled
        # with its kind ("PEDIDO S00123") instead of "COTIZACIÓN".
        if self.state == "sale":
            order = self.sudo()
            env = order.with_context(lang=order.partner_id.lang or self.env.lang or "en_US").env
            values["title"] = "%s %s" % (order.with_env(env).xb_wa_kind_label.upper(), order.name)
        return values
