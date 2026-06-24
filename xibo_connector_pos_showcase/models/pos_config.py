# -*- coding: utf-8 -*-
# =============================================================================
# Videowall Showcase (since v1.6.0)
# =============================================================================
# Ambient/idle content for the counter videowall: a rotating gallery of the
# online catalog plus a QR code that opens the web store on the customer's
# phone ("Escanea y arma tu selección"). Reuses the same idea as the Thank-You
# page — a self-contained HTML page served by Odoo that the Xibo Webpage widget
# loads — but for the idle layout instead of the post-sale layout.
# =============================================================================
import logging
import random

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PosConfigShowcase(models.Model):
    _inherit = 'pos.config'

    xibo_showcase_enabled = fields.Boolean(
        string='Enable Videowall Showcase', default=False,
        help="When idle, show a rotating catalog gallery + a QR that opens the "
             "online store on the customer's phone.",
    )
    xibo_showcase_url = fields.Char(
        string='Catalog URL (QR target)',
        help="Where the QR sends the customer. Leave empty to use this server's "
             "online shop (/shop).",
    )
    xibo_showcase_category_id = fields.Many2one(
        'product.public.category', string='Showcase Category',
        help="Optional: only feature pieces from this eCommerce category. "
             "Empty = all published products.",
    )
    xibo_showcase_count = fields.Integer(
        string='Pieces to Rotate', default=12,
        help="How many catalog pieces to cycle through on screen.",
    )
    xibo_showcase_interval = fields.Integer(
        string='Seconds per Piece', default=6,
        help="How long each piece stays on screen before the next one.",
    )
    xibo_showcase_heading = fields.Char(
        string='Call to Action', default='Escanea y arma tu selección',
        help="Text shown next to the QR code.",
    )
    xibo_showcase_order = fields.Selection(
        [('price_desc', 'Most exclusive first (price high → low)'),
         ('curated', 'Curated (website order)'),
         ('price_asc', 'Price low → high'),
         ('newest', 'Newest first'),
         ('random', 'Random each load')],
        string='Showcase Order', default='price_desc',
        help="How to pick and order the pieces on screen.",
    )
    xibo_showcase_widget_url = fields.Char(
        string='Showcase Webpage URL', compute='_compute_xibo_showcase_widget_url',
        help="Paste this into the Xibo Webpage widget of the idle/showcase layout.",
    )

    @api.depends('xibo_showcase_enabled')
    def _compute_xibo_showcase_widget_url(self):
        base_url = (self.env['ir.config_parameter'].sudo()
                    .get_param('web.base.url') or '').rstrip('/')
        for rec in self:
            rec.xibo_showcase_widget_url = (
                "%s/xibo/showcase/%s" % (base_url, rec.id)
                if base_url and rec.id else False
            )

    def _xibo_showcase_qr_target(self):
        """Resolve the URL the QR points to (config override or /shop)."""
        self.ensure_one()
        if self.xibo_showcase_url:
            return self.xibo_showcase_url
        base_url = (self.env['ir.config_parameter'].sudo()
                    .get_param('web.base.url') or '').rstrip('/')
        return (base_url + '/shop') if base_url else ''

    _SHOWCASE_ORDER_MAP = {
        'price_desc': 'list_price desc, id desc',
        'curated': 'website_sequence asc, id desc',
        'price_asc': 'list_price asc, id desc',
        'newest': 'id desc',
    }

    def _xibo_showcase_products(self):
        """Pick the catalog pieces to feature: published, priced, with an image,
        optionally limited to one eCommerce category, in the configured order."""
        self.ensure_one()
        count = max(self.xibo_showcase_count or 12, 1)
        domain = [('is_published', '=', True), ('list_price', '>', 0)]
        if self.xibo_showcase_category_id:
            domain.append(
                ('public_categ_ids', 'child_of', self.xibo_showcase_category_id.id))
        Product = self.env['product.template'].sudo()
        order = self.xibo_showcase_order or 'price_desc'
        if order == 'random':
            pool = Product.search(domain, order='id desc', limit=max(count * 6, 30))
            ids = pool.filtered(lambda p: p.image_512).ids
            random.shuffle(ids)
            return Product.browse(ids[:count])
        # Pull a slightly larger pool, keep only those with an image, then cap.
        search_order = self._SHOWCASE_ORDER_MAP.get(order, 'list_price desc, id desc')
        pool = Product.search(domain, order=search_order, limit=count * 3)
        return pool.filtered(lambda p: p.image_512)[:count]
