# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.pos_self_order.controllers.orders import PosSelfOrderController


class XbPosSelfOrderController(PosSelfOrderController):

    @staticmethod
    def _xb_pricelist(pos_config, preset_id):
        return (preset_id.pricelist_id if preset_id else False) or pos_config.pricelist_id

    @http.route("/pos-self-order/xb-precio-joya", auth="public", type="jsonrpc", website=True)
    def xb_precio_joya(self, access_token, product_tmpl_id, ptav_ids=None):
        """Price of a jewel priced by its metal with the options chosen so far:
        {'sin': untaxed, 'con': taxes included}, or False."""
        pos_config = self._verify_pos_config(access_token, check_active_session=False)
        if not pos_config.pricelist_id:
            return False
        Template = request.env["product.template"].sudo().with_company(pos_config.company_id)
        tmpl = Template.browse(int(product_tmpl_id)).exists()
        if not tmpl:
            return False
        # Options not chosen yet take the cheapest ones (as the "from" price), so the price
        # follows the customer choice by choice instead of waiting for all of them.
        elegidos = request.env["product.template.attribute.value"].sudo().browse(
            [int(i) for i in (ptav_ids or [])]
        ).exists()
        ptavs = tmpl._xb_combinacion_desde().filtered(
            lambda v: v.attribute_line_id not in elegidos.attribute_line_id
        ) | elegidos
        return Template.xb_pos_precio_combinacion(tmpl.id, ptavs.ids, pos_config.pricelist_id.id)

    def _verify_line_price(self, lines, pos_config, preset_id):
        """The kiosk sends the price it shows. For a jewel priced by its metal the server
        computes it again from the chosen options, so a line never stays at $0."""
        super()._verify_line_price(lines, pos_config, preset_id)
        pricelist = self._xb_pricelist(pos_config, preset_id)
        if not pricelist:
            return
        Template = request.env["product.template"].sudo().with_company(pos_config.company_id)
        for line in lines.sudo():
            tmpl = line.product_id.product_tmpl_id
            if not tmpl.xb_precio_por_metal or line.combo_parent_id:
                continue
            # With dynamic attributes the line's variant may carry other values (another
            # size): what the customer chose wins, attribute by attribute.
            elegidos = line.attribute_value_ids
            ptavs = line.product_id.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_line_id not in elegidos.attribute_line_id
            ) | elegidos
            precio = Template.xb_pos_precio_combinacion(tmpl.id, ptavs.ids, pricelist.id)
            if precio and precio.get("sin"):
                line.write({"price_unit": precio["sin"]})
                line.write(line._compute_amount_line_all())
