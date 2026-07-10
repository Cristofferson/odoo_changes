from odoo import fields, models
from odoo.fields import Domain


class Website(models.Model):
    _inherit = 'website'

    nv_is_marketplace = fields.Boolean(
        'Sitio marketplace',
        help='En este sitio la tienda muestra únicamente anuncios publicados '
             'del marketplace (nada del catálogo general de la BD).')

    def sale_product_domain(self):
        domain = super().sale_product_domain()
        website = self.get_current_website()
        if website.nv_is_marketplace:
            domain = Domain.AND([domain, [
                ('nv_is_listing', '=', True),
                ('nv_state', '=', 'published'),
            ]])
        return domain
