from odoo import api, fields, models


class ParroquiaAviso(models.Model):
    _name = 'parroquia.aviso'
    _description = 'Aviso parroquial'
    _order = 'sequence, fecha desc, id desc'

    name = fields.Char(string='Resumen', compute='_compute_name', store=True)
    texto = fields.Text(string='Aviso', required=True)
    fecha = fields.Date(string='Fecha', default=fields.Date.context_today,
                        help='Fecha de captura; los avisos se ordenan por '
                             'secuencia y fecha.')
    sequence = fields.Integer(string='Secuencia', default=10)
    publicado = fields.Boolean(
        string='Publicado en el sitio', default=True,
        help='Los avisos publicados aparecen en el sitio web y en la hoja '
             'impresa. Desmárquelo cuando el aviso ya no aplique.')
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.company)

    @api.depends('texto')
    def _compute_name(self):
        for rec in self:
            texto = (rec.texto or '').strip().replace('\n', ' ')
            rec.name = texto[:80] + ('…' if len(texto) > 80 else '')
