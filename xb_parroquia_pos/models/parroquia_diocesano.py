"""Clasificación diocesana, egresos y recibos foliados de la parroquia."""
from datetime import timedelta

import pytz

from odoo import api, fields, models

TZ = 'America/Mexico_City'

CATEGORIAS_INGRESO = [
    ('celebraciones', 'Celebraciones de culto'),
    ('derechos', 'Derechos y servicios parroquiales'),
    ('limosnas', 'Limosnas'),
    ('colectas', 'Colectas'),
    ('diezmo', 'Diezmo'),
    ('articulos', 'Artículos religiosos'),
    ('otros', 'Otros'),
]

CATEGORIAS_EGRESO = [
    ('administrativos', 'Gastos administrativos'),
    ('pastorales', 'Gastos pastorales y de culto'),
    ('personal', 'Gastos de personal'),
    ('custodia', 'Fondos en custodia'),
]

UNIDADES = ['', 'UN', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE',
            'OCHO', 'NUEVE']
DECENAS = ['DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS',
           'DIECISIETE', 'DIECIOCHO', 'DIECINUEVE']
DECENAS2 = ['', '', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA',
            'SETENTA', 'OCHENTA', 'NOVENTA']
CENTENAS = ['', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS',
            'QUINIENTOS', 'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS',
            'NOVECIENTOS']


def _tres_cifras(n):
    if n == 0:
        return ''
    if n == 100:
        return 'CIEN'
    c, resto = divmod(n, 100)
    partes = [CENTENAS[c]] if c else []
    if resto:
        if resto < 10:
            partes.append(UNIDADES[resto])
        elif resto < 20:
            partes.append(DECENAS[resto - 10])
        elif resto < 30:
            partes.append('VEINTE' if resto == 20 else
                          'VEINTI' + UNIDADES[resto - 20].lower().upper())
        else:
            d, u = divmod(resto, 10)
            partes.append(DECENAS2[d] + (' Y ' + UNIDADES[u] if u else ''))
    return ' '.join(partes)


def monto_en_letra(monto):
    """«DOCE MIL OCHOCIENTOS PESOS 00/100 M.N.» al estilo del recibo."""
    entero = int(monto)
    centavos = int(round((monto - entero) * 100))
    if entero == 0:
        letras = 'CERO'
    else:
        millones, resto = divmod(entero, 1000000)
        miles, unidades = divmod(resto, 1000)
        partes = []
        if millones:
            partes.append('UN MILLÓN' if millones == 1
                          else _tres_cifras(millones) + ' MILLONES')
        if miles:
            partes.append('MIL' if miles == 1
                          else _tres_cifras(miles) + ' MIL')
        if unidades:
            partes.append(_tres_cifras(unidades))
        letras = ' '.join(partes)
    peso = 'PESO' if entero == 1 else 'PESOS'
    return '%s %s %02d/100 M.N.' % (letras, peso, centavos)


class ProductTemplateDiocesano(models.Model):
    _inherit = 'product.template'

    xb_categoria_diocesana = fields.Selection(
        CATEGORIAS_INGRESO, string='Categoría diocesana',
        default='otros',
        help='Columna del informe mensual de la Diócesis de Tacámbaro en la '
             'que se clasifica lo cobrado con este producto.')


class ParroquiaEgreso(models.Model):
    _name = 'parroquia.egreso'
    _description = 'Egreso de la parroquia'
    _order = 'fecha desc, id desc'

    fecha = fields.Date(string='Fecha', required=True,
                        default=fields.Date.context_today, index=True)
    concepto = fields.Char(string='Concepto', required=True)
    categoria = fields.Selection(CATEGORIAS_EGRESO, string='Categoría',
                                 required=True, default='administrativos')
    monto = fields.Monetary(string='Monto', required=True)
    referencia = fields.Char(string='Folio / factura',
                             help='Folio de la nota o factura (opcional).')
    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company',
                                 default=lambda self: self.env.company)


class ParroquiaRecibo(models.Model):
    _name = 'parroquia.recibo'
    _description = 'Recibo de ingresos foliado'
    _order = 'folio desc'
    _rec_name = 'folio'

    folio = fields.Char(string='Folio', readonly=True, copy=False,
                        default='Nuevo')
    fecha = fields.Date(string='Fecha', required=True,
                        default=fields.Date.context_today)
    periodo_desde = fields.Date(string='Periodo desde')
    periodo_hasta = fields.Date(string='Periodo hasta')
    recibido_de = fields.Char(string='Recibí de', required=True,
                              default='LOS FIELES DE LA PARROQUIA')
    linea_ids = fields.One2many('parroquia.recibo.linea', 'recibo_id',
                                string='Conceptos')
    total = fields.Monetary(string='Bueno por', compute='_compute_total',
                            store=True)
    currency_id = fields.Many2one('res.currency',
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company',
                                 default=lambda self: self.env.company)

    @api.depends('linea_ids.monto')
    def _compute_total(self):
        for rec in self:
            rec.total = sum(rec.linea_ids.mapped('monto'))

    def total_en_letra(self):
        self.ensure_one()
        return monto_en_letra(self.total)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('folio', 'Nuevo') == 'Nuevo':
                vals['folio'] = self.env['ir.sequence'].next_by_code(
                    'parroquia.recibo') or '/'
        return super().create(vals_list)


class ParroquiaReciboLinea(models.Model):
    _name = 'parroquia.recibo.linea'
    _description = 'Concepto del recibo de ingresos'

    recibo_id = fields.Many2one('parroquia.recibo', required=True,
                                ondelete='cascade')
    concepto = fields.Char(string='Concepto', required=True)
    monto = fields.Monetary(string='Monto', required=True)
    currency_id = fields.Many2one(related='recibo_id.currency_id')


class ParroquiaInformeDatos(models.AbstractModel):
    """Agrupa las ventas POS pagadas y los egresos por día y categoría."""
    _name = 'parroquia.informe.datos'
    _description = 'Datos del informe diocesano'

    @api.model
    def _dia_local(self, dt):
        return dt.replace(tzinfo=pytz.utc).astimezone(
            pytz.timezone(TZ)).date()

    @api.model
    def lineas_pos(self, desde, hasta):
        """Líneas POS pagadas del rango [desde, hasta] en día local MX."""
        tz = pytz.timezone(TZ)
        ini = tz.localize(fields.Datetime.to_datetime(
            fields.Date.to_string(desde))).astimezone(pytz.utc)
        fin = tz.localize(fields.Datetime.to_datetime(
            fields.Date.to_string(hasta)) + timedelta(days=1)
        ).astimezone(pytz.utc)
        return self.env['pos.order.line'].search([
            ('order_id.state', 'in', ('paid', 'done', 'invoiced')),
            ('order_id.date_order', '>=', ini.replace(tzinfo=None)),
            ('order_id.date_order', '<', fin.replace(tzinfo=None)),
        ])

    @api.model
    def ingresos(self, desde, hasta):
        """[{fecha, concepto, categoria, monto}] ordenado por fecha."""
        filas = {}
        for linea in self.lineas_pos(desde, hasta):
            dia = self._dia_local(linea.order_id.date_order)
            prod = linea.product_id.product_tmpl_id
            clave = (dia, prod.id)
            fila = filas.setdefault(clave, {
                'fecha': dia,
                'producto': prod.name,
                'categoria': prod.xb_categoria_diocesana or 'otros',
                'cantidad': 0.0,
                'monto': 0.0,
            })
            fila['cantidad'] += linea.qty
            fila['monto'] += linea.price_subtotal_incl
        out = []
        for fila in sorted(filas.values(), key=lambda f: (f['fecha'],
                                                          f['producto'])):
            n = fila['cantidad']
            cant = ('%d' % n) if n == int(n) else ('%.2f' % n)
            fila['concepto'] = ('%s × %s' % (cant, fila['producto'])
                                if n != 1 else fila['producto'])
            out.append(fila)
        return out

    @api.model
    def totales_ingresos(self, desde, hasta):
        tot = {clave: 0.0 for clave, _et in CATEGORIAS_INGRESO}
        for fila in self.ingresos(desde, hasta):
            tot[fila['categoria']] += fila['monto']
        tot['suma'] = sum(tot.values())
        return tot

    @api.model
    def egresos(self, desde, hasta):
        return self.env['parroquia.egreso'].search([
            ('fecha', '>=', desde), ('fecha', '<=', hasta)],
            order='fecha, id')

    @api.model
    def totales_egresos(self, desde, hasta):
        tot = {clave: 0.0 for clave, _et in CATEGORIAS_EGRESO}
        for egreso in self.egresos(desde, hasta):
            tot[egreso.categoria] += egreso.monto
        tot['suma'] = sum(tot.values())
        return tot
