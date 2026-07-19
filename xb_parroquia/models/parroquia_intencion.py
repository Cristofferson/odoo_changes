from odoo import fields, models


class ParroquiaIntencion(models.Model):
    _name = 'parroquia.intencion'
    _description = 'Intención de misa'
    _order = 'celebracion_id, sequence, id'

    celebracion_id = fields.Many2one('parroquia.celebracion',
                                     string='Celebración', required=True,
                                     ondelete='cascade', index=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    tipo = fields.Selection([
        ('destacada', 'Intención destacada'),
        ('vivos', 'Vivos'),
        ('salud', 'Por la salud de'),
        ('familias', 'Familias'),
        ('difuntos', 'Difuntos'),
        ('desaparecidos', 'Desaparecidos'),
        ('otros', 'Otros'),
    ], string='Tipo', required=True, default='difuntos')
    nombres = fields.Text(
        string='Nombres', required=True,
        help='Nombres tal como deben aparecer en la hoja, separados por '
             'comas. Ej.: «6° aniversario luctuoso de María Pérez, Salvador '
             'Villegas» o «fin de novenario de Adela Ornelas».')
    solicitante = fields.Char(
        string='Solicitante',
        help='Quién pidió la intención (opcional, no se imprime).')
    pagada = fields.Boolean(
        string='Pagada', default=True,
        help='Solo las intenciones pagadas se imprimen en la hoja. La '
             'captura manual en notaría se asume cobrada; las ventas del '
             'punto de venta la marcan al pagar el ticket.')
    fecha = fields.Date(related='celebracion_id.fecha', store=True,
                        string='Fecha de la misa')
    lugar_id = fields.Many2one(related='celebracion_id.lugar_id', store=True,
                               string='Lugar')
    company_id = fields.Many2one(related='celebracion_id.company_id',
                                 store=True)

    def imprimible(self):
        self.ensure_one()
        return self.pagada
