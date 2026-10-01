# -*- coding: utf-8 -*-
import re

from odoo import api, models
from odoo.http import request

KT = re.compile(r'(\d+)\s*k', re.I)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _xb_combinacion_desde(self):
        """Combinación para el «Desde»: la primera posible, cambiando el metal por el ORO
        de menor kilataje que ofrece la pieza (no plata/acero: sería engañoso para oro)."""
        self.ensure_one()
        comb = self._get_first_possible_combination()
        metal_line = self.valid_product_template_attribute_line_ids.filtered(lambda l: l.attribute_id.name == 'Metal')
        if not metal_line:
            return comb
        oros = metal_line.product_template_value_ids._only_active().filtered(
            lambda v: 'oro' in (v.name or '').lower() and 'imitaci' not in (v.name or '').lower() and KT.search(v.name or ''))
        if not oros:
            return comb
        barato = min(oros, key=lambda v: int(KT.search(v.name).group(1)))
        return (comb - comb.filtered(lambda v: v.attribute_line_id == metal_line)) | barato

    def _get_sales_prices(self, website):
        res = super()._get_sales_prices(website)
        joyas = self.filtered(lambda t: t.xb_precio_por_metal)
        if not joyas or not request:
            return res
        pricelist = request.pricelist
        currency = website.currency_id
        for tmpl in joyas:
            vals = res.get(tmpl.id) or {}
            if vals.get('price_reduce'):
                continue
            try:
                comb = tmpl._xb_combinacion_desde()
                precio = pricelist._get_product_price(tmpl.with_context(xb_combinacion=tuple(comb.ids)), 1.0)
            except Exception:  # noqa: BLE001 - un producto mal capturado nunca debe tumbar la tienda
                continue
            if not precio:
                continue
            product_taxes = tmpl.sudo().taxes_id._filter_taxes_by_company(self.env.company)
            taxes = request.fiscal_position.map_tax(product_taxes)
            vals['price_reduce'] = self._apply_taxes_to_price(precio, currency, product_taxes, taxes, tmpl, website=website)
            vals['xb_desde'] = True
            res[tmpl.id] = vals
        return res

    @api.model
    def _load_pos_data_fields(self, config):
        res = super()._load_pos_data_fields(config)
        if res and 'xb_precio_por_metal' not in res:   # lista vacía = «todos los campos»: no tocar
            res.append('xb_precio_por_metal')
        return res


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def xb_pos_precio_metal(self, ptav_ids, pricelist_id=False):
        """Precio SIN impuestos de esta joya con la combinación elegida en la caja."""
        self.ensure_one()
        tmpl = self.product_tmpl_id
        if not tmpl.xb_precio_por_metal:
            return False
        ptavs = (self.product_template_attribute_value_ids
                 | self.env['product.template.attribute.value'].browse(ptav_ids or []).exists())
        pricelist = self.env['product.pricelist'].browse(pricelist_id).exists() if pricelist_id else False
        prod = self.with_context(xb_combinacion=tuple(ptavs.ids))
        if pricelist:
            return pricelist._get_product_price(prod, 1.0)
        costo = tmpl._xb_costo_combinacion(ptavs)
        return costo or False
