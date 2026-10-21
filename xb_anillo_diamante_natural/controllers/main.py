# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from ..models.product import ordenar_formas
from ..models.sale_order import SESION


class XbDiamanteNatural(http.Controller):

    def _xb_gemas(self):
        website = request.website
        gemas = request.env["product.template"].sudo().with_context(lang="en_US").search(
            request.env["product.template"]._xb_diamantes_naturales_domain(website))
        gemas = gemas.with_context(lang=request.env.lang)
        en_carrito = request.cart.order_line.product_id if request.cart else request.env["product.product"]
        return gemas.filtered(lambda t: t.product_variant_id not in en_carrito
                              and website._get_product_available_qty(t.product_variant_id) > 0)

    @http.route("/xb_diamante_natural/lista", type="jsonrpc", auth="public", website=True, sitemap=False)
    def lista(self):
        """Diamantes naturales que el cliente puede elegir para su anillo (cualquier forma)."""
        gemas = self._xb_gemas()
        precios = gemas._get_sales_prices(request.website)
        res = [t._xb_datos_diamante(precios[t.id]["price_reduce"]) for t in gemas]
        res.sort(key=lambda d: d["precio"])
        return {"diamantes": res, "formas": ordenar_formas(d["forma"] for d in res),
                "moneda": request.website.currency_id.symbol or "$"}

    @http.route("/xb_diamante_natural/elegir", type="jsonrpc", auth="public", website=True, sitemap=False)
    def elegir(self, product_template_id, product_id=None):
        """Recuerda el diamante elegido para este anillo hasta que se agregue al carrito."""
        elegidas = dict(request.session.get(SESION) or {})
        if product_id:
            gema = request.env["product.product"].sudo().browse(int(product_id)).exists()
            if not gema or not gema._xb_es_diamante_natural(request.website):
                return {"ok": False}
            elegidas[str(int(product_template_id))] = gema.id
        else:
            elegidas.pop(str(int(product_template_id)), None)
        request.session[SESION] = elegidas
        return {"ok": True}
