from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def action_pos_order_paid(self):
        res = super().action_pos_order_paid()
        self._xb_crear_intenciones()
        return res

    def _xb_crear_intenciones(self):
        """Crea la intención pagada de cada línea de intención cobrada.

        Idempotente: una línea que ya tiene intención ligada no vuelve a
        crearla (reintentos de sincronización del POS). Las devoluciones
        (cantidad negativa) no crean intenciones.
        """
        Intencion = self.env['parroquia.intencion'].sudo()
        for order in self:
            for line in order.lines:
                if (not line.intencion_celebracion_id
                        or not line.intencion_nombres
                        or line.intencion_id
                        or line.qty <= 0):
                    continue
                line.intencion_id = Intencion.create({
                    'celebracion_id': line.intencion_celebracion_id.id,
                    'tipo': line.intencion_tipo or 'difuntos',
                    'nombres': line.intencion_nombres,
                    'solicitante': order.partner_id.name or order.name,
                    'pagada': True,
                    'pos_order_line_id': line.id,
                })


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    intencion_celebracion_id = fields.Many2one(
        'parroquia.celebracion', string='Misa (intención)')
    intencion_tipo = fields.Selection([
        ('destacada', 'Intención destacada'),
        ('vivos', 'Vivos'),
        ('salud', 'Por la salud de'),
        ('familias', 'Familias'),
        ('difuntos', 'Difuntos'),
        ('desaparecidos', 'Desaparecidos'),
        ('otros', 'Otros'),
    ], string='Tipo de intención')
    intencion_nombres = fields.Text(string='Nombres (intención)')
    intencion_id = fields.Many2one('parroquia.intencion',
                                   string='Intención creada', readonly=True)

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            'intencion_celebracion_id', 'intencion_tipo',
            'intencion_nombres',
        ]
