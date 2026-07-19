import logging
import re
from datetime import timedelta

import pytz
import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

FEED = 'https://feed.evangelizo.org/v2/reader.php'
TZ = 'America/Mexico_City'


class ParroquiaDiaLiturgico(models.Model):
    _name = 'parroquia.dia.liturgico'
    _description = 'Santo y evangelio del día (informativo)'
    _order = 'fecha desc'
    _rec_name = 'fecha'

    fecha = fields.Date(string='Fecha', required=True, index=True)
    titulo_liturgico = fields.Char(string='Día litúrgico')
    santos = fields.Text(string='Santos del día')
    evangelio_titulo = fields.Char(string='Evangelio')
    evangelio_texto = fields.Html(string='Texto del evangelio',
                                  sanitize=True)

    _fecha_unica = models.Constraint(
        'unique(fecha)', 'Ya existe el día litúrgico de esa fecha.')

    # ------- descarga desde Evangelizo (evangelizo.org) -------

    @api.model
    def _feed(self, fecha, tipo, contenido=None):
        params = {
            'date': fecha.strftime('%Y%m%d'),
            'type': tipo,
            'lang': 'SP',
        }
        if contenido:
            params['content'] = contenido
        resp = requests.get(FEED, params=params, timeout=20)
        resp.raise_for_status()
        return resp.text.strip()

    @api.model
    def _obtener_dia(self, fecha):
        """Devuelve (creando si hace falta) el registro de esa fecha."""
        rec = self.search([('fecha', '=', fecha)], limit=1)
        if rec:
            return rec
        try:
            titulo = self._feed(fecha, 'liturgic_t')
            crudo_santos = self._feed(fecha, 'saint')
            nombres = re.findall(r'>([^<>]+)</a>', crudo_santos)
            santos = ' · '.join(n.strip() for n in nombres if n.strip())
            ev_titulo = self._feed(fecha, 'reading_lt', 'GSP')
            ev_texto = self._feed(fecha, 'reading', 'GSP')
        except Exception:
            _logger.warning('No se pudo obtener el día litúrgico %s', fecha,
                            exc_info=True)
            return self.browse()
        limpiar = lambda t: re.sub(r'<[^>]+>', '', t or '').strip()
        return self.create({
            'fecha': fecha,
            'titulo_liturgico': limpiar(titulo),
            'santos': santos,
            'evangelio_titulo': limpiar(ev_titulo),
            'evangelio_texto': ev_texto,
        })

    @api.model
    def hoy(self):
        """Fecha local de la parroquia (no la del servidor)."""
        return fields.Datetime.now().astimezone(
            pytz.timezone(TZ)).date()

    @api.model
    def cron_actualizar(self):
        """Trae hoy y precarga mañana; conserva histórico."""
        hoy = self.hoy()
        self._obtener_dia(hoy)
        self._obtener_dia(hoy + timedelta(days=1))
