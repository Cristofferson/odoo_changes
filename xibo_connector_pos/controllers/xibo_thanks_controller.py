# -*- coding: utf-8 -*-
"""HTTP controller serving the Thank-You page rendered at /xibo/thanks/<id>.

This endpoint is what the Xibo Webpage widget hits on every refresh during
the Thank-You display window. It MUST be public (no auth) because the
Xibo player doesn't carry Odoo session cookies, and it MUST return
``Cache-Control: no-cache`` so the player shows the latest message.

Security
--------
* No write operations. Only reads from ``xibo.thanks.render`` (a small,
  TTL-bounded table).
* The URL contains only an integer ``config_id`` — guessable, but the
  response only ever reveals the message that's currently scheduled to
  display on a public store screen anyway. No customer PII beyond what the
  cashier configured to show.
* If no fresh render exists for the config, we serve a neutral fallback
  page ("Thank you for your visit") rather than leaking error details.
"""
import html
import logging

from odoo import http, fields
from odoo.http import request, Response
from odoo.tools import consteq

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML presets
# ---------------------------------------------------------------------------
# Design notes (apps.odoo.com review):
#   * Each preset is a complete, self-contained HTML page (DOCTYPE → </html>).
#   * CSS is inline in <style> blocks. No external fonts, no JS frameworks,
#     no CDN. This guarantees rendering when the player has no internet
#     beyond the Odoo server it's already talking to.
#   * System-stack fonts are used so we look good on Windows / Linux / Android
#     players without bundling font files.
#   * Animations are pure CSS keyframes (no JS) so they trigger on every
#     full page load — which is exactly what the Webpage widget does.
#   * Designed for 1920×1080 but uses fluid units (vw/vh) so it scales
#     gracefully to any aspect ratio.
#   * The Lottie-like "check" animation in MINIMAL is a pure-SVG stroke
#     reveal, no JS.
# ---------------------------------------------------------------------------

PRESET_MINIMAL = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Thanks</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:100%;height:100%;background:#fafaf9;overflow:hidden;
    font-family:'Helvetica Neue',Helvetica,Arial,system-ui,sans-serif;color:#1c1917}
  .wrap{width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;
    flex-direction:column;text-align:center;padding:8vh 6vw}
  .check{width:14vh;height:14vh;margin-bottom:4vh}
  .check circle{fill:none;stroke:#16a34a;stroke-width:3;stroke-dasharray:170;stroke-dashoffset:170;
    animation:draw 0.9s ease-out 0.1s forwards}
  .check path{fill:none;stroke:#16a34a;stroke-width:5;stroke-linecap:round;stroke-linejoin:round;
    stroke-dasharray:48;stroke-dashoffset:48;
    animation:draw 0.6s ease-out 0.9s forwards}
  .message{font-size:5.2vh;font-weight:300;letter-spacing:-0.01em;line-height:1.2;
    max-width:80vw;opacity:0;animation:fadeIn 0.8s ease-out 1.3s forwards}
  .customer{font-size:3.8vh;font-weight:600;color:#0c0a09;margin-top:2vh;
    opacity:0;animation:fadeIn 0.8s ease-out 1.6s forwards}
  .product-img{width:30vh;height:30vh;object-fit:cover;border-radius:1vh;margin-top:5vh;
    opacity:0;animation:fadeIn 0.8s ease-out 1.9s forwards;
    box-shadow:0 4px 30px rgba(0,0,0,.08)}
  .footer{position:absolute;bottom:4vh;font-size:2.2vh;color:#a8a29e;
    opacity:0;animation:fadeIn 1s ease-out 2.2s forwards;letter-spacing:0.05em}
  @keyframes draw{to{stroke-dashoffset:0}}
  @keyframes fadeIn{to{opacity:1}}
</style></head>
<body><div class="wrap">
  <svg class="check" viewBox="0 0 60 60">
    <circle cx="30" cy="30" r="27"/>
    <path d="M18 31 l9 9 l16 -18"/>
  </svg>
  <div class="message">{message_html}</div>
  {customer_html}
  {product_image_html}
  <div class="footer">{company_html}</div>
</div></body></html>"""


PRESET_WARM = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Thanks</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:100%;height:100%;overflow:hidden;
    font-family:Georgia,'Times New Roman',serif;color:#3d2814;
    background:radial-gradient(ellipse at center,#fef3e2 0%,#fde4c0 60%,#f5d29a 100%)}
  .wrap{width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;
    flex-direction:column;text-align:center;padding:8vh 6vw;position:relative}
  .ornament{font-size:8vh;color:#b8860b;
    animation:bloom 1.2s ease-out forwards;opacity:0;transform:scale(0.5)}
  .message{font-size:5.4vh;font-style:italic;font-weight:400;line-height:1.3;max-width:78vw;
    margin-top:4vh;color:#3d2814;
    opacity:0;animation:fadeUp 1s ease-out 0.6s forwards;transform:translateY(20px)}
  .customer{font-size:4vh;font-weight:700;color:#8b4513;margin-top:3vh;font-family:Georgia,serif;
    opacity:0;animation:fadeUp 1s ease-out 1s forwards;transform:translateY(20px)}
  .product-img{width:32vh;height:32vh;object-fit:cover;border-radius:50%;margin-top:5vh;
    border:0.6vh solid #b8860b;box-shadow:0 8px 30px rgba(184,134,11,.3);
    opacity:0;animation:fadeUp 1s ease-out 1.4s forwards;transform:translateY(20px)}
  .divider{width:12vh;height:1px;background:#b8860b;margin:3vh 0;
    opacity:0;animation:fadeIn 1s ease-out 1.3s forwards}
  .footer{position:absolute;bottom:4vh;font-size:2.4vh;color:#8b4513;letter-spacing:0.2em;
    text-transform:uppercase;opacity:0;animation:fadeIn 1s ease-out 1.6s forwards}
  @keyframes bloom{to{opacity:1;transform:scale(1)}}
  @keyframes fadeUp{to{opacity:1;transform:translateY(0)}}
  @keyframes fadeIn{to{opacity:1}}
</style></head>
<body><div class="wrap">
  <div class="ornament">❦</div>
  <div class="divider"></div>
  <div class="message">{message_html}</div>
  {customer_html}
  {product_image_html}
  <div class="footer">{company_html}</div>
</div></body></html>"""


PRESET_BOLD = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Thanks</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:100%;height:100%;overflow:hidden;
    font-family:'Impact','Arial Black',system-ui,sans-serif;color:#fff;
    background:linear-gradient(135deg,#000 0%,#1a1a1a 100%)}
  body::before{content:'';position:absolute;inset:0;
    background:radial-gradient(circle at 30% 20%,rgba(220,38,38,.25) 0%,transparent 50%),
               radial-gradient(circle at 80% 80%,rgba(59,130,246,.2) 0%,transparent 50%);
    animation:slowPulse 8s ease-in-out infinite}
  .wrap{width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;
    flex-direction:column;text-align:center;padding:6vh 4vw;position:relative;z-index:1}
  .badge{display:inline-block;padding:1.5vh 4vh;background:#dc2626;color:#fff;
    font-size:3vh;font-weight:900;letter-spacing:0.3em;text-transform:uppercase;
    transform:skew(-8deg) scale(0);animation:pop 0.5s ease-out forwards;border-radius:0.5vh}
  .message{font-size:7vh;font-weight:900;line-height:1;letter-spacing:-0.02em;
    text-transform:uppercase;margin-top:5vh;max-width:90vw;
    opacity:0;animation:slideIn 0.7s ease-out 0.5s forwards;transform:translateX(-50px);
    text-shadow:0 4px 20px rgba(0,0,0,.5)}
  .customer{font-size:5vh;font-weight:900;color:#fbbf24;margin-top:3vh;letter-spacing:0.05em;
    text-transform:uppercase;
    opacity:0;animation:slideIn 0.7s ease-out 0.9s forwards;transform:translateX(50px)}
  .product-img{width:30vh;height:30vh;object-fit:cover;margin-top:4vh;
    border:0.8vh solid #fff;box-shadow:0 0 50px rgba(220,38,38,.5);
    opacity:0;animation:zoomIn 0.6s ease-out 1.3s forwards;transform:scale(0.8)}
  .footer{position:absolute;bottom:3vh;font-size:2.4vh;color:#737373;letter-spacing:0.3em;
    text-transform:uppercase;font-weight:700;
    opacity:0;animation:fadeIn 1s ease-out 1.6s forwards}
  @keyframes pop{to{transform:skew(-8deg) scale(1)}}
  @keyframes slideIn{to{opacity:1;transform:translateX(0)}}
  @keyframes zoomIn{to{opacity:1;transform:scale(1)}}
  @keyframes fadeIn{to{opacity:1}}
  @keyframes slowPulse{0%,100%{opacity:.5}50%{opacity:1}}
</style></head>
<body><div class="wrap">
  <div class="badge">★ THANK YOU ★</div>
  <div class="message">{message_html}</div>
  {customer_html}
  {product_image_html}
  <div class="footer">{company_html}</div>
</div></body></html>"""


# Served when no fresh render exists. Intentionally neutral.
FALLBACK_HTML = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Thanks</title>
<style>
  html,body{margin:0;padding:0;width:100%;height:100%;
    background:#fafaf9;color:#57534e;
    font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;
    display:flex;align-items:center;justify-content:center}
  .msg{font-size:5vh;font-weight:300;letter-spacing:0.02em;text-align:center}
</style></head>
<body><div class="msg">Gracias por su visita</div></body></html>"""


# Wrapper templates used by _build_html for the conditional bits.
_CUSTOMER_TPL = '<div class="customer">— {customer}</div>'
_PRODUCT_IMG_TPL = '<img class="product-img" src="{url}" alt="">'


def _escape(value):
    """HTML-escape a value, treating None / empty as ''."""
    if value is None:
        return ''
    return html.escape(str(value), quote=True)


def _no_cache_headers():
    """Headers that prevent any caching by intermediaries or the player."""
    return [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Cache-Control', 'no-store, no-cache, must-revalidate, private, max-age=0'),
        ('Pragma', 'no-cache'),
        ('Expires', '0'),
        ('X-Robots-Tag', 'noindex, nofollow'),  # not for SEO
    ]


def _audio_html(render):
    """Build the HTML5 ``<audio autoplay>`` snippet for the configured audio.

    Returns empty string when audio is disabled. The element is hidden
    (display:none) — the user never sees a player UI, just hears the sound.

    HTML5 autoplay policy notes:
      * In standard browsers, autoplay is allowed for muted audio or after a
        user gesture. In Xibo's embedded WebView (running in kiosk mode), the
        autoplay policy is typically permissive enough to allow short
        notification sounds without user interaction.
      * The ``onerror`` attribute logs failures to the browser console so
        kiosks with stricter policies surface the issue in player logs.
    """
    url = (getattr(render, 'audio_url', '') or '').strip()
    if not url:
        return ''
    # Clamp volume to [0,1]. Many older WebViews ignore the attribute and
    # default to 1.0 — the JS line is a belt-and-braces volume set.
    vol = getattr(render, 'audio_volume', 0.8) or 0.8
    try:
        vol = float(vol)
    except (TypeError, ValueError):
        vol = 0.8
    vol = max(0.0, min(1.0, vol))

    return (
        '<audio id="xibo-thanks-audio" autoplay preload="auto" '
        'style="display:none" '
        'onerror="console.warn(\'Xibo Thanks audio failed to load\')">'
        '<source src="%s" type="audio/mpeg">'
        '</audio>'
        '<script>(function(){var a=document.getElementById('
        '"xibo-thanks-audio");if(a){a.volume=%.2f;a.play&&a.play().catch('
        'function(e){console.warn("Xibo Thanks audio autoplay blocked",e)})}'
        '})();</script>'
    ) % (_escape(url), vol)


def _inject_before_body_close(html_body, snippet):
    """Insert ``snippet`` immediately before the closing ``</body>`` tag.

    Falls back to appending if ``</body>`` is not present (defensive).
    """
    if not snippet:
        return html_body
    marker = '</body>'
    idx = html_body.lower().rfind(marker)
    if idx == -1:
        # No </body> — append. Won't be valid HTML5 but the browser will
        # still parse it as best it can.
        return html_body + snippet
    return html_body[:idx] + snippet + html_body[idx:]


def _build_html(render, company):
    """Render the chosen preset (or custom HTML) with the data on ``render``.

    All user-controlled values are HTML-escaped (the only exception is the
    customer's `Custom HTML Template`, which the cashier explicitly chose
    to author themselves — same trust level as Website snippets).
    """
    message_html = _escape(render.message)
    customer_html = (_CUSTOMER_TPL.format(customer=_escape(render.customer_name))
                     if render.customer_name else '')

    if render.show_product_image and render.top_product_image_url:
        product_image_html = _PRODUCT_IMG_TPL.format(
            url=_escape(render.top_product_image_url),
        )
    else:
        product_image_html = ''

    company_name = (company.name if company else '') or ''
    company_html = _escape(company_name).upper()

    fmt_args = {
        'message_html': message_html,
        'customer_html': customer_html,
        'product_image_html': product_image_html,
        'company_html': company_html,
    }

    preset = render.preset or 'minimal'

    if preset == 'custom' and render.custom_html:
        # Custom template substitution with double-braced placeholders.
        # We deliberately do NOT escape — the cashier wrote this HTML
        # themselves and may include intentional markup, fonts, etc.
        # The only fields we substitute are the dynamic ones; everything
        # else stays as written.
        product_url = render.top_product_image_url or ''
        currency = render.currency_code or ''
        total_str = (
            ("%.2f" % render.amount_total) if render.amount_total is not None else ''
        )
        substitutions = {
            '{{message}}': _escape(render.message),
            '{{customer_name}}': _escape(render.customer_name),
            '{{top_product}}': _escape(render.top_product),
            '{{product_image_url}}': _escape(product_url),
            '{{total}}': _escape(total_str),
            '{{currency}}': _escape(currency),
            '{{company_name}}': _escape(company_name),
            '{{company_logo_url}}': _escape(_company_logo_url(company)),
        }
        body = render.custom_html
        for key, val in substitutions.items():
            body = body.replace(key, val)
        # Inject audio snippet (no-op if disabled).
        return _inject_before_body_close(body, _audio_html(render))

    template = {
        'minimal': PRESET_MINIMAL,
        'warm': PRESET_WARM,
        'bold': PRESET_BOLD,
    }.get(preset, PRESET_MINIMAL)

    # Use direct string replacement instead of .format() because the
    # HTML templates contain literal `{` / `}` characters in their inline
    # CSS rules (e.g. `body{margin:0}`), which `.format()` would try to
    # interpret as field placeholders and raise KeyError. Token style
    # `__TOKEN__` is unambiguous in both HTML and CSS contexts.
    result = template
    for token, value in fmt_args.items():
        result = result.replace('{' + token + '}', value)
    # Inject audio snippet (no-op if disabled).
    return _inject_before_body_close(result, _audio_html(render))


def _company_logo_url(company):
    """Build an absolute URL to the company logo, or empty string."""
    if not company:
        return ''
    ICP = request.env['ir.config_parameter'].sudo()
    base_url = (ICP.get_param('web.base.url') or '').rstrip('/')
    if not base_url:
        return ''
    return f"{base_url}/web/image/res.company/{company.id}/logo"


class XiboThanksController(http.Controller):

    @http.route(
        '/xibo/thanks/<int:config_id>',
        type='http', auth='public', methods=['GET'], csrf=False, save_session=False,
    )
    def render_thanks(self, config_id, **kwargs):
        """Public endpoint hit by the Xibo Webpage widget once per refresh.

        Returns the freshest non-expired ``xibo.thanks.render`` record for
        the given ``config_id``. If none exists (or the config doesn't
        exist), returns a neutral fallback page so the on-screen experience
        never looks broken.
        """
        env = request.env

        # --- Optional access-key gate (OFF by default; backward compatible) ---
        # When the cashier turns ON "Require key" for this POS, the Xibo
        # Webpage widget URL must carry ?key=<token>. Configs left with the
        # switch OFF (the default) behave exactly as before — no key needed —
        # so deploying this code changes nothing until an admin opts in per
        # screen. On a bad/missing key we serve the same neutral fallback page
        # (never an error, never any data) so a misconfigured screen degrades
        # gracefully and an outsider learns nothing.
        config = env['pos.config'].sudo().browse(config_id)
        if config.exists() and config.xibo_thanks_require_token:
            provided = kwargs.get('key') or ''
            expected = config.xibo_thanks_token or ''
            if not expected or not consteq(provided, expected):
                _logger.info(
                    "[XIBO POS THANKS] /xibo/thanks/%s: key required but "
                    "missing/invalid — serving fallback", config_id,
                )
                return Response(FALLBACK_HTML, headers=_no_cache_headers())

        Render = env['xibo.thanks.render'].sudo()
        now = fields.Datetime.now()
        render = Render.search(
            [('config_id', '=', config_id),
             ('expires_at', '>', now)],
            order='create_date desc', limit=1,
        )
        if not render:
            _logger.debug(
                "[XIBO POS THANKS] /xibo/thanks/%s: no fresh render — serving fallback",
                config_id,
            )
            return Response(FALLBACK_HTML, headers=_no_cache_headers())

        # Resolve company from the pos.config for branding (logo + name).
        company = render.config_id.company_id if render.config_id else env.company
        try:
            html_body = _build_html(render, company)
        except Exception as e:
            _logger.exception(
                "[XIBO POS THANKS] /xibo/thanks/%s: render FAILED (render_id=%s): %s",
                config_id, render.id, e,
            )
            return Response(FALLBACK_HTML, headers=_no_cache_headers())

        return Response(html_body, headers=_no_cache_headers())

    @http.route(
        ['/xibo/thanks/<int:config_id>/admin-preview',
         '/xibo/thanks/<int:config_id>/preview'],  # deprecated alias
        type='http', auth='user', methods=['GET'], csrf=False, save_session=False,
    )
    def admin_preview_thanks(self, config_id, **kwargs):
        """Authenticated preview endpoint for store admins.

        Renders the configured preset with placeholder data so the cashier
        can preview their template without making a sale. Useful when
        tuning the Custom HTML.

        URL note (since v19.0.1.5.31):
          The canonical URL is ``/xibo/thanks/<id>/admin-preview``. The old
          ``/preview`` URL still works for backwards compatibility but logs
          a deprecation warning. The name was changed because customers
          kept (incorrectly) pasting the ``/preview`` URL into their Xibo
          Webpage widget, which would then redirect the player to a login
          page since the preview requires authentication.
        """
        # Detect legacy URL and warn (path will end with /preview but not /admin-preview).
        path = request.httprequest.path or ''
        if path.endswith('/preview') and not path.endswith('/admin-preview'):
            _logger.warning(
                "[XIBO POS THANKS] DEPRECATED URL used: %s — the canonical "
                "URL is /xibo/thanks/%s/admin-preview. The Xibo Webpage "
                "widget should use the PUBLIC URL /xibo/thanks/%s (no "
                "/preview, no /admin-preview).",
                path, config_id, config_id,
            )

        env = request.env
        config = env['pos.config'].browse(config_id).exists()
        if not config:
            return request.not_found()

        company = config.company_id or env.company
        # Build an in-memory render-like object so we don't pollute the DB.
        class _Dummy:
            pass
        dummy = _Dummy()
        dummy.message = "¡Gracias por su compra, Diana! Disfrute su nueva pieza."
        dummy.customer_name = "Diana García"
        dummy.top_product = "Anillo Solitario 0.5ct"
        dummy.top_product_image_url = ''
        dummy.amount_total = 25000.0
        dummy.currency_code = (
            config.currency_id.name if config.currency_id else 'USD'
        )
        dummy.preset = config.xibo_thanks_preset or 'minimal'
        dummy.custom_html = config.xibo_thanks_custom_html or ''
        dummy.show_product_image = False  # no sample image in preview
        dummy.config_id = config
        # Audio (since v1.5.31)
        try:
            dummy.audio_url = config._xibo_resolve_audio_url()
            dummy.audio_volume = config._xibo_resolve_audio_volume()
        except Exception:
            dummy.audio_url = ''
            dummy.audio_volume = 0.8

        try:
            html_body = _build_html(dummy, company)
        except Exception as e:
            _logger.exception("[XIBO POS THANKS] preview render failed: %s", e)
            return Response(FALLBACK_HTML, headers=_no_cache_headers())
        # Preview can be cached for a second to make rapid template edits snappier.
        headers = [('Content-Type', 'text/html; charset=utf-8'),
                   ('Cache-Control', 'private, max-age=1')]
        return Response(html_body, headers=headers)

    @http.route(
        '/xibo/healthcheck',
        type='http', auth='public', methods=['GET'], csrf=False, save_session=False,
    )
    def healthcheck(self, **kwargs):
        """Lightweight diagnostic endpoint for monitoring tools and support.

        Returns a JSON document with:
          * module_version
          * schema_ok: every expected column exists
          * server_count: how many Xibo servers are configured
          * server_connected_count: how many are currently in 'connected' state
          * ai_available: whether the Odoo 'ai' module is installed
          * fresh_render_count: count of non-expired renders right now

        Closed by default (404). To use it, set the secret
        ir.config_parameter 'xibo_connector_pos.healthcheck_token' and call
        /xibo/healthcheck?token=<secret> — e.g. from a monitoring tool that
        can carry the secret. Without the secret nothing is revealed.
        """
        import json
        env = request.env

        # --- Access gate: CLOSED by default --------------------------------
        # This endpoint used to be public and leaked module version, Xibo
        # connectivity, AI availability and render counts to anyone. Now it is
        # closed unless an admin sets a secret in ir.config_parameter
        # 'xibo_connector_pos.healthcheck_token' and calls
        # /xibo/healthcheck?token=<secret>. With no secret configured, every
        # request gets a bare 404 (we don't even confirm the route exists).
        secret = env['ir.config_parameter'].sudo().get_param(
            'xibo_connector_pos.healthcheck_token')
        provided = kwargs.get('token') or ''
        if not secret or not consteq(provided, secret):
            return Response('Not Found', status=404)

        # 1) Module version (read from manifest — single source of truth).
        try:
            module = env['ir.module.module'].sudo().search(
                [('name', '=', 'xibo_connector_pos')], limit=1)
            module_version = module.latest_version or ''
            module_state = module.state or 'unknown'
        except Exception:
            module_version = ''
            module_state = 'unknown'

        # 2) Schema integrity (best-effort: check a couple of pivotal columns
        #    declared since 1.5.31).
        schema_ok = True
        schema_missing = []
        try:
            cr = env.cr
            for table, col in [
                ('pos_order', 'xibo_thanks_sent'),
                ('pos_config', 'xibo_thanks_preset'),
                ('pos_config', 'xibo_thanks_audio_enabled'),
                ('xibo_thanks_render', 'audio_url'),
            ]:
                cr.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = %s AND column_name = %s",
                    (table, col),
                )
                if not cr.fetchone():
                    schema_ok = False
                    schema_missing.append('%s.%s' % (table, col))
        except Exception as e:
            schema_ok = False
            schema_missing.append('check_failed: %s' % e)

        # 3) Xibo server status.
        try:
            servers = env['xibo.server'].sudo().search([])
            server_count = len(servers)
            server_connected_count = sum(1 for s in servers if s.state == 'connected')
        except Exception:
            server_count = -1
            server_connected_count = -1

        # 4) AI module installed?
        try:
            ai_module = env['ir.module.module'].sudo().search(
                [('name', '=', 'ai'), ('state', '=', 'installed')], limit=1)
            ai_available = bool(ai_module)
        except Exception:
            ai_available = False

        # 5) Fresh render count.
        try:
            fresh_render_count = env['xibo.thanks.render'].sudo().search_count(
                [('expires_at', '>', fields.Datetime.now())]
            )
        except Exception:
            fresh_render_count = -1

        payload = {
            'module': 'xibo_connector_pos',
            'module_version': module_version,
            'module_state': module_state,
            'schema_ok': schema_ok,
            'schema_missing': schema_missing,
            'server_count': server_count,
            'server_connected_count': server_connected_count,
            'ai_available': ai_available,
            'fresh_render_count': fresh_render_count,
            'now_utc': fields.Datetime.now().isoformat() if fields.Datetime.now() else '',
        }
        status = 200 if (schema_ok and server_count >= 0) else 500
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        return Response(
            body, status=status,
            headers=[('Content-Type', 'application/json; charset=utf-8'),
                     ('Cache-Control', 'no-store')],
        )
