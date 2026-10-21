# -*- coding: utf-8 -*-
from odoo.http import request, route

from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.main import WebsiteSale


def _xb_denied():
    """Con sesión pero sin verificar: Odoo lo mandaría al login, que lo regresa a la tienda (vuelta infinita)."""
    website = request.website
    if website._xb_b2b_blocked():
        return request.redirect(website.xb_b2b_denied_url or "/contactus", local=False)
    return None


class XbWebsiteSaleB2b(WebsiteSale):

    @route()
    def shop(self, *args, **kwargs):
        return _xb_denied() or super().shop(*args, **kwargs)

    @route()
    def product(self, *args, **kwargs):
        return _xb_denied() or super().product(*args, **kwargs)


class XbCartB2b(Cart):

    @route()
    def cart(self, *args, **kwargs):
        return _xb_denied() or super().cart(*args, **kwargs)
