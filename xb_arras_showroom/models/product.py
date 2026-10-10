# -*- coding: utf-8 -*-
import os

from odoo import models

from odoo.addons.xb_arras.models.product import IMG_VUELTAS, VALORES_ARRAS, _slug


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _xb_arras_muro(self, pricelist, options, company, money):
        """Lo que el muro necesita para dibujar unas arras: frente, vuelta elegida, tamaños y la
        tabla de precios (lista de la tienda, IVA incluido) de cada metal en cada tamaño."""
        self.ensure_one()
        lineas = self.valid_product_template_attribute_line_ids
        def valores(nombre):
            l = lineas.filtered(lambda x: x.attribute_id.name == nombre)
            return l.product_template_value_ids._only_active()
        metales, tamanos, vueltas = valores('Metal'), valores('Tamaño de arra'), valores('Vuelta')
        m_sel = (options & metales)[:1] or metales[:1]
        t_sel = (options & tamanos)[:1] or tamanos[:1]
        v_sel = (options & vueltas)[:1] or vueltas[:1]
        moneda = pricelist.currency_id or company.currency_id
        impuestos = self.taxes_id._filter_taxes_by_company(company)

        def precio(m, t):
            p = pricelist._get_product_price(self.with_context(**self._get_product_price_context(m | t)), 1.0)
            return impuestos.compute_all(p, currency=moneda, product=self)['total_included'] if impuestos else p

        filas = []
        orden = {'Imitación': 0, 'Plata .925': 1, 'Oro amarillo': 2}
        for m in metales.sorted(lambda v: orden.get(self._xb_arras_metal(v.product_attribute_value_id)[0], 9)):
            grupo, etiqueta, tono = self._xb_arras_metal(m.product_attribute_value_id)
            filas.append({'g': grupo, 'n': etiqueta, 't': tono, 'sel': m == m_sel,
                          'p': [money(precio(m, t), moneda) for t in tamanos]})
        archivo = '%s.webp' % _slug(v_sel.product_attribute_value_id.with_context(lang='es_MX').name or '')
        vuelta_img = ('/xb_arras/static/src/img/v/' + archivo
                      if v_sel and os.path.exists(os.path.join(IMG_VUELTAS, archivo)) else '')
        v_nombre = (v_sel.name or '').lower()
        nombre = (self.name or '').split(' ·')[0]
        _g, metal_txt, tono = self._xb_arras_metal(m_sel.product_attribute_value_id) if m_sel else ('', '', 'g')
        return {
            'nombre': nombre,
            'frente': '/web/image/product.template/%d/%s' % (
                self.id, 'xb_arras_frente' if self.xb_arras_frente else 'image_1024'),
            'vuelta': v_sel.name or '',
            'vuelta_img': vuelta_img,
            'metal': metal_txt,
            'tono': tono,
            'tamano': (t_sel.name or ''),
            'tamanos': [{'n': t.name, 'k': t.xb_factor_peso or 1.0, 'sel': t == t_sel} for t in tamanos],
            'filas': filas,
            'precio': money(precio(m_sel, t_sel), moneda) if m_sel and t_sel else '',
            'valores': [v for v, _s in VALORES_ARRAS] if ('valor' in v_nombre or nombre == 'Valores') else [],
            'logo': '/xb_arras/static/src/img/logo-dorado.webp',
            'logo_blanco': '/xb_arras/static/src/img/logo-blanco.webp',
        }
