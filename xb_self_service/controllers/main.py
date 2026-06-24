# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class JewelrySelfService(http.Controller):

    @http.route('/jewelry/reserve', type='http', auth='public', website=True,
                methods=['POST'], csrf=True)
    def reserve(self, **post):
        """Reserve the current cart for counter pickup (no payment).

        Marks the cart quotation as self-service-reserved, assigns the
        configured sales team, posts a note, then starts a fresh cart and
        shows a confirmation with the order reference.
        """
        order = request.cart  # Odoo 19: current cart sale.order (sudo, lazy)
        if not order or not order.order_line:
            return request.redirect('/shop')

        website = request.website
        vals = {'self_service_reserved': True}
        if website.self_service_team_id:
            vals['team_id'] = website.self_service_team_id.id
        order.sudo().write(vals)
        try:
            order.sudo().message_post(
                body="Selección apartada desde el autoservicio (videowall/web). "
                     "El cliente pasará al mostrador a cerrar la compra.")
        except Exception as e:  # never block the customer on a chatter hiccup
            _logger.warning("[XB SELF-SERVICE] message_post failed on %s: %s",
                            order.name, e)

        ref = order.name
        # Start a fresh empty cart; the reserved quotation stays in the backend.
        request.website.sale_reset()
        return request.render('xb_self_service.reserve_confirmation',
                              {'order_ref': ref})
