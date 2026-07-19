from odoo import api, fields, models

MESES_MIN = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
             'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

TIPOS_PARTIDA = [
    ('bautismo', 'Bautismo'),
    ('comunion', '1.ª Comunión'),
    ('confirmacion', 'Confirmación'),
    ('matrimonio', 'Matrimonio'),
]

LIBROS = {
    'bautismo': 'Libro de Bautismos',
    'comunion': 'Libro de Comuniones',
    'confirmacion': 'Libro de Confirmaciones',
    'matrimonio': 'Libro de Matrimonios',
}


def fecha_larga(f):
    """«4 de junio de 1995» a partir de un date."""
    if not f:
        return ''
    return '%d de %s de %d' % (f.day, MESES_MIN[f.month - 1], f.year)


class ParroquiaPartida(models.Model):
    _name = 'parroquia.partida'
    _description = 'Partida sacramental (asiento en libro)'
    _inherit = ['mail.thread']
    _order = 'tipo, libro, hoja, partida'
    _rec_name = 'display_name'

    tipo = fields.Selection(TIPOS_PARTIDA, string='Sacramento',
                            required=True, default='bautismo', index=True)

    # Referencia en el archivo parroquial
    libro = fields.Char(string='Libro', tracking=True)
    hoja = fields.Char(string='Hoja No.', tracking=True)
    partida = fields.Char(string='Partida', tracking=True)
    partida_ubicacion = fields.Char(
        string='Ubicación de la partida',
        help='Como se cita en el libro: «Al Margen», «Al Centro», etc.')

    # Persona(s)
    nombre = fields.Char(string='Nombre', required=True, tracking=True,
                         help='Bautizado, comulgante, confirmado o primer '
                              'contrayente.')
    conyuge = fields.Char(string='Cónyuge',
                          help='Segundo contrayente (solo matrimonio).')
    padre = fields.Char(string='Padre')
    madre = fields.Char(string='Madre')
    padrinos = fields.Char(
        string='Padrino(s)',
        help='Tal como deben imprimirse: «Roberto Jiménez García y '
             'Magdalena Jaramillo Álvarez».')

    # Datos del sacramento
    fecha_sacramento = fields.Date(string='Fecha del sacramento',
                                   tracking=True)
    lugar_sacramento = fields.Char(string='Lugar del sacramento',
                                   default='Santa Clara del Cobre, Mich.')
    ministro = fields.Char(
        string='Ministro',
        help='Sacerdote u obispo que administró el sacramento, como debe '
             'imprimirse: «Pbro. Carlos Alberto González Murga».')

    # Solo bautismo
    fecha_nacimiento = fields.Date(string='Fecha de nacimiento')
    lugar_nacimiento = fields.Char(string='Lugar de nacimiento')

    # Solo confirmación (referencia a su bautismo)
    fecha_bautismo = fields.Date(string='Fecha del bautismo')
    lugar_bautismo = fields.Char(string='Lugar del bautismo')

    notas_marginales = fields.Text(string='Notas marginales',
                                   default='Ninguna.')
    partner_id = fields.Many2one('res.partner', string='Contacto',
                                 help='Contacto en Odoo (opcional).')
    company_id = fields.Many2one('res.company', string='Compañía',
                                 default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    @api.depends('tipo', 'nombre', 'conyuge', 'libro', 'partida')
    def _compute_display_name(self):
        tipos = dict(TIPOS_PARTIDA)
        for rec in self:
            nombre = rec.nombre or ''
            if rec.tipo == 'matrimonio' and rec.conyuge:
                nombre = '%s y %s' % (nombre, rec.conyuge)
            rec.display_name = '%s · %s (L.%s P.%s)' % (
                tipos.get(rec.tipo, ''), nombre, rec.libro or '?',
                rec.partida or '?')

    # ------- ayudas para el certificado QWeb -------

    def nombre_libro(self):
        self.ensure_one()
        return LIBROS.get(self.tipo, 'Libro')

    def padres_texto(self):
        """«Leodegario Arciga Acosta e Isaura Cázares Loera»."""
        self.ensure_one()
        partes = [p for p in (self.padre, self.madre) if p]
        if len(partes) == 2:
            conj = 'e' if partes[1][:1].upper() in ('I', 'Í') else 'y'
            return '%s %s %s' % (partes[0], conj, partes[1])
        return partes[0] if partes else ''

    def fecha_larga_sacramento(self):
        self.ensure_one()
        return fecha_larga(self.fecha_sacramento)

    def fecha_larga_nacimiento(self):
        self.ensure_one()
        return fecha_larga(self.fecha_nacimiento)

    def fecha_larga_bautismo(self):
        self.ensure_one()
        return fecha_larga(self.fecha_bautismo)

    def fecha_emision_texto(self):
        """«a 6 de julio del año 2026» con la fecha de impresión."""
        hoy = fields.Date.context_today(self)
        return 'a %d del mes de %s del año %d' % (
            hoy.day, MESES_MIN[hoy.month - 1], hoy.year)
