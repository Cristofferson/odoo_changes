# -*- coding: utf-8 -*-
import logging
import secrets
import string

from datetime import datetime, timedelta

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class XiboThanksRender(models.Model):
    """Temporary render cache for POS Thank-You HTML pages.

    Architecture
    ------------
    Instead of pushing a row to a Xibo DataSet (which the player caches and
    refreshes only every N minutes — causing the on-screen message to lag
    behind the AI), we publish the message into THIS table and serve it
    fresh on every HTTP request from the Xibo player.

    Flow:
      1. ``pos.order._xibo_send_thanks`` creates a record here with the
         message body and contextual data.
      2. The connector sends an XMR ``changeLayout`` to the target screen.
      3. The Xibo player loads a Webpage widget pointing at the URL
         ``/xibo/thanks/<config_id>`` (one URL per POS config — stable, so
         the player widget can be saved once and never edited again).
      4. The HTTP controller looks up the most recent active record for
         that config_id, renders the chosen preset with the data, and
         returns ``Cache-Control: no-cache`` so the player does NOT cache.

    Records older than ``expires_at`` (default: 60s) are considered stale
    and ignored by the controller. A daily cron deletes them to keep the
    table small.

    Why one record per config (not per token)
    -----------------------------------------
    Using a token-per-message would require dynamically updating the
    Webpage widget URL on every sale (Xibo doesn't easily support that).
    Using ``config_id`` keeps the widget URL static while still allowing
    one independent Thanks stream per POS config (you can have many).
    """
    _name = 'xibo.thanks.render'
    _description = 'Xibo POS Thank-You Render Cache'
    _order = 'create_date desc'
    _rec_name = 'config_id'

    config_id = fields.Many2one(
        'pos.config', string='POS Config', required=True,
        ondelete='cascade', index=True,
        help="Each POS config has its own Thank-You stream.",
    )
    order_id = fields.Many2one(
        'pos.order', string='POS Order',
        ondelete='set null',
        help="The order that triggered this render. Kept for audit only.",
    )
    message = fields.Text(
        string='Message', required=True,
        help="The Thank-You message body (AI-generated or fallback).",
    )
    customer_name = fields.Char(string='Customer Name')
    top_product = fields.Char(string='Top Product')
    top_product_image_url = fields.Char(
        string='Top Product Image URL',
        help="Absolute URL to the largest product's image, or empty.",
    )
    amount_total = fields.Float(string='Order Total')
    currency_code = fields.Char(string='Currency Code')
    expires_at = fields.Datetime(
        string='Expires At', required=True, index=True,
        help="UTC datetime after which this render is no longer served.",
    )

    # Snapshot of the rendering config (so future cron cleanups don't have
    # to re-read the pos.config to know how to render — also future-proofs
    # against config edits between create and serve).
    preset = fields.Selection([
        ('minimal', 'Minimal'),
        ('warm', 'Warm'),
        ('bold', 'Bold'),
        ('custom', 'Custom HTML'),
    ], string='Preset', default='minimal', required=True)
    custom_html = fields.Html(
        string='Custom HTML',
        sanitize=False,
        help="Used when preset='custom'. Snapshot of the user's template "
             "at render time.",
    )
    show_product_image = fields.Boolean(string='Show Product Image')

    # Audio snapshot (since v19.0.1.5.31). We snapshot the resolved URL,
    # not the preset name, so that even if the addon's static folder
    # changes between publish and serve, the on-screen sound stays
    # consistent for any in-flight render.
    audio_url = fields.Char(
        string='Audio URL',
        help="Absolute URL to the audio file to play, or empty when audio "
             "is disabled. Snapshotted at publish time.",
    )
    audio_volume = fields.Float(
        string='Audio Volume',
        default=0.8,
        help="Audio volume normalised to [0.0, 1.0] for HTML5 <audio>.",
    )

    @api.model
    def _gc_expired(self, batch_size=500):
        """Delete renders that expired more than 1 hour ago. Called by cron.

        We keep them for 1 hour past expiry to help debugging: if a sale
        looks wrong on screen, you have a brief window to check what was
        actually published.
        """
        cutoff = fields.Datetime.now() - timedelta(hours=1)
        stale = self.sudo().search(
            [('expires_at', '<', cutoff)], limit=batch_size,
        )
        if stale:
            count = len(stale)
            stale.unlink()
            _logger.info("[XIBO POS THANKS] GC removed %s expired render(s)", count)
        return True

    @api.model
    def _create_for_order(self, config, order, message, ctx, ttl_seconds=60):
        """Convenience factory called from ``pos.order._xibo_send_thanks``.

        :param config: the ``pos.config`` driving the broadcast.
        :param order:  the ``pos.order`` that triggered it.
        :param message: the final message text to display (AI or fallback).
        :param ctx: the context dict produced by
                    ``pos.order._xibo_collect_thanks_context`` (carries
                    customer_name, top_product, top_product_id, total,
                    currency).
        :param ttl_seconds: how long this render stays "fresh" — should be
                            >= ``config.xibo_thanks_duration`` so the
                            Webpage widget always finds a valid record
                            during its display window.
        :returns: the new ``xibo.thanks.render`` recordset.
        """
        # Resolve product image URL: use the image_1024 of the top product
        # if available. We compose an absolute URL using the system's
        # ``web.base.url`` so the Xibo player (outside the LAN) can reach it.
        top_product_image_url = ''
        top_product_id = ctx.get('top_product_id')
        if top_product_id:
            ICP = self.env['ir.config_parameter'].sudo()
            base_url = (ICP.get_param('web.base.url') or '').rstrip('/')
            if base_url:
                top_product_image_url = (
                    f"{base_url}/web/image/product.product/"
                    f"{top_product_id}/image_1024"
                )

        currency_code = ''
        if order and order.currency_id:
            currency_code = order.currency_id.name or ''
        elif config and config.currency_id:
            currency_code = config.currency_id.name or ''

        # Audio snapshot (since v19.0.1.5.31). Resolve at publish time so the
        # served HTML is self-contained: no further calls into pos.config.
        audio_url = ''
        audio_volume = 0.8
        try:
            audio_url = config._xibo_resolve_audio_url()
            audio_volume = config._xibo_resolve_audio_volume()
        except Exception:
            # Audio is a non-essential nicety; if resolution fails for any
            # reason, the Thank-You still works in silence.
            _logger.exception(
                "[XIBO POS THANKS] could not resolve audio settings for "
                "config %s — falling back to silent",
                getattr(config, 'id', '?'),
            )

        vals = {
            'config_id': config.id,
            'order_id': order.id if order else False,
            'message': message,
            'customer_name': ctx.get('customer_name') or '',
            'top_product': ctx.get('top_product') or '',
            'top_product_image_url': top_product_image_url,
            'amount_total': ctx.get('total') or (order.amount_total if order else 0.0),
            'currency_code': currency_code,
            'expires_at': fields.Datetime.now() + timedelta(seconds=ttl_seconds),
            'preset': config.xibo_thanks_preset or 'minimal',
            'custom_html': config.xibo_thanks_custom_html or '',
            'show_product_image': bool(config.xibo_thanks_show_product_image),
            'audio_url': audio_url,
            'audio_volume': audio_volume,
        }
        return self.sudo().create(vals)
