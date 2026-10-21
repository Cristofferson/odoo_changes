from odoo import api, fields, models, _


class ResPartner(models.Model):
    """El vendedor del marketplace vive en su propio modelo, pero siempre
    cuelga de un contacto. Esto hace que desde el contacto se vea —y se llegue
    a— su ficha de vendedor, en vez de que el marketplace parezca un mundo
    aparte."""
    _inherit = 'res.partner'

    nv_seller_ids = fields.One2many(
        'marketplace.seller', 'partner_id', string='Ficha de vendedor Novadiam')
    nv_seller_count = fields.Integer(compute='_compute_nv_counts')
    nv_listing_count = fields.Integer(
        string='Anuncios en Novadiam', compute='_compute_nv_counts')

    @api.depends('nv_seller_ids', 'nv_seller_ids.listing_ids')
    def _compute_nv_counts(self):
        for partner in self:
            partner.nv_seller_count = len(partner.nv_seller_ids)
            partner.nv_listing_count = sum(
                len(seller.listing_ids) for seller in partner.nv_seller_ids)

    def action_nv_open_seller(self):
        self.ensure_one()
        seller = self.nv_seller_ids[:1]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendedor Novadiam'),
            'res_model': 'marketplace.seller',
            'view_mode': 'form',
            'res_id': seller.id,
            'target': 'current',
        }
