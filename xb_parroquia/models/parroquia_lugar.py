from odoo import fields, models


class ParroquiaLugar(models.Model):
    _name = 'parroquia.lugar'
    _description = 'Lugar de celebración'
    _order = 'sequence, name'

    name = fields.Char(string='Nombre', required=True, translate=False)
    sequence = fields.Integer(string='Secuencia', default=10)
    es_templo_parroquial = fields.Boolean(
        string='Templo parroquial',
        help='Márquelo solo para el templo sede; se usa para ordenar la hoja '
             'de intenciones.')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'Ya existe un lugar con ese nombre.',
    )
