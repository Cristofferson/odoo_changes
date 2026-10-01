# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    xb_wa_cart_sent = fields.Datetime('Aviso de carrito enviado por WhatsApp', copy=False, readonly=True)
    xb_wa_cart_product = fields.Char('Producto del carrito', compute='_compute_xb_wa_cart')
    xb_wa_cart_url = fields.Char('Liga del producto del carrito', compute='_compute_xb_wa_cart')

    def _compute_xb_wa_cart(self):
        for order in self:
            line = order.order_line.filtered(lambda l: not l.display_type and not l.is_delivery
                                             and l.product_id.type != 'service')[:1]
            tmpl = line.product_id.product_tmpl_id
            order.xb_wa_cart_product = tmpl.name or ''
            base = order.website_id.domain or order.get_base_url()
            order.xb_wa_cart_url = (base.rstrip('/') + tmpl.website_url) if tmpl and tmpl.website_url else base

    @api.model
    def _cron_xb_wa_abandoned_cart(self):
        """Una sola vez por carrito, solo clientes identificados con teléfono, dentro de 48 h."""
        now = fields.Datetime.now()
        for website in self.env['website'].sudo().search([('xb_wa_cart_enabled', '=', True),
                                                         ('xb_wa_cart_template_id', '!=', False)]):
            tmpl = website.xb_wa_cart_template_id
            if tmpl.status != 'approved':
                continue
            public = website.user_id.partner_id
            delay = max(website.xb_wa_cart_delay_hours, 1)
            orders = self.sudo().search([
                ('website_id', '=', website.id), ('state', '=', 'draft'),
                ('xb_wa_cart_sent', '=', False), ('partner_id', '!=', public.id),
                ('write_date', '<=', now - timedelta(hours=delay)),
                ('write_date', '>=', now - timedelta(hours=48)),
                ('order_line', '!=', False),
            ], limit=50)
            for order in orders:
                partner = order.partner_id
                phone = partner.phone or (partner.mobile if 'mobile' in partner._fields else False)
                if not phone or not order.xb_wa_cart_product:
                    continue
                # ¿ya compró algo después? entonces no se le molesta
                if self.sudo().search_count([('partner_id', '=', order.partner_id.id), ('website_id', '=', website.id),
                                             ('state', '=', 'sale'), ('date_order', '>=', order.create_date)]):
                    order.xb_wa_cart_sent = now
                    continue
                order.xb_wa_cart_sent = now  # marcar ANTES: nunca dos avisos aunque falle el envío
                try:
                    composer = self.env['whatsapp.composer'].sudo().with_company(order.company_id).with_context(
                        active_model='sale.order', active_id=order.id, default_wa_template_id=tmpl.id,
                    ).create({'phone': phone, 'wa_template_id': tmpl.id, 'res_model': 'sale.order'})
                    composer._send_whatsapp_template()
                    order.message_post(body='Aviso de carrito abandonado enviado por WhatsApp.',
                                       message_type='comment', subtype_xmlid='mail.mt_note')
                except Exception:  # noqa: BLE001
                    _logger.exception('xb_whatsapp_web_leads: no se pudo avisar el carrito %s', order.name)
                self.env.cr.commit()
