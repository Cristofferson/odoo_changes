import re
from datetime import timedelta

from odoo import fields, http
from odoo.http import request

DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado',
        'Domingo']
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


class ParroquiaWebsite(http.Controller):

    def _dias_celebraciones(self, dias_max=13, limite_dias=None):
        hoy = fields.Date.context_today(request.env['parroquia.celebracion'])
        celebraciones = request.env['parroquia.celebracion'].sudo().search([
            ('fecha', '>=', hoy),
            ('fecha', '<=', hoy + timedelta(days=dias_max)),
            ('tipo', 'in', ('misa', 'misa_especial', 'clausura')),
        ])
        dias = []
        for fecha in sorted(set(celebraciones.mapped('fecha'))):
            if limite_dias and len(dias) >= limite_dias:
                break
            del_dia = celebraciones.filtered(
                lambda c: c.fecha == fecha).sorted(
                key=lambda c: (c.hora, c.id))
            dias.append({
                'titulo': '%s %d de %s' % (
                    DIAS[fecha.weekday()], fecha.day, MESES[fecha.month - 1]),
                'celebraciones': [{
                    'hora': c.hora_texto(),
                    'lugar': c.lugar_id.name,
                } for c in del_dia],
            })
        return dias

    @http.route(['/portada', '/inicio'], type='http', auth='public',
                website=True, sitemap=False)
    def portada(self, **kw):
        Dia = request.env['parroquia.dia.liturgico'].sudo()
        evangelio = Dia.search([('fecha', '=', Dia.hoy())], limit=1)
        frase = ''
        if evangelio and evangelio.evangelio_texto:
            texto = re.sub(r'<[^>]+>', ' ', evangelio.evangelio_texto)
            texto = re.sub(r'\s+', ' ', texto).strip()
            citas = re.findall(r'"([^"]{25,150})"', texto) or \
                re.findall(r'«([^»]{25,150})»', texto)
            if citas:
                frase = citas[-1].strip().rstrip('.') + '.'
            else:
                frase = texto[:140].rsplit(' ', 1)[0] + '…'
        return request.render('xb_parroquia_website.pagina_portada', {
            'dias': self._dias_celebraciones(dias_max=8, limite_dias=3),
            'evangelio': evangelio,
            'frase': frase,
        })

    @http.route('/horarios', type='http', auth='public', website=True,
                sitemap=True)
    def horarios(self, **kw):
        return request.render('xb_parroquia_website.pagina_horarios',
                              {'dias': self._dias_celebraciones()})

    @http.route('/avisos', type='http', auth='public', website=True,
                sitemap=True)
    def avisos(self, **kw):
        avisos = request.env['parroquia.aviso'].sudo().search([
            ('publicado', '=', True)])
        return request.render('xb_parroquia_website.pagina_avisos',
                              {'avisos': avisos})

    @http.route('/evangelio', type='http', auth='public', website=True,
                sitemap=True)
    def evangelio(self, **kw):
        Dia = request.env['parroquia.dia.liturgico'].sudo()
        dia = Dia._obtener_dia(Dia.hoy())
        fecha_texto = ''
        if dia:
            f = dia.fecha
            fecha_texto = '%s %d de %s de %d' % (
                DIAS[f.weekday()], f.day, MESES[f.month - 1], f.year)
        return request.render('xb_parroquia_website.pagina_evangelio',
                              {'dia': dia, 'fecha_texto': fecha_texto})
