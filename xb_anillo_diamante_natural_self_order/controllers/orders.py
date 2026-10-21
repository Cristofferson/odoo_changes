# -*- coding: utf-8 -*-
from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.xb_anillo_diamante_natural.models.product import ordenar_formas
from odoo.addons.xb_joyeria_peso_precio_self_order.controllers.orders import XbPosSelfOrderController


class XbDiamanteNaturalSelfOrder(XbPosSelfOrderController):

    @http.route("/pos-self-order/xb-diamantes-naturales", auth="public", type="jsonrpc", website=True)
    def xb_diamantes_naturales(self, access_token):
        """Diamantes naturales con existencia para el anillo, con el precio de la lista del kiosco."""
        pos_config = self._verify_pos_config(access_token, check_active_session=False)
        Template = request.env["product.template"].sudo().with_company(pos_config.company_id)
        gemas = Template.with_context(lang="en_US").search(
            Template._xb_diamantes_naturales_domain() + [("available_in_pos", "=", True),
                                                         ("self_order_available", "=", True)])
        gemas = gemas.with_context(lang=request.env.lang).filtered(
            lambda t: t.product_variant_id.with_context(
                warehouse_id=pos_config.picking_type_id.warehouse_id.id).free_qty > 0)
        pricelist = pos_config.pricelist_id
        res = []
        for t in gemas:
            precio = pricelist._get_product_price(t.product_variant_id, 1.0)
            impuestos = t.taxes_id._filter_taxes_by_company(pos_config.company_id)
            total = impuestos.compute_all(precio, currency=pricelist.currency_id, quantity=1.0, product=t)
            res.append(t._xb_datos_diamante(total["total_included"]))
        res.sort(key=lambda d: d["precio"])
        return {"diamantes": res, "formas": ordenar_formas(d["forma"] for d in res)}

    def _verify_line_price(self, lines, pos_config, preset_id):
        super()._verify_line_price(lines, pos_config, preset_id)
        lines = lines.sudo()
        anillos = sum(l.qty for l in lines if l.product_id._xb_es_anillo_natural())
        gemas = sum(l.qty for l in lines if l.product_id._xb_es_diamante_natural())
        if anillos > gemas:
            raise UserError(_("Cada anillo con diamante natural necesita su diamante. Vuelve a agregar el "
                              "anillo eligiendo el diamante."))
