from odoo import api, fields, models

DIAS = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO',
        'DOMINGO']
MESES = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO',
         'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']


class ParroquiaCelebracion(models.Model):
    _name = 'parroquia.celebracion'
    _description = 'Celebración (misa o acto parroquial)'
    _inherit = ['mail.thread']
    _order = 'fecha, hora, id'

    name = fields.Char(string='Referencia', compute='_compute_name',
                       store=True)
    fecha = fields.Date(string='Fecha', required=True,
                        default=fields.Date.context_today, index=True,
                        tracking=True)
    hora = fields.Float(string='Hora', required=True, default=7.0,
                        help='Hora local de la celebración (formato 24 h).')
    lugar_id = fields.Many2one('parroquia.lugar', string='Lugar',
                               required=True, tracking=True)
    celebrante_id = fields.Many2one(
        'res.partner', string='Celebrante',
        help='Sacerdote asignado. Puede dejarse vacío y definirse en el '
             'tablero del comedor, como se hace hoy.')
    tipo = fields.Selection([
        ('misa', 'Misa'),
        ('misa_especial', 'Misa especial'),
        ('funeral', 'Funeral'),
        ('boda', 'Boda'),
        ('xv', 'XV años'),
        ('clausura', 'Misa de clausura'),
        ('presentacion', 'Presentación de matrimonio'),
        ('otro', 'Otro acto'),
    ], string='Tipo', required=True, default='misa', tracking=True)
    nota = fields.Char(
        string='Nota para la hoja',
        help='Texto libre que se imprime en la columna de intenciones cuando '
             'no hay intenciones capturadas (p. ej. «Misa de aniversario del '
             'Santísimo», «pagado», «estarán presentes los alumnos del '
             'preescolar»).')
    pagada = fields.Boolean(
        string='Pagada', tracking=True,
        help='Para misas especiales/funerales: ya se cubrió el costo.')
    incluir_animas = fields.Boolean(
        string='Cerrar difuntos con «ánimas del purgatorio»', default=True)
    intencion_ids = fields.One2many('parroquia.intencion', 'celebracion_id',
                                    string='Intenciones')
    intencion_count = fields.Integer(compute='_compute_intencion_count')
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.company)

    @api.depends('fecha', 'hora', 'lugar_id', 'tipo')
    def _compute_name(self):
        tipos = dict(self._fields['tipo'].selection)
        for rec in self:
            partes = []
            if rec.tipo:
                partes.append(tipos.get(rec.tipo, rec.tipo))
            if rec.lugar_id:
                partes.append(rec.lugar_id.name)
            if rec.fecha:
                partes.append('%s %s' % (
                    fields.Date.to_string(rec.fecha), rec.hora_texto()))
            rec.name = ' · '.join(partes) or 'Celebración'

    def _compute_intencion_count(self):
        for rec in self:
            rec.intencion_count = len(rec.intencion_ids)

    def hora_texto(self):
        """Hora en el formato de la hoja: 7:30 a.m. / 6:00 p.m."""
        self.ensure_one()
        horas = int(self.hora)
        minutos = int(round((self.hora - horas) * 60))
        if minutos == 60:
            horas, minutos = horas + 1, 0
        sufijo = 'a.m.' if horas < 12 else 'p.m.'
        hora12 = horas % 12 or 12
        return '%d:%02d %s' % (hora12, minutos, sufijo)

    def encabezado_dia(self):
        """Encabezado tipo «LUNES 29 JUNIO 2026» para la hoja."""
        self.ensure_one()
        f = self.fecha
        return '%s %d %s %d' % (
            DIAS[f.weekday()], f.day, MESES[f.month - 1], f.year)

    def intenciones_agrupadas(self):
        """Lista [(etiqueta, texto)] en el orden de la hoja impresa.

        Devuelve las intenciones agrupadas por tipo con la etiqueta tal como
        la escribe la notaría; los difuntos cierran con «ánimas del
        purgatorio» si así se pidió.
        """
        self.ensure_one()
        etiquetas = [
            ('destacada', None),
            ('vivos', 'Vivos'),
            ('salud', 'Por la salud de'),
            ('familias', 'Familias'),
            ('desaparecidos', 'Desaparecidos'),
            ('difuntos', 'Difuntos'),
            ('otros', None),
        ]
        grupos = []
        for tipo, etiqueta in etiquetas:
            lineas = self.intencion_ids.filtered(
                lambda i, t=tipo: i.tipo == t and i.imprimible())
            if not lineas:
                if tipo == 'difuntos' and self.incluir_animas and grupos:
                    grupos.append(('Difuntos', 'ánimas del purgatorio.'))
                continue
            texto = '; '.join(l.nombres.strip().rstrip(';,.')
                              for l in lineas if l.nombres)
            if tipo == 'difuntos' and self.incluir_animas:
                texto += ', ánimas del purgatorio.'
            else:
                texto += '.'
            grupos.append((etiqueta, texto))
        return grupos
