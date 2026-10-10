# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    xb_arras_frente = fields.Image(
        'Frente sin fondo', max_width=1024, max_height=1024,
        help='Arras: la moneda del frente con fondo transparente, para la ficha configuradora.')
    xb_arras = fields.Boolean(
        'Arras 3888', compute='_compute_xb_arras', store=True, readonly=True,
        help='Juego de arras personalizadas. Se prende solo cuando la categoría del producto está '
             'marcada como «Arras 3888»: el tamaño multiplica el peso con su factor y la imitación '
             'se cotiza solo con su lista de materiales.')
    xb_arras_tamano_ids = fields.One2many(
        'product.template.attribute.value', 'product_tmpl_id', string='Metal por tamaño',
        domain=[('attribute_id.name', '=', 'Tamaño de arra'), ('ptav_active', '=', True)])

    @api.depends('categ_id.xb_arras_categoria')
    def _compute_xb_arras(self):
        for t in self:
            t.xb_arras = bool(t.categ_id.xb_arras_categoria)

    def _xb_factor_arras(self, ptavs):
        """Producto de los factores de peso de la combinación (1 si no hay)."""
        factor = 1.0
        for v in ptavs:
            if v.product_tmpl_id == self and v.xb_factor_peso:
                factor *= v.xb_factor_peso
        return factor

    def _xb_proyectar_ptavs(self, ptavs):
        peso, fino, metal = super()._xb_proyectar_ptavs(ptavs)
        if self.xb_arras and peso:
            f = self._xb_factor_arras(ptavs)
            return peso * f, fino * f, metal
        return peso, fino, metal

    def _xb_costo_combinacion(self, ptavs):
        costo = super()._xb_costo_combinacion(ptavs)
        if costo is None and self.xb_arras and self.xb_precio_por_metal:
            # Imitación: sin metal fino que cotizar; cuesta lo que diga la lista de materiales.
            ldm = self._xb_costo_ldm(ptavs, self.company_id or self.env.company)
            return ldm or None
        return costo

    def _xb_combinacion_desde(self):
        """«Desde» de las arras: el juego más barato que se ofrece (el menor costo entre metales
        en el tamaño más chico), no el oro de menor kilataje."""
        self.ensure_one()
        comb = super()._xb_combinacion_desde()
        if not self.xb_arras:
            return comb
        lineas = self.valid_product_template_attribute_line_ids
        metal_l = lineas.filtered(lambda l: l.attribute_id.name == 'Metal')
        if not metal_l:
            return comb
        tam_l = lineas.filtered(lambda l: l.attribute_id.name == 'Tamaño de arra')
        if tam_l:
            chico = tam_l.product_template_value_ids._only_active()[:1]
            comb = (comb - comb.filtered(lambda v: v.attribute_line_id == tam_l)) | chico
        base = comb - comb.filtered(lambda v: v.attribute_line_id == metal_l)
        # Se compara el PRECIO de venta: el costo no sirve (en plata y oro el metal se cobra aparte del costo).
        pricelist = (request.pricelist if request and hasattr(request, 'pricelist') else None) \
            or self.env['product.pricelist'].search([('company_id', 'in', [self.company_id.id, False])], limit=1)
        mejor, precio = comb, None
        for m in metal_l.product_template_value_ids._only_active():
            c = base | m
            try:
                p = pricelist._get_product_price(self.with_context(**self._get_product_price_context(c)), 1.0)
            except Exception:  # noqa: BLE001
                continue
            if p and (precio is None or p < precio):
                mejor, precio = c, p
        return mejor


class ProductCategory(models.Model):
    _inherit = 'product.category'

    xb_arras_categoria = fields.Boolean(
        'Arras 3888',
        help='Los productos de esta categoría son juegos de Arras 3888: se cotizan por tamaño, salen '
             'en /arras con el configurador, tienen su diseño en el muro y el taller recibe el grabado.')


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    xb_factor_peso = fields.Float(
        'Factor de peso', default=1.0, digits=(12, 4),
        help='Arras: multiplica el peso de la pieza cuando se elige este valor (p. ej. el tamaño).')
    xb_arras_peso_juego = fields.Float(
        'Peso del juego (14K)', compute='_compute_xb_arras_peso_juego', digits=(12, 2),
        help='Peso de referencia del juego de 13 (oro 14K) multiplicado por el factor de este tamaño.')

    @api.depends('xb_factor_peso', 'product_tmpl_id')
    def _compute_xb_arras_peso_juego(self):
        for v in self:
            t = v.product_tmpl_id
            base = t._xb_numero(t.x_studio_peso_joya) if 'x_studio_peso_joya' in t._fields else 0.0
            v.xb_arras_peso_juego = (base or 0.0) * (v.xb_factor_peso or 0.0)

    def _only_active(self):
        res = super()._only_active()
        # En la tienda, xb_joyeria_peso_precio oculta los metales marcados (imitación, plata, 22K);
        # en las arras sí se venden en línea.
        if request and getattr(request, 'is_frontend', False):
            arras = self.filtered(lambda v: v.ptav_active and v.product_tmpl_id.xb_arras)
            if arras:
                res = self.filtered(lambda v: v in res or v in arras)
        return res


import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import unicodedata  # noqa: E402

IMG_VUELTAS = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'src', 'img', 'v')


def _slug(texto):
    t = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')

VALORES_ARRAS = [
    ('Amor', 'El amor incondicional'), ('Fidelidad', 'La fidelidad mutua'),
    ('Confianza', 'La confianza en la pareja'), ('Respeto', 'El respeto mutuo'),
    ('Alegría', 'La alegría en el hogar'), ('Paciencia', 'La paciencia en la convivencia'),
    ('Comprensión', 'La comprensión'), ('Fortaleza', 'La fortaleza en las dificultades'),
    ('Prosperidad', 'El trabajo y la prosperidad compartida'), ('Salud', 'La salud física y espiritual'),
    ('Familia', 'La familia y los hijos'), ('Fe', 'La fe en Dios'),
    ('Generosidad', 'La generosidad y la caridad'),
]
TAMANO_TXT = {'1.5': ('Chica', 'como una moneda de 50 centavos'),
              '2.0': ('Mediana', 'como una moneda de $1'),
              '2.5': ('Grande', 'como una moneda de $5')}


class ProductTemplateFicha(models.Model):
    _inherit = 'product.template'

    def _xb_arras_metal(self, pav):
        """(grupo, etiqueta, tono) de un valor del atributo Metal, en palabras del cliente."""
        n = (pav.name or '').lower()
        if (pav.x_metal or '') == 'Imitación' or 'imitaci' in n:
            oro = 'oro' in n
            return 'Imitación', 'Imitación oro' if oro else 'Imitación plata', 'g' if oro else 's'
        if (pav.x_metal or '') == 'Plata':
            rodio = 'rodio' in n
            return 'Plata .925', 'Plata con baño de rodio' if rodio else 'Plata con baño de oro', 's' if rodio else 'g'
        kt = re.search(r'(\d+)\s*k', n)
        kt = kt.group(1) if kt else ''
        return 'Oro amarillo', 'Oro %sK' % kt if kt else pav.name, {'10': 'g10', '22': 'g22', '24': 'g24'}.get(kt, 'g')

    def _xb_arras_json(self):
        """Todo lo que la ficha de arras necesita, calculado en el servidor (precio de cada metal ×
        tamaño con la lista y los impuestos de la tienda)."""
        self.ensure_one()
        lineas = self.valid_product_template_attribute_line_ids
        def linea(nombre):
            return lineas.filtered(lambda l: l.attribute_id.name == nombre)
        lm, lt, lv, lg = linea('Metal'), linea('Tamaño de arra'), linea('Vuelta'), linea('Grabado de la vuelta')
        activos = lambda l: l.product_template_value_ids._only_active()
        base = self._get_first_possible_combination()
        resto = base - base.filtered(lambda v: v.attribute_line_id in (lm | lt))
        metales, tamanos = activos(lm), activos(lt)
        precios = {}
        for m in metales:
            for t in tamanos:
                comb = resto | m | t
                info = self._get_combination_info(combination=comb, add_qty=1)
                peso, _fino, _met = self._xb_proyectar_ptavs(comb)
                precios['%d-%d' % (m.id, t.id)] = {'p': info.get('price'), 'g': round(peso / 13.0, 2) if peso else 0}
        grupos = []
        for m in metales:
            g, etiqueta, tono = self._xb_arras_metal(m.product_attribute_value_id)
            if not grupos or grupos[-1]['g'] != g:
                grupos.append({'g': g, 'o': []})
            grupos[-1]['o'].append({'id': m.id, 'n': etiqueta, 't': tono})
        orden = {'Imitación': 0, 'Plata .925': 1, 'Oro amarillo': 2}
        grupos.sort(key=lambda x: orden.get(x['g'], 9))
        sub = {'Imitación': 'Económicas, con acabado de joyería', 'Plata .925': 'Plata fina con un baño que le da su color',
               'Oro amarillo': 'Oro macizo, el mismo de nuestros anillos'}
        for g in grupos:
            g['s'] = sub.get(g['g'], '')
        vueltas = []
        for v in activos(lv):
            n = (v.name or '').lower()
            campos = [c for c, k in (('v', 'valor'), ('n', 'nombre'), ('i', 'iniciales'), ('d', 'fecha')) if k in n]
            # La foto del valor de atributo se guarda a 70 px: para la ficha se usa la del módulo (600 px).
            archivo = '%s.webp' % _slug(v.product_attribute_value_id.with_context(lang='es_MX').name)
            img = ('/xb_arras/static/src/img/v/' + archivo if os.path.exists(os.path.join(IMG_VUELTAS, archivo))
                   else '/web/image/product.template.attribute.value/%d/image' % v.id)
            vueltas.append({'id': v.id, 'n': v.name, 'img': img, 'f': campos})
        frentes = self.search([('xb_arras', '=', True), ('is_published', '=', True)], order='website_sequence, id')
        datos = {
            'tmpl': self.id,
            'nombre': (self.name or '').split(' ·')[0],
            'frente_img': '/web/image/product.template/%d/%s' % (self.id, 'xb_arras_frente' if self.xb_arras_frente else 'image_1024'),
            'valores_frente': (self.name or '').startswith('Valores'),
            'metales': grupos, 'precios': precios,
            'tamanos': [{'id': t.id, 'n': t.name, 'k': t.xb_factor_peso,
                         'cm': (re.search(r'[\d.]+', t.name) or [''])[0],
                         'l': TAMANO_TXT.get((re.search(r'[\d.]+', t.name) or [''])[0], ('', ''))[0],
                         'c': TAMANO_TXT.get((re.search(r'[\d.]+', t.name) or [''])[0], ('', ''))[1]} for t in tamanos],
            'vueltas': vueltas,
            'grabado': activos(lg)[:1].id,
            'frentes': [{'id': f.id, 'n': (f.name or '').split(' ·')[0], 'url': f.website_url,
                         'img': '/web/image/product.template/%d/image_128' % f.id} for f in frentes],
            'fotos': ['/web/image/product.image/%d/image_512' % i.id for i in self.product_template_image_ids],
            'valores': VALORES_ARRAS,
            'moneda': self.env.company.currency_id.symbol or '$',
        }
        return json.dumps(datos, ensure_ascii=False)


class ProductTemplateDesde(models.Model):
    _inherit = 'product.template'

    def _xb_arras_desde_precio(self):
        """Precio «Desde» (juego más barato) tal como lo muestra la tienda (lista e impuestos del sitio)."""
        self.ensure_one()
        try:
            comb = self._xb_combinacion_desde()
            return self._get_combination_info(combination=comb, add_qty=1).get('price')
        except Exception:  # noqa: BLE001 - una ficha mal capturada no debe tumbar la página
            return None
