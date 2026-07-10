from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    nv_has_listing = fields.Boolean(
        'Orden de marketplace', compute='_compute_nv_has_listing', store=True)

    @api.depends('order_line.product_id')
    def _compute_nv_has_listing(self):
        for order in self:
            order.nv_has_listing = any(
                order.order_line.product_id.product_tmpl_id.mapped('nv_is_listing'))

    def _nv_listings(self):
        return self.order_line.product_id.product_tmpl_id.filtered('nv_is_listing')

    def action_confirm(self):
        for order in self:
            for listing in order._nv_listings():
                if listing.nv_state != 'published' \
                        and listing.nv_sale_order_id != order:
                    raise UserError(_(
                        'La pieza "%s" ya no está disponible (cada anuncio '
                        'es una pieza única).', listing.name))
        res = super().action_confirm()
        for order in self:
            to_reserve = order._nv_listings().filtered(
                lambda l: l.nv_state == 'published')
            if to_reserve:
                to_reserve.sudo().action_mark_reserved(order=order)
                order.message_post(body=_(
                    'Marketplace: pieza(s) reservada(s) — %s. Sigue: guía '
                    'del vendedor al taller.',
                    ', '.join(to_reserve.mapped('name'))))
        return res

    def _action_cancel(self):
        for order in self:
            reserved = order._nv_listings().filtered(
                lambda l: l.nv_state == 'reserved'
                and l.nv_sale_order_id == order)
            if reserved:
                reserved.sudo().write({
                    'nv_state': 'published',
                    'is_published': True,
                    'nv_sale_order_id': False,
                    'nv_sold_price': 0.0,
                })
                for listing in reserved:
                    listing.message_post(body=_(
                        'Orden %s cancelada: la pieza vuelve al catálogo.',
                        order.name))
        return super()._action_cancel()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.constrains('product_id', 'product_uom_qty')
    def _check_nv_listing_available(self):
        for line in self:
            tmpl = line.product_id.product_tmpl_id
            if not tmpl.nv_is_listing:
                continue
            if line.product_uom_qty > 1:
                raise ValidationError(_(
                    'La pieza "%s" es única: solo puede llevarse una.',
                    tmpl.name))
            if line.order_id.state in ('draft', 'sent') \
                    and tmpl.nv_state != 'published' \
                    and tmpl.nv_sale_order_id != line.order_id:
                raise ValidationError(_(
                    'La pieza "%s" ya no está disponible.', tmpl.name))
