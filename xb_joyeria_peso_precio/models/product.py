# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, models
from odoo.http import request

_logger = logging.getLogger(__name__)

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
    def _get_combination_info(self, combination=False, product_id=False, add_qty=1.0, uom_id=False,
                              only_template=False):
        """La «Ficha de la pieza» (peso y metal fino, de stij_website) se calculaba con la
        variante. Con atributos dinámicos o «sin variante» (medida) la combinación elegida
        casi nunca existe como variante → llegaba vacía y el peso se quedaba fijo. Aquí se
        proyecta con la combinación COMPLETA que eligió el cliente."""
        info = super()._get_combination_info(combination=combination, product_id=product_id,
                                             add_qty=add_qty, uom_id=uom_id, only_template=only_template)
        if only_template or 'dmn_peso' not in info:
            return info
        ptavs = combination or self.env['product.template.attribute.value']
        if not ptavs and info.get('product_id'):
            ptavs = self.env['product.product'].browse(info['product_id']).product_template_attribute_value_ids
        if ptavs:
            peso, fino, metal = self._xb_proyectar_ptavs(ptavs)
            if peso:
                info['dmn_peso'] = '%.2f g' % peso
                info['dmn_fino'] = '%.2f g' % fino
                info['dmn_peso_detalle'] = '%.2f g de %s, con %.2f g de %s puro' % (
                    peso, metal.name, fino, (metal.x_metal or 'metal').lower())
            try:
                info['xb_gemas'], info['xb_diamantes'] = self._xb_gemas(ptavs)
            except Exception:  # noqa: BLE001 - un dato mal capturado nunca debe tumbar la ficha
                _logger.exception('xb_gemas: plantilla %s', self.id)
        return info

    _XB_CORTE = {'EX': 'Excelente', 'VG': 'Muy bueno', 'G': 'Bueno', 'F': 'Regular', 'ID': 'Ideal'}

    def _xb_gemas(self, ptavs):
        """Las piedras de la combinación elegida: ``(texto, [renglones de diamantes])``.
        La central sale del atributo «Piedra»; los acentos, de la lista de materiales (solo las
        líneas que aplican a esa piedra). Los diamantes de acento se describen por su producto
        («Diamante LAB 0.02Qts SI1 G VG» → 0.02 qt, pureza SI1, color G, corte Muy bueno)."""
        self.ensure_one()
        central = ptavs.filtered(lambda v: v.attribute_id.name == 'Piedra')[:1]
        acentos = {}
        bom = self.env['mrp.bom'].sudo().search(
            [('product_tmpl_id', '=', self.id), ('product_id', '=', False)], order='sequence, id', limit=1) \
            if 'mrp.bom' in self.env else None
        for linea in (bom.bom_line_ids if bom else []):
            if self._xb_linea_aplica(linea.bom_product_template_attribute_value_ids, ptavs):
                acentos[linea.product_id] = acentos.get(linea.product_id, 0) + linea.product_qty
        # El diamante central elegido por tamaño («Diamante de laboratorio 1.00 ct») es una línea más de
        # la lista de materiales: se separa de los acentos.
        centro = None
        mc = re.search(r'([\d.]+)\s*ct', central.name or '', re.I)
        if mc:
            for prod in list(acentos):
                mq = re.search(r'([\d.]+)\s*Qts?', prod.name or '', re.I)
                if mq and abs(float(mq.group(1)) - float(mc.group(1))) < 1e-6:
                    centro = prod
                    acentos.pop(prod)
                    break
        n = int(sum(acentos.values()))
        primero = next(iter(acentos), None)
        nombres = primero.name if primero else ''
        if central and n:
            tipo = 'zirconias' if 'irconia' in nombres else (
                'diamantes de laboratorio' if 'LAB' in nombres else 'diamantes naturales')
            texto = '1 central + %d de acento (%s)' % (n, tipo)
        elif central:
            texto = '1 piedra central'
        else:
            texto = '%d piedras' % n if n else ''
        renglones = []
        cn = (central.name or '').lower()
        mcen = centro and re.search(r'Diamante\s+(LAB|NAT)\s+([\d.]+)\s*Qts?\s+(\S+)\s+(\S+)\s+(\S+)', centro.name or '', re.I)
        if mcen:
            tipo, qt, pureza, color, corte = mcen.groups()
            renglones.append('Diamante central %s de %s ct · corte %s · color %s · pureza %s · certificado ICERT' % (
                'de laboratorio' if tipo.upper() == 'LAB' else 'natural', qt,
                self._XB_CORTE.get(corte.upper(), corte), color, pureza))
        elif 'diamante' in cn:
            origen = 'de laboratorio' if 'laboratorio' in cn else 'natural'
            renglones.append('Diamante central %s: quilataje, color y pureza a tu elección con tu asesor · '
                             'certificado ICERT' % origen)
        for prod, qty in acentos.items():
            m = re.search(r'Diamante\s+(LAB|NAT)\s+([\d.]+)\s*Qts?\s+(\S+)\s+(\S+)\s+(\S+)', prod.name or '', re.I)
            if not m:
                continue
            tipo, qt, pureza, color, corte = m.groups()
            q = int(qty)
            renglones.append('%d diamantes de acento %s de %s qt (%.2f qt en total) · corte %s · pureza %s · '
                             'color %s · certificado ICERT de la pieza' % (
                                 q, 'de laboratorio' if tipo.upper() == 'LAB' else 'naturales', qt,
                                 q * float(qt), self._XB_CORTE.get(corte.upper(), corte), pureza, color))
        return texto, renglones

    # ------------------------------------------------------------------
    # Precio = metal (a su precio de venta) + (hechura + piedras) × margen de la lista   (5-oct)
    # El metal vale lo mismo suelto que dentro de una joya: se cobra con la regla de la lista para el
    # metal suelto (p. ej. «Oro suelto por gramo»: costo + 8 %). El margen del joyero va en la hechura y
    # las piedras: la regla de la joya («costo + 128 %») solo se aplica a ese costo. Todo se configura
    # en la lista de precios; no hay parámetros aparte.
    # ------------------------------------------------------------------
    def _xb_metal_aleacion(self, ptavs):
        """(aleación, gramos) de la combinación, o (False, 0) si el metal no tiene aleación ligada."""
        self.ensure_one()
        peso, _fino, metal = self._xb_proyectar_ptavs(ptavs)
        aleacion = metal.xb_aleacion_id if metal and 'xb_aleacion_id' in metal._fields else False
        return (aleacion, peso) if aleacion and peso else (False, 0.0)

    def _xb_costo_combinacion(self, ptavs):
        """Costo que ve la regla de la joya: SOLO hechura y piedras cuando el metal tiene aleación
        (el metal se suma aparte, a su precio de venta)."""
        costo = super()._xb_costo_combinacion(ptavs)
        if costo is None:
            return costo
        aleacion, _g = self._xb_metal_aleacion(ptavs)
        if not aleacion:
            return costo
        _peso, fino, metal = self._xb_proyectar_ptavs(ptavs)
        return costo - fino * self._xb_cotizacion(metal)

    def _xb_metal_venta(self, ptavs, pricelist, date=False, currency=None):
        """Lo que se cobra por el metal: gramos de la aleación × su precio en esa lista."""
        aleacion, gramos = self._xb_metal_aleacion(ptavs)
        if not aleacion or not pricelist:
            return 0.0
        # sudo: el visitante de la tienda no puede leer el COSTO del metal suelto (campo solo para
        # empleados) y la regla del metal es «costo + 8 %». Se cotiza con la compañía de la lista.
        cia = pricelist.company_id or self.company_id or self.env.company
        pl = pricelist.sudo().with_company(cia)
        precio_g = pl._get_product_price(aleacion.sudo().with_company(cia), gramos, currency=currency, date=date)
        return precio_g * gramos

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


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    def _compute_price(self, product, quantity, uom, date, currency=None, **kwargs):
        """Joya cotizada por metal con regla «sobre costo»: al resultado (hechura + piedras con margen)
        se le suma el metal a su precio de venta en la misma lista."""
        price = super()._compute_price(product, quantity, uom, date, currency=currency, **kwargs)
        if not self or self.compute_price != 'formula' or self.base != 'standard_price':
            return price
        tmpl = product.product_tmpl_id if product._name == 'product.product' else product
        if not tmpl.xb_precio_por_metal:
            return price
        ptavs = tmpl._xb_ptavs_del_contexto()
        if not ptavs and product._name == 'product.product':
            ptavs = product.product_template_attribute_value_ids
        if not ptavs:
            return price
        moneda = currency or self.currency_id or self.env.company.currency_id
        metal = tmpl._xb_metal_venta(ptavs, self.pricelist_id, date=date, currency=moneda)
        if metal and product.uom_id != uom:
            metal = product.uom_id._compute_price(metal, uom)
        return price + metal
