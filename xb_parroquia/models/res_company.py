from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    xb_parroco = fields.Char(
        string='Párroco',
        default='Pbro. José Antonio Rodríguez Ortiz',
        help='Nombre que firma los certificados sacramentales.')
    xb_direccion_membrete = fields.Char(
        string='Membrete (dirección)',
        default='Portal Matamoros No. 8 Centro, CP. 61800',
        help='Línea de dirección del encabezado de los certificados.')
    xb_firma = fields.Image(
        string='Firma del párroco',
        max_width=1024, max_height=1024,
        help='Firma escaneada que se imprime sobre la línea de firma de los '
             'certificados sacramentales.')
