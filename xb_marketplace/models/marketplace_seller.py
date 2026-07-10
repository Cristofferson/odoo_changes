from odoo import api, fields, models


class MarketplaceSeller(models.Model):
    _name = 'marketplace.seller'
    _description = 'Vendedor del marketplace'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner', string='Contacto', required=True, ondelete='restrict',
        index=True, tracking=True)
    name = fields.Char(related='partner_id.name', store=True)
    state = fields.Selection([
        ('new', 'Nuevo'),
        ('approved', 'Aprobado'),
        ('suspended', 'Suspendido'),
    ], default='new', required=True, tracking=True, string='Estatus')
    city = fields.Char('Ciudad', help='Único dato de ubicación visible en los anuncios.')
    identity_verified = fields.Boolean(
        'Identidad verificada', tracking=True,
        help='Identidad cotejada por el equipo Novadiam (INE / comprobante).')
    payout_bank = fields.Char('Banco para depósito')
    payout_clabe = fields.Char('CLABE para depósito')
    notes = fields.Text('Notas internas')
    listing_ids = fields.One2many('product.template', 'nv_seller_id', string='Anuncios')
    listing_count = fields.Integer(compute='_compute_listing_count')

    _sql_constraints = [
        ('partner_uniq', 'unique(partner_id)', 'Este contacto ya tiene ficha de vendedor.'),
    ]

    @api.depends('listing_ids')
    def _compute_listing_count(self):
        for rec in self:
            rec.listing_count = len(rec.listing_ids)

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_suspend(self):
        self.write({'state': 'suspended'})
        self.listing_ids.filtered(
            lambda l: l.nv_state == 'published').action_unpublish_listing()

    def action_view_listings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'xb_marketplace.action_marketplace_listings')
        action['domain'] = [('nv_seller_id', '=', self.id)]
        action['context'] = {'default_nv_seller_id': self.id, 'default_nv_is_listing': True}
        return action
