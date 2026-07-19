from datetime import timedelta

from odoo import api, fields, models

ABREV_DIA = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']


class ParroquiaCelebracion(models.Model):
    _name = 'parroquia.celebracion'
    _inherit = ['parroquia.celebracion', 'pos.load.mixin']

    etiqueta_pos = fields.Char(string='Etiqueta POS',
                               compute='_compute_etiqueta_pos')

    @api.depends('fecha', 'hora', 'lugar_id')
    def _compute_etiqueta_pos(self):
        for rec in self:
            if not rec.fecha:
                rec.etiqueta_pos = ''
                continue
            rec.etiqueta_pos = '%s %02d/%02d · %s · %s' % (
                ABREV_DIA[rec.fecha.weekday()], rec.fecha.day,
                rec.fecha.month, rec.hora_texto(),
                rec.lugar_id.name or '')

    @api.model
    def _load_pos_data_domain(self, data, config):
        hoy = fields.Date.context_today(self)
        return [
            ('fecha', '>=', hoy),
            ('fecha', '<=', hoy + timedelta(days=60)),
            ('tipo', 'in', ('misa', 'misa_especial', 'clausura', 'funeral',
                            'boda', 'xv')),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'fecha', 'hora', 'tipo', 'etiqueta_pos', 'write_date']
