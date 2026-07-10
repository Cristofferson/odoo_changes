from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Flujo NOVADIAM: exhibición gratis → venta → taller (limpieza/verificación/
# certificado, opcionalmente personalización) → envío → inspección 72 h →
# liberación del pago. Ramas: rechazo en moderación, cancelación por
# verificación fallida y devolución (con reversión de personalizaciones).
LISTING_STATES = [
    ('draft', 'Borrador'),
    ('review', 'En revisión'),
    ('published', 'Publicado'),
    ('reserved', 'Vendido / reservado'),
    ('to_workshop', 'En tránsito a taller'),
    ('verifying', 'En verificación'),
    ('certified', 'Certificada'),
    ('personalizing', 'En personalización'),
    ('shipped', 'Enviada al comprador'),
    ('inspection', 'Inspección 72 h'),
    ('released', 'Liberada / pagada'),
    ('rejected', 'Rechazado (moderación)'),
    ('cancelled_verif', 'Cancelada: no pasó verificación'),
    ('returned', 'Devuelta'),
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nv_is_listing = fields.Boolean('Anuncio de marketplace', index=True)
    nv_seller_id = fields.Many2one(
        'marketplace.seller', string='Vendedor', index=True, ondelete='restrict',
        tracking=True)
    nv_state = fields.Selection(
        LISTING_STATES, string='Etapa', default='draft', tracking=True, copy=False)
    nv_brand = fields.Char('Marca', help='Marca de la pieza, si aplica (se coteja en taller).')
    nv_city = fields.Char('Ciudad', help='Ciudad de origen; único dato de ubicación que se publica.')
    nv_story = fields.Text(
        'Nota personal del vendedor',
        help='Opcional y siempre anónima; se muestra en el anuncio.')
    nv_size = fields.Char('Talla')
    nv_carats = fields.Float('Quilates (centro)', digits=(6, 2))
    nv_cert_type = fields.Selection([
        ('gia', 'GIA'),
        ('igi', 'IGI'),
        ('other', 'Otra certificadora'),
        ('none', 'Sin certificado'),
        ('unknown', 'Por confirmar'),
    ], string='Certificado original', default='unknown')
    nv_cert_number = fields.Char('No. de certificado')
    nv_cert_file = fields.Binary('Archivo del certificado', attachment=True)
    nv_cert_filename = fields.Char('Nombre archivo certificado')
    nv_serial = fields.Char(
        'No. de serie Novadiam', copy=False, tracking=True,
        help='Se asigna al certificar: inscrito con láser en el diamante y grabado en la joya.')
    nv_workshop_notes = fields.Text('Notas de taller')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_marketplace_website(self):
        website = self.env['website'].sudo().search(
            [('nv_is_marketplace', '=', True)], limit=1)
        if not website:
            website = self.env['website'].sudo().search(
                [('name', 'ilike', 'novadiam')], limit=1)
        return website or self.env['website'].sudo().search([], limit=1)

    def _bind_to_marketplace(self):
        """Amarra el producto al website y compañía del marketplace para no
        contaminar catálogos/POS de las demás compañías de la BD."""
        website = self._get_marketplace_website()
        vals = {}
        if website:
            vals['website_id'] = website.id
            if website.company_id:
                vals['company_id'] = website.company_id.id
        if vals:
            self.write(vals)

    # ------------------------------------------------------------------
    # Moderación
    # ------------------------------------------------------------------
    def action_submit_review(self):
        self.filtered(lambda l: l.nv_state in ('draft', 'rejected')).write(
            {'nv_state': 'review'})

    def action_publish_listing(self):
        for rec in self:
            if not rec.nv_seller_id:
                raise UserError(_('El anuncio no tiene vendedor asignado.'))
            if rec.list_price <= 0:
                raise UserError(_('El anuncio necesita un precio de venta.'))
            rec._bind_to_marketplace()
            rec.write({'nv_state': 'published', 'is_published': True})

    def action_reject_listing(self):
        self.write({'nv_state': 'rejected', 'is_published': False})

    def action_unpublish_listing(self):
        self.write({'nv_state': 'review', 'is_published': False})

    # ------------------------------------------------------------------
    # Post-venta (el disparo automático desde la orden llega en F4c;
    # mientras, el equipo opera estas etapas desde el kanban)
    # ------------------------------------------------------------------
    def action_mark_reserved(self):
        self.write({'nv_state': 'reserved', 'is_published': False})

    def action_send_to_workshop(self):
        self.write({'nv_state': 'to_workshop'})

    def action_receive_workshop(self):
        self.write({'nv_state': 'verifying'})

    def action_certify(self):
        for rec in self:
            if not rec.nv_serial:
                raise UserError(_(
                    'Asigna primero el No. de serie Novadiam (inscripción '
                    'láser) para poder certificar la pieza.'))
            rec.write({'nv_state': 'certified'})

    def action_personalize(self):
        self.write({'nv_state': 'personalizing'})

    def action_ship(self):
        self.filtered(
            lambda l: l.nv_state in ('certified', 'personalizing')).write(
            {'nv_state': 'shipped'})

    def action_start_inspection(self):
        self.write({'nv_state': 'inspection'})

    def action_release(self):
        self.write({'nv_state': 'released'})

    def action_cancel_verification(self):
        """La pieza no corresponde a lo publicado: reembolso al comprador y
        devolución al vendedor."""
        self.write({'nv_state': 'cancelled_verif', 'is_published': False})

    def action_mark_returned(self):
        self.write({'nv_state': 'returned', 'is_published': False})
