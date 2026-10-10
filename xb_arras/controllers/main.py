# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request

RELIGIOSOS = {'Divino Rostro', 'Sagrado Corazón', 'Madona con manos', 'San Benito', 'Milagrosa', 'Madona',
              'Dolorosa', 'Espíritu Santo', 'Crucifijo', 'Virgen de Guadalupe'}


class ArrasPage(http.Controller):

    @http.route('/arras', type='http', auth='public', website=True, sitemap=True)
    def arras(self, **kw):
        frentes = request.env['product.template'].search(
            [('xb_arras', '=', True), ('is_published', '=', True),
             ('website_id', 'in', [False, request.website.id])], order='website_sequence, id')
        tarjetas = []
        for t in frentes:
            corto = (t.name or '').split(' ·')[0]
            tarjetas.append({'t': t, 'corto': corto, 'rel': corto in RELIGIOSOS, 'desde': t._xb_arras_desde_precio()})
        vueltas = []
        if frentes:
            datos = json.loads(frentes[0]._xb_arras_json())
            vueltas = [(v['n'], v['img']) for v in datos['vueltas']]
            metales = [o['n'] for g in datos['metales'] for o in g['o']]
        else:
            metales = []
        return request.render('xb_arras.arras_page', {
            'tarjetas': tarjetas, 'vueltas': vueltas, 'metales': metales,
            'main_object': request.website,
        })
