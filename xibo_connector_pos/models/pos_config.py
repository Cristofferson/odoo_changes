# -*- coding: utf-8 -*-
import logging
import secrets
import uuid

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Master server pointer
    xibo_server_id = fields.Many2one(
        'xibo.server', string='Xibo Server',
        help="Xibo CMS that this POS will broadcast to.",
    )
    xibo_time_from = fields.Float(string='Active From', default=0.0)
    xibo_time_to = fields.Float(string='Active To', default=24.0)
    xibo_display_ids = fields.Many2many(
        'xibo.display', 'pos_config_xibo_display_rel',
        'config_id', 'display_id', string='Default Displays',
        domain="[('server_id', '=', xibo_server_id)]",
    )
    xibo_display_group_ids = fields.Many2many(
        'xibo.display.group', 'pos_config_xibo_display_group_rel',
        'config_id', 'group_id', string='Default Display Groups',
        domain="[('server_id', '=', xibo_server_id)]",
    )

    # ① AI Thank-You
    xibo_thanks_enabled = fields.Boolean(string='Enable AI Thank-You', default=False)
    xibo_thanks_layout_id = fields.Many2one(
        'xibo.layout', string='Thank-You Layout',
        domain="[('server_id', '=', xibo_server_id)]",
    )
    xibo_thanks_dataset_id = fields.Many2one(
        'xibo.dataset', string='Thank-You DataSet (legacy)',
        domain="[('server_id', '=', xibo_server_id)]",
        help="DEPRECATED. Only used by the legacy Camino A (Broadcast) flow. "
             "The new URL-render flow (default since 19.0.1.5.27) does not "
             "use this — it serves a fresh HTML page on every request, "
             "bypassing the player's DataSet cache.",
    )
    xibo_thanks_duration = fields.Integer(string='Display For (s)', default=15)
    xibo_thanks_min_amount = fields.Float(string='Minimum Order Total', default=0.0)
    xibo_thanks_use_ai = fields.Boolean(string='Use AI', default=True)
    xibo_thanks_ai_agent_id = fields.Many2one(
        'ai.agent', string='AI Agent',
        help="Odoo AI agent that generates the message. Empty = system default.",
    )
    xibo_thanks_ai_prompt = fields.Text(
        string='AI Prompt Template',
        default=(
            "Escribe un mensaje breve y cálido de agradecimiento "
            "(MÁXIMO 12 palabras, una sola frase corta) para un cliente que "
            "acaba de comprar en nuestra tienda.\n\n"
            "Cliente: {customer_name}\n"
            "Producto principal: {top_product}\n"
            "Categoría: {top_category}\n"
            "Total: {total} {currency}\n\n"
            "Reglas:\n"
            "- Responde SIEMPRE en el idioma del cliente (si el nombre del "
            "cliente parece extranjero, adapta).\n"
            "- Máximo 12 palabras, una sola frase corta.\n"
            "- Si el cliente tiene nombre, úsalo.\n"
            "- Si la categoría sugiere un momento especial "
            "(boda, compromiso, bebé), reconócelo brevemente.\n"
            "- Output SOLO el mensaje. Sin comillas, sin etiquetas, sin prefijos."
        ),
    )
    xibo_thanks_fallback_text = fields.Char(
        string='Fallback Message',
        default="¡Gracias por su compra, {customer_name}!",
    )
    xibo_thanks_display_ids = fields.Many2many(
        'xibo.display', 'pos_config_xibo_thanks_display_rel',
        'config_id', 'display_id',
        string='Thank-You Target Screens',
        domain="[('server_id', '=', xibo_server_id)]",
        help="Screens that will receive the Thank-You broadcast. The Thank-You "
             "Layout on each of these screens must contain a Webpage widget "
             "pointing at this server's URL "
             "/xibo/thanks/<pos_config_id>. Leave empty to fall back to the "
             "legacy Broadcast path (Camino A) using the Default Displays.",
    )

    # ① — URL-render flow settings (since v19.0.1.5.27)
    xibo_thanks_preset = fields.Selection([
        ('minimal', 'Minimal — clean, lots of whitespace, thin typography'),
        ('warm', 'Warm — jewelry-friendly, gold accents, soft animation'),
        ('bold', 'Bold — high contrast, big text, energetic'),
        ('custom', 'Custom — paste your own HTML below'),
    ], string='Thank-You Visual Preset', default='minimal', required=True,
        help="Visual style of the Thank-You page rendered by Xibo. Each "
             "preset is a self-contained, animated HTML template tuned for "
             "digital signage. Choose 'Custom' to paste your own.")
    xibo_thanks_custom_html = fields.Html(
        string='Custom HTML Template',
        sanitize=False,
        help="Used when Visual Preset is 'Custom'. The following placeholders "
             "will be replaced at render time:\n"
             "  {{message}}, {{customer_name}}, {{top_product}}, "
             "{{product_image_url}}, {{total}}, {{currency}}, "
             "{{company_name}}, {{company_logo_url}}.\n"
             "Tip: design at 1920×1080 with a dark or branded background "
             "so it looks crisp on full-HD screens.",
    )
    xibo_thanks_show_product_image = fields.Boolean(
        string='Show Top Product Image',
        default=False,
        help="If enabled, the chosen visual preset includes a photo of the "
             "most expensive product in the order, served from this Odoo's "
             "Media library via a public URL. Has no effect on Custom HTML "
             "(use the {{product_image_url}} placeholder there).",
    )

    # ④ — Audio notification (since v19.0.1.5.31)
    xibo_thanks_audio_enabled = fields.Boolean(
        string='Enable Audio Notification',
        default=False,
        help="If enabled, the Thank-You page plays a short audio cue when it "
             "appears on the screen. The sound is played by the Xibo player's "
             "embedded browser (HTML5 audio). Volume and preset are configured "
             "below.",
    )
    xibo_thanks_audio_preset = fields.Selection([
        ('chime', 'Chime — soft bells (jewelry, premium retail)'),
        ('cash', 'Cash — register clicks and ka-ching'),
        ('success', 'Success — modern ascending beep'),
        ('bell', 'Bell — single warm "ding" (hotel reception)'),
        ('custom', 'Custom — your own audio file URL'),
    ], string='Audio Preset', default='chime',
        help="Which sound to play. Four royalty-free, synthetic presets are "
             "built in (each <25KB). Choose 'Custom' to point at your own "
             "audio file via URL — must be a publicly reachable MP3, OGG or "
             "WAV file that the Xibo player can fetch.")
    xibo_thanks_audio_custom_url = fields.Char(
        string='Custom Audio URL',
        help="Required when Audio Preset is 'Custom'. Full https:// URL to "
             "an audio file. Recommended format: MP3 mono ~96kbps, under 2 "
             "seconds. Larger files delay the audio start.",
    )
    xibo_thanks_audio_volume = fields.Integer(
        string='Audio Volume',
        default=80,
        help="Audio volume from 0 (silent) to 100 (maximum). The actual "
             "physical loudness also depends on the Video Wall's hardware "
             "volume — adjust both for the best experience. Default 80.",
    )

    # ③ Customer Display Mirror (DYNAMIC)
    xibo_customer_display_enabled = fields.Boolean(
        string='Mirror Customer Display', default=False,
    )
    xibo_customer_display_display_id = fields.Many2one(
        'xibo.display', string='Customer Display Screen',
        domain="[('server_id', '=', xibo_server_id)]",
    )
    xibo_customer_display_layout_id = fields.Many2one(
        'xibo.layout', string='Auto-Created Layout', readonly=True, copy=False,
    )
    xibo_customer_display_url = fields.Char(
        string='Customer Display URL', compute='_compute_xibo_customer_display_url',
        store=True,
    )
    xibo_customer_display_duration = fields.Integer(
        string='Mirror Duration (s)', default=0,
        help="0 = stay until cart is cleared/paid (recommended).",
    )

    # ④ Recommendations
    xibo_reco_enabled = fields.Boolean(string='Enable Contextual Recommendations', default=False)
    xibo_reco_duration = fields.Integer(string='Recommendation Display For (s)', default=20)
    xibo_reco_mode = fields.Selection(
        [('overlay', 'Overlay'), ('fullscreen', 'Full-screen')],
        default='overlay', string='Recommendation Mode',
    )
    xibo_reco_priority = fields.Selection(
        [('latest', 'Latest added wins'),
         ('most_expensive', 'Most expensive wins'),
         ('accumulate', 'Accumulate')],
        default='latest', string='Multi-product Priority',
    )
    xibo_reco_cooldown = fields.Integer(string='Cool-down (s)', default=60)
    xibo_reco_last_sent = fields.Datetime(string='Last Reco Sent', readonly=True, copy=False)
    xibo_reco_last_tag_signature = fields.Char(string='Last Tag Signature', readonly=True, copy=False)

    # A stable device_uuid that identifies the Xibo screen as a "device"
    # for the POS Customer Display websocket bus. Generated once; persists
    # across sessions so the URL stays stable.
    xibo_customer_display_device_uuid = fields.Char(
        string='Customer Display Device UUID', readonly=True, copy=False,
        help="Stable identifier used in the Customer Display URL for the Xibo screen.",
    )

    @api.depends('xibo_customer_display_device_uuid')
    def _compute_xibo_customer_display_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for rec in self:
            # Lazily allocate a stable device_uuid for the Xibo screen.
            if not rec.xibo_customer_display_device_uuid and rec.id:
                rec.xibo_customer_display_device_uuid = (
                    'xibo-' + str(uuid.uuid4())
                )
            if base_url and rec.xibo_customer_display_device_uuid:
                # Direct URL to the Odoo Customer Display, using a stable
                # device_uuid we own. Odoo does not validate device_uuid
                # against any field — it is just an identifier for the
                # browser/bus channel.
                rec.xibo_customer_display_url = (
                    f"{base_url.rstrip('/')}/pos_customer_display/{rec.id}/"
                    f"{rec.xibo_customer_display_device_uuid}"
                )
            else:
                rec.xibo_customer_display_url = False

    # ------------------------------------------------------------------
    # Thank-You URL access key (since v1.5.33)
    # ------------------------------------------------------------------
    # The public Thank-You endpoint /xibo/thanks/<id> is keyed only by the
    # (guessable) integer id. To stop anyone from reading the last customer
    # name + product, we add an OPTIONAL secret key. Enforcement is OFF by
    # default (xibo_thanks_require_token = False) so simply deploying this
    # code changes nothing: existing screens keep working with their old
    # URL. The admin updates each screen's URL to include ?key=<token>,
    # confirms it still renders, and only then flips the switch ON.
    xibo_thanks_token = fields.Char(
        string='Thank-You URL Key', readonly=True, copy=False,
        help="Secret key embedded in the Thank-You URL when 'Require key' is on.",
    )
    xibo_thanks_require_token = fields.Boolean(
        string='Require key on Thank-You URL', default=False,
        help="OFF (default): the Thank-You page works with the old URL — nothing "
             "breaks on upgrade. Turn ON only after every screen's Xibo Webpage "
             "widget URL has been updated to the one shown below (with the key); "
             "then outsiders who guess the id can no longer read it.",
    )
    xibo_thanks_url = fields.Char(
        string='Thank-You Webpage URL', compute='_compute_xibo_thanks_url',
        help="Paste this into the Xibo Webpage widget for the Thank-You screen. "
             "It already includes the access key.",
    )

    @api.depends('xibo_thanks_token')
    def _compute_xibo_thanks_url(self):
        base_url = (self.env['ir.config_parameter'].sudo()
                    .get_param('web.base.url') or '').rstrip('/')
        for rec in self:
            # Lazily allocate a stable secret key the first time the URL is
            # read (mirrors the device_uuid pattern above).
            if rec.id and not rec.xibo_thanks_token:
                rec.xibo_thanks_token = secrets.token_urlsafe(24)
            if base_url and rec.id:
                url = "%s/xibo/thanks/%s" % (base_url, rec.id)
                if rec.xibo_thanks_token:
                    url += "?key=%s" % rec.xibo_thanks_token
                rec.xibo_thanks_url = url
            else:
                rec.xibo_thanks_url = False

    # Auto-apply Customer Display Mirror on save
    def write(self, vals):
        result = super().write(vals)
        if any(k in vals for k in (
                'xibo_customer_display_enabled',
                'xibo_customer_display_display_id',
                'xibo_server_id')):
            for rec in self:
                if (rec.xibo_customer_display_enabled
                        and rec.xibo_server_id
                        and rec.xibo_customer_display_display_id):
                    try:
                        rec._xibo_ensure_customer_display_layout()
                    except Exception as e:
                        _logger.warning(
                            "Auto-apply CD Mirror failed for POS %s: %s",
                            rec.name, e)
                        # Post a visible warning in the POS chatter so the
                        # cashier/admin notices the broadcasts will not work.
                        try:
                            rec.message_post(
                                body=_(
                                    "Xibo Customer Display Mirror could not be "
                                    "auto-configured: %s. Review the Xibo Event "
                                    "Log for details and try saving again."
                                ) % e,
                                subject=_("Xibo Connector — Setup Issue"),
                            )
                        except Exception:
                            pass
        return result

    def _xibo_has_target_displays(self):
        self.ensure_one()
        return bool(self.xibo_display_ids or self.xibo_display_group_ids)

    def _xibo_within_active_window(self):
        self.ensure_one()
        if self.xibo_time_from == 0.0 and self.xibo_time_to == 24.0:
            return True
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        hour = now.hour + now.minute / 60.0
        return self.xibo_time_from <= hour <= self.xibo_time_to

    # ===== ③ Customer Display Mirror layout =====
    def _xibo_ensure_customer_display_layout(self):
        self.ensure_one()
        if not (self.xibo_customer_display_enabled and self.xibo_server_id
                and self.xibo_customer_display_display_id and self.xibo_customer_display_url):
            return False
        if self.xibo_server_id.state != 'connected':
            return False
        # Include a timestamp to guarantee uniqueness in Xibo even when
        # earlier attempts left orphan layouts behind. Xibo CMS validates
        # layout name uniqueness per owner.
        layout_name = _("POS Customer Display — %s [%s]") % (
            self.name, fields.Datetime.now().strftime('%Y%m%d-%H%M%S'),
        )
        if self.xibo_customer_display_layout_id and self.xibo_customer_display_layout_id.xibo_layout_id:
            self._xibo_update_customer_display_layout()
        else:
            layout = self._xibo_create_customer_display_layout(layout_name)
            self.sudo().write({'xibo_customer_display_layout_id': layout.id})
        return True

    def _xibo_create_customer_display_layout(self, name):
        self.ensure_one()
        server = self.xibo_server_id
        layout_resp = server._request('POST', '/api/layout', data={
            'name': name,
            'description': _("Auto-created for POS %s") % self.name,
            'resolutionId': 1,
        })
        published_layout_id = layout_resp.get('layoutId')
        campaign_id = layout_resp.get('campaignId') or 0
        if not published_layout_id:
            raise UserError(_("Xibo did not return a layoutId."))

        # In modern Xibo (3.x+), even a freshly-created layout has a
        # Published parent and a Draft child. To edit regions/widgets we
        # MUST work on the Draft. The /api/layout/checkout endpoint returns
        # the Draft layoutId we need. If the layout is *already* checked
        # out (because Xibo auto-creates a Draft on first create), the
        # response will be 422 "already checked out" — in which case we
        # find the Draft by querying for its parentId.
        draft_layout_id = self._xibo_get_or_create_draft(
            server, published_layout_id,
        )

        # Locate or create a playlist on the draft.
        detail = server._request(
            'GET', '/api/layout',
            params={'layoutId': draft_layout_id, 'embed': 'regions,playlists,widgets'},
            raise_on_error=False,
        )
        playlist_id = self._xibo_find_first_playlist(detail)

        if not playlist_id:
            region_resp = server._request(
                'POST', f'/api/region/{draft_layout_id}',
                data={
                    'type': 'playlist',
                    'width': 1920,
                    'height': 1080,
                    'top': 0,
                    'left': 0,
                },
            )
            detail = server._request(
                'GET', '/api/layout',
                params={'layoutId': draft_layout_id, 'embed': 'regions,playlists,widgets'},
                raise_on_error=False,
            )
            playlist_id = self._xibo_find_first_playlist(detail)
            if not playlist_id and isinstance(region_resp, dict):
                rp = region_resp.get('regionPlaylist') or region_resp.get('playlists')
                if isinstance(rp, list) and rp:
                    playlist_id = rp[0].get('playlistId')
                elif isinstance(rp, dict):
                    playlist_id = rp.get('playlistId')

        if not playlist_id:
            raise UserError(_(
                "Could not locate or create a playlist on the Xibo layout. "
                "Check the Xibo Event Log for the most recent API responses."
            ))

        # Step 1: Create the widget shell (modern Xibo only accepts an empty
        # body here; properties must be set via PUT in the next step).
        widget_resp = server._request(
            'POST', f'/api/playlist/widget/webpage/{playlist_id}',
        )
        widget_id = None
        if isinstance(widget_resp, dict):
            widget_id = widget_resp.get('widgetId')
        if not widget_id:
            raise UserError(_(
                "Xibo did not return a widgetId after widget creation."
            ))

        # Step 2: Populate the widget properties (URL, duration, mode).
        server._request(
            'PUT', f'/api/playlist/widget/{widget_id}',
            data={
                'name': _("POS Customer Display"),
                'uri': self.xibo_customer_display_url,
                'link': self.xibo_customer_display_url,
                'duration': 86400,
                'useDuration': 1,
                'transparency': 0,
                'modeId': 1,
            },
        )

        # Publish the layout. In Xibo, /api/layout/publish/{layoutId} expects
        # the PUBLISHED layoutId (parent), NOT the draft id. Xibo finds the
        # draft by parentId and publishes it.
        publish_resp = server._request(
            'PUT', f'/api/layout/publish/{published_layout_id}',
            data={'publishNow': 1}, raise_on_error=False,
        )
        if isinstance(publish_resp, dict) and publish_resp.get('layoutId'):
            final_layout_id = publish_resp.get('layoutId')
            final_campaign_id = publish_resp.get('campaignId') or campaign_id
        else:
            final_layout_id = published_layout_id
            final_campaign_id = campaign_id

        return self.env['xibo.layout'].sudo().create({
            'name': name,
            'server_id': server.id,
            'xibo_layout_id': final_layout_id,
            'xibo_campaign_id': final_campaign_id,
            'duration': 86400,
        })

    @staticmethod
    def _xibo_get_or_create_draft(server, published_layout_id):
        """Get the editable Draft layoutId for a Published layout.

        In Xibo 3.x+, calling /api/layout/checkout returns a 200 with the
        Draft layoutId in the response when a Draft is created. If a Draft
        already exists, Xibo returns 422 "Layout is already checked out".
        In that case, we look up the Draft by querying for parentId.
        """
        # Try to check out (creates Draft, returns the new layoutId).
        try:
            resp = server._request(
                'PUT', f'/api/layout/checkout/{published_layout_id}',
                raise_on_error=False,
            )
            if isinstance(resp, dict):
                # Successful checkout returns the Draft layout entity.
                new_id = resp.get('layoutId')
                if new_id and new_id != published_layout_id:
                    return new_id
                # Some Xibo versions echo back the same id but the Draft
                # actually has a different id; check via parentId below.
                err = resp.get('error') or resp.get('message')
                if not err:
                    # No error indicator — fall through and verify by parentId.
                    pass
        except Exception:
            pass

        # Look up the Draft by parentId (Draft with parentId == published id).
        drafts = server._request(
            'GET', '/api/layout',
            params={'parentId': published_layout_id},
            raise_on_error=False,
        )
        if isinstance(drafts, list) and drafts:
            for d in drafts:
                if d.get('publishedStatusId') == 2:  # 2 = Draft
                    return d.get('layoutId')

        # Last fallback: assume the published id itself is editable
        # (oldest Xibo behaviour).
        return published_layout_id

    def _xibo_update_customer_display_layout(self):
        self.ensure_one()
        server = self.xibo_server_id
        layout = self.xibo_customer_display_layout_id
        detail = server._request(
            'GET', '/api/layout',
            params={'layoutId': layout.xibo_layout_id, 'embed': 'regions,playlists,widgets'},
            raise_on_error=False,
        )
        widget_id = self._xibo_find_first_widget(detail)
        if not widget_id:
            new_layout = self._xibo_create_customer_display_layout(layout.name)
            self.sudo().write({'xibo_customer_display_layout_id': new_layout.id})
            return
        try:
            server._request('PUT', f'/api/layout/checkout/{layout.xibo_layout_id}', raise_on_error=False)
        except Exception:
            pass
        server._request(
            'PUT', f'/api/playlist/widget/{widget_id}',
            data={'uri': self.xibo_customer_display_url, 'duration': 86400, 'useDuration': 1},
            raise_on_error=False,
        )
        server._request(
            'PUT', f'/api/layout/publish/{layout.xibo_layout_id}',
            data={'publishNow': 1}, raise_on_error=False,
        )

    # ===== RPC: cart events from POS frontend =====
    @api.model
    def xibo_notify_cart_event(self, *args, **kwargs):
        # Find the payload dict regardless of position in args.
        # When called via RPC, args may be ([config_id], payload) or (payload,)
        # depending on the Odoo version and call convention.
        payload = None
        for arg in args:
            if isinstance(arg, dict):
                payload = arg
                break
        if payload is None:
            payload = kwargs.get('payload')
        _logger.info("[XIBO POS] xibo_notify_cart_event called with payload: %s (args=%s, kwargs=%s)",
                     payload, args, kwargs)
        if not isinstance(payload, dict):
            _logger.info("[XIBO POS] payload not a dict, ignored")
            return False
        config_id = payload.get('config_id') or (self.id if self else False)
        if not config_id:
            _logger.info("[XIBO POS] no config_id")
            return False
        config = self.sudo().browse(config_id)
        if not config or not config.exists():
            _logger.info("[XIBO POS] config not found: %s", config_id)
            return False
        if not config.xibo_server_id or config.xibo_server_id.state != 'connected':
            _logger.info("[XIBO POS] server not connected")
            return False
        if not config._xibo_within_active_window():
            _logger.info("[XIBO POS] outside active time window")
            return False

        event = payload.get('event')
        cart_count = payload.get('cart_count', 0)
        _logger.info("[XIBO POS] event=%s cart_count=%s cd_enabled=%s reco_enabled=%s",
                     event, cart_count, config.xibo_customer_display_enabled, config.xibo_reco_enabled)

        if config.xibo_customer_display_enabled:
            try:
                if event == 'add':
                    config._xibo_activate_customer_display()
                elif event == 'clear':
                    _logger.info("[XIBO POS] deactivating customer display mirror")
                    config._xibo_deactivate_customer_display()
            except Exception as e:
                _logger.exception("[XIBO POS] CD Mirror toggle FAILED: %s", e)

        if event == 'add' and config.xibo_reco_enabled and config._xibo_has_target_displays():
            try:
                config._xibo_send_recommendation(payload)
            except Exception as e:
                _logger.exception("[XIBO POS] Recommendation FAILED: %s", e)

        return True

    # In-memory tracking of which POS configs are currently mirroring.
    # This avoids re-sending changeLayout XMR on every product added.
    _xibo_mirror_active = set()

    def _xibo_set_mirror_active(self, active):
        """Mark this pos.config as having an active Customer Display mirror
        on its target screen. Used to deduplicate XMR calls when the
        cashier adds multiple products to the same cart."""
        if active:
            self.__class__._xibo_mirror_active.add(self.id)
        else:
            self.__class__._xibo_mirror_active.discard(self.id)

    def _xibo_is_mirror_active(self):
        return self.id in self.__class__._xibo_mirror_active

    def _xibo_activate_customer_display(self):
        self.ensure_one()
        if self._xibo_is_mirror_active():
            _logger.info("[XIBO POS] mirror already active for POS %s, skipping XMR", self.id)
            return True
        if not (self.xibo_customer_display_layout_id and self.xibo_customer_display_display_id):
            _logger.info("[XIBO POS] activate: missing layout_id or display_id")
            return False
        if not self.xibo_customer_display_layout_id.xibo_layout_id:
            _logger.info("[XIBO POS] activate: layout has no xibo_layout_id")
            return False
        dg_xibo_id = self.xibo_customer_display_display_id.own_display_group_id
        if not dg_xibo_id:
            _logger.info("[XIBO POS] activate: target display has no own_display_group_id")
            return False
        _logger.info("[XIBO POS] calling change_layout: display_group=%s campaign=%s layout=%s",
                     dg_xibo_id,
                     self.xibo_customer_display_layout_id.xibo_campaign_id,
                     self.xibo_customer_display_layout_id.xibo_layout_id)
        result = self.xibo_server_id.change_layout(
            dg_xibo_id,
            layout_xibo_id=self.xibo_customer_display_layout_id.xibo_layout_id,
            campaign_xibo_id=self.xibo_customer_display_layout_id.xibo_campaign_id,
            duration=self.xibo_customer_display_duration or 0,
            change_mode='replace',
        )
        _logger.info("[XIBO POS] change_layout result: %s", result)
        self._xibo_set_mirror_active(True)
        return result

    def _xibo_deactivate_customer_display(self):
        self.ensure_one()
        if not self._xibo_is_mirror_active():
            _logger.info("[XIBO POS] mirror already inactive for POS %s, skipping XMR", self.id)
            return True
        if not self.xibo_customer_display_display_id:
            return False
        dg_xibo_id = self.xibo_customer_display_display_id.own_display_group_id
        if not dg_xibo_id:
            return False
        _logger.info("[XIBO POS] calling revert_layout: display_group=%s", dg_xibo_id)
        result = self.xibo_server_id.revert_layout(dg_xibo_id)
        _logger.info("[XIBO POS] revert_layout result: %s", result)
        self._xibo_set_mirror_active(False)
        return result

    # ===== ④ Audio notification helpers (since v19.0.1.5.31) =====

    @api.constrains('xibo_thanks_audio_volume')
    def _xibo_check_audio_volume(self):
        for cfg in self:
            v = cfg.xibo_thanks_audio_volume
            if v is None:
                continue
            if v < 0 or v > 100:
                raise ValidationError(_(
                    "Audio volume must be between 0 and 100 (got %s).") % v)

    @api.constrains('xibo_thanks_audio_enabled', 'xibo_thanks_audio_preset',
                    'xibo_thanks_audio_custom_url')
    def _xibo_check_audio_custom_url(self):
        for cfg in self:
            if (cfg.xibo_thanks_audio_enabled
                    and cfg.xibo_thanks_audio_preset == 'custom'
                    and not (cfg.xibo_thanks_audio_custom_url or '').strip()):
                raise ValidationError(_(
                    "Audio Preset is set to 'Custom' but Custom Audio URL is "
                    "empty. Either fill in the URL or pick a built-in preset."))

    def _xibo_resolve_audio_url(self):
        """Return the absolute URL to the audio file the Thank-You page must
        play, or empty string when audio is disabled.

        For built-in presets we serve the file from this addon's ``static/``
        folder (publicly reachable). For 'custom' we trust the URL the
        cashier configured.
        """
        self.ensure_one()
        if not self.xibo_thanks_audio_enabled:
            return ''
        preset = (self.xibo_thanks_audio_preset or 'chime').strip()
        if preset == 'custom':
            return (self.xibo_thanks_audio_custom_url or '').strip()
        # Built-in preset: served from /xibo_connector_pos/static/src/audio/*.mp3
        if preset not in ('chime', 'cash', 'success', 'bell'):
            preset = 'chime'  # safe fallback
        base = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '').rstrip('/')
        return '%s/xibo_connector_pos/static/src/audio/%s.mp3' % (base, preset)

    def _xibo_resolve_audio_volume(self):
        """Return the audio volume as a float in [0.0, 1.0] for HTML5 ``<audio>``."""
        self.ensure_one()
        v = self.xibo_thanks_audio_volume
        if v is None:
            v = 80
        v = max(0, min(100, int(v)))
        return v / 100.0

    # ===== ① AI Thank-You — URL-render flow (since v19.0.1.5.27) =====
    def _xibo_activate_thanks_layout(self, order, message, ctx=None):
        """Publish the Thank-You message and switch the configured screens to
        the Thank-You layout via XMR.

        Architecture (since 19.0.1.5.27)
        --------------------------------
        Instead of pushing a row to a Xibo DataSet (whose cache makes the
        on-screen text lag behind the AI by minutes), we publish the message
        into the ``xibo.thanks.render`` table and rely on the Thank-You
        Layout's **Webpage widget** to fetch ``/xibo/thanks/<config_id>``
        on every display. The HTTP response carries
        ``Cache-Control: no-cache`` so the player always shows the latest
        message.

        Steps:
          1. Create a ``xibo.thanks.render`` record (the HTTP controller
             reads from it).
          2. For each screen in ``xibo_thanks_display_ids``, send an XMR
             ``changeLayout`` with the configured duration.

        We do NOT call ``revertToSchedule`` manually: when the XMR carries
        a non-zero ``duration``, the Xibo player auto-reverts when the
        duration elapses. Calling revert here would race with the auto-
        revert and could blank the screen.

        :param order: the ``pos.order`` record that triggered the thanks.
        :param message: the rendered text (AI-generated or fallback).
        :param ctx: the context dict from ``_xibo_collect_thanks_context``,
                    used to fill the render template.
        :returns: True on success, False otherwise. All steps are logged
                  with the ``[XIBO POS THANKS]`` prefix.
        """
        self.ensure_one()
        if not message:
            _logger.info("[XIBO POS THANKS] no message — aborting")
            return False
        if not self.xibo_thanks_layout_id:
            _logger.info("[XIBO POS THANKS] no thanks layout configured — aborting")
            return False
        if not self.xibo_thanks_display_ids:
            _logger.info("[XIBO POS THANKS] no target screens configured")
            return False
        if not (self.xibo_server_id and self.xibo_server_id.state == 'connected'):
            _logger.info("[XIBO POS THANKS] server not connected — aborting")
            return False

        layout = self.xibo_thanks_layout_id
        if not (layout.xibo_layout_id or layout.xibo_campaign_id):
            _logger.warning(
                "[XIBO POS THANKS] thanks layout '%s' has no xibo_layout_id "
                "nor xibo_campaign_id — cannot dispatch XMR", layout.name,
            )
            return False

        # The TTL must outlive the display window so the Webpage widget
        # always finds a fresh record. We add a 30s safety margin.
        duration = int(self.xibo_thanks_duration or 15)
        ttl = duration + 30

        # 1) Publish the render.
        try:
            render = self.env['xibo.thanks.render'].sudo()._create_for_order(
                config=self, order=order, message=message,
                ctx=(ctx or {}), ttl_seconds=ttl,
            )
            _logger.info(
                "[XIBO POS THANKS] render published id=%s (order=%s, ttl=%ss, preset=%s)",
                render.id, order.name if order else '<none>', ttl, render.preset,
            )
        except Exception as e:
            _logger.exception(
                "[XIBO POS THANKS] FAILED to publish render (order=%s): %s",
                order.name if order else '<none>', e,
            )
            return False

        # 2) Fire XMR changeLayout to every target screen.
        successes = 0
        failures = 0
        for screen in self.xibo_thanks_display_ids:
            dg_xibo_id = screen.own_display_group_id
            if not dg_xibo_id:
                _logger.warning(
                    "[XIBO POS THANKS] screen '%s' has no own_display_group_id — skipped",
                    screen.name,
                )
                failures += 1
                continue
            _logger.info(
                "[XIBO POS THANKS] changeLayout: screen=%s dg=%s campaign=%s layout=%s dur=%s",
                screen.name, dg_xibo_id,
                layout.xibo_campaign_id, layout.xibo_layout_id, duration,
            )
            result = self.xibo_server_id.change_layout(
                dg_xibo_id,
                layout_xibo_id=layout.xibo_layout_id,
                campaign_xibo_id=layout.xibo_campaign_id,
                duration=duration,
                change_mode='replace',
            )
            if result is not False and result is not None:
                successes += 1
            else:
                failures += 1
            _logger.info("[XIBO POS THANKS] changeLayout result for %s: %s",
                         screen.name, result)

        _logger.info(
            "[XIBO POS THANKS] dispatched: %s successes, %s failures (order=%s, msg=%r)",
            successes, failures,
            order.name if order else '<none>',
            (message or '')[:80],
        )
        return successes > 0

    # ===== ④ Recommendations =====
    def _xibo_send_recommendation(self, payload):
        self.ensure_one()
        product_id = payload.get('product_id')
        if not product_id:
            return False
        product = self.env['product.product'].sudo().browse(product_id)
        if not product.exists():
            return False
        tags = product._xibo_effective_tags()
        if not tags:
            return False
        if self.xibo_reco_cooldown and self.xibo_reco_last_sent:
            elapsed = (fields.Datetime.now() - self.xibo_reco_last_sent).total_seconds()
            if elapsed < self.xibo_reco_cooldown:
                return False
        media = self._xibo_find_media_by_tags(tags)
        if not media:
            return False
        try:
            layout = self.env['xibo.layout']._create_simple_image_layout(
                self.xibo_server_id, media[0],
                _('Reco: %s') % product.display_name[:40],
                resolution_id=1,
            )
        except Exception as e:
            _logger.warning("Reco layout build failed: %s", e)
            return False

        self.env['xibo.broadcast'].sudo().quick_send(
            server=self.xibo_server_id,
            mode=self.xibo_reco_mode,
            layout=layout,
            displays=self.xibo_display_ids,
            display_groups=self.xibo_display_group_ids,
            duration=self.xibo_reco_duration or 20,
            origin=('product.product', product.id, _('Reco: %s') % product.display_name),
            name=_('Reco: %s') % product.display_name,
        )

        self.sudo().write({
            'xibo_reco_last_sent': fields.Datetime.now(),
            'xibo_reco_last_tag_signature': ','.join(sorted(set(tags))),
        })
        return True

    def _xibo_find_media_by_tags(self, tags):
        self.ensure_one()
        if not tags:
            return self.env['xibo.media']
        domain = [
            ('server_id', '=', self.xibo_server_id.id),
            ('state', 'in', ['uploaded', 'xibo_only']),
        ]
        tag_clauses = [('tags', 'ilike', t) for t in tags]
        if len(tag_clauses) == 1:
            domain += tag_clauses
        else:
            domain += ['|'] * (len(tag_clauses) - 1) + tag_clauses
        return self.env['xibo.media'].sudo().search(domain, limit=10)

    @staticmethod
    def _xibo_find_first_playlist(detail):
        if not isinstance(detail, list) or not detail:
            return None
        regions = detail[0].get('regions') or []
        if not regions:
            return None
        pls = regions[0].get('regionPlaylist') or regions[0].get('playlists') or []
        if isinstance(pls, list) and pls:
            return pls[0].get('playlistId')
        if isinstance(pls, dict):
            return pls.get('playlistId')
        return None

    @staticmethod
    def _xibo_find_first_widget(detail):
        if not isinstance(detail, list) or not detail:
            return None
        regions = detail[0].get('regions') or []
        if not regions:
            return None
        pls = regions[0].get('regionPlaylist') or regions[0].get('playlists') or []
        if isinstance(pls, dict):
            widgets = pls.get('widgets') or []
        elif isinstance(pls, list) and pls:
            widgets = pls[0].get('widgets') or []
        else:
            widgets = []
        if widgets:
            return widgets[0].get('widgetId')
        return None
