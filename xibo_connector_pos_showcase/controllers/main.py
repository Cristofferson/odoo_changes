# -*- coding: utf-8 -*-
"""HTTP controller serving the idle/showcase page at /xibo/showcase/<config_id>.

The Xibo Webpage widget of the idle layout loads this URL on the counter
videowall. It returns a self-contained luxury page that cross-fades through a
gallery of the online catalog and shows a QR code that opens the web store on
the customer's phone. No customer data is shown — only the public catalog —
so the endpoint is public, like a storefront window.
"""
import base64
import html
import io
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def _no_cache_headers():
    return [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Cache-Control', 'no-cache, no-store, must-revalidate'),
        ('Pragma', 'no-cache'),
    ]


def _qr_data_uri(text):
    """Generate a QR code for ``text`` and return it as a base64 data URI so the
    page stays fully self-contained (no external calls from the player)."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            box_size=10, border=2,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
        )
        qr.add_data(text or '')
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        _logger.warning("[XIBO SHOWCASE] QR generation failed: %s", e)
        return ''


def _fmt_price(amount, symbol):
    try:
        return '%s%s' % (symbol or '', '{:,.0f}'.format(amount or 0.0))
    except Exception:
        return ''


# Minimal, brand-neutral fallback when the showcase is off or has no pieces.
def _fallback_html(qr_uri, heading, brand):
    qr_block = (
        '<img class="qr" src="%s" alt="QR"/>' % qr_uri if qr_uri else ''
    )
    return """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  html,body{margin:0;height:100%%;background:#0d0d0f;color:#f3efe6;
    font-family:Georgia,'Times New Roman',serif;overflow:hidden}
  .wrap{height:100%%;display:flex;flex-direction:column;align-items:center;
    justify-content:center;gap:28px}
  .brand{letter-spacing:.42em;font-size:2.2vw;color:#cda349;text-transform:uppercase}
  .qr{width:18vh;height:18vh;background:#fff;padding:10px;border-radius:10px}
  .cta{font-size:1.7vw;color:#f3efe6;opacity:.92}
</style></head><body><div class="wrap">
  <div class="brand">%s</div>%s<div class="cta">%s</div>
</div></body></html>""" % (html.escape(brand or ''), qr_block, html.escape(heading or ''))


class XiboShowcaseController(http.Controller):

    @http.route(
        '/xibo/showcase/<int:config_id>',
        type='http', auth='public', methods=['GET'], csrf=False, save_session=False,
    )
    def render_showcase(self, config_id, **kwargs):
        env = request.env
        config = env['pos.config'].sudo().browse(config_id)
        brand = (config.company_id.name if config.exists() and config.company_id
                 else env.company.name)
        heading = (config.xibo_showcase_heading
                   if config.exists() else '') or 'Escanea y arma tu selección'
        qr_uri = _qr_data_uri(
            config._xibo_showcase_qr_target() if config.exists() else '')

        if not config.exists() or not config.xibo_showcase_enabled:
            return Response(_fallback_html(qr_uri, heading, brand),
                            headers=_no_cache_headers())

        products = config._xibo_showcase_products()
        if not products:
            return Response(_fallback_html(qr_uri, heading, brand),
                            headers=_no_cache_headers())

        symbol = (config.currency_id.symbol if config.currency_id
                  else (env.company.currency_id.symbol or '$'))
        base_url = (env['ir.config_parameter'].sudo()
                    .get_param('web.base.url') or '').rstrip('/')

        # Brand: prefer the company logo; fall back to elegant text.
        company = config.company_id or env.company
        if company and company.logo:
            brand_html = ('<img class="brandlogo" src="%s/web/image/res.company/%s/logo" alt="%s"/>'
                          % (base_url, company.id, html.escape(brand or '')))
        else:
            brand_html = '<span>%s</span>' % html.escape(brand or '')

        slides = []
        for p in products:
            img = '%s/web/image/product.template/%s/image_1024' % (base_url, p.id)
            slides.append(
                '<div class="slide"><div class="ph">'
                '<img src="%s" alt=""/></div>'
                '<div class="meta"><div class="name">%s</div>'
                '<div class="price">%s</div></div></div>' % (
                    img,
                    html.escape(p.name or ''),
                    html.escape(_fmt_price(p.list_price, symbol)),
                )
            )

        interval_ms = max((config.xibo_showcase_interval or 6), 2) * 1000
        qr_block = (
            '<img class="qr" src="%s" alt="QR"/>' % qr_uri if qr_uri else ''
        )
        page = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  *{box-sizing:border-box}
  html,body{margin:0;height:100%%;background:#0d0d0f;color:#f3efe6;
    font-family:Georgia,'Times New Roman',serif;overflow:hidden}
  .stage{position:absolute;inset:0}
  .slide{position:absolute;inset:0;display:flex;align-items:center;
    justify-content:center;gap:5vw;opacity:0;transition:opacity 1.1s ease;
    padding:6vh 10vw 6vh 6vw}
  .slide.on{opacity:1}
  .ph{height:74vh;width:54vw;display:flex;align-items:center;justify-content:center;
    overflow:hidden}
  .ph img{max-height:100%%;max-width:100%%;object-fit:contain;
    border-radius:14px;box-shadow:0 24px 70px rgba(0,0,0,.55);transform:scale(1)}
  .slide.on .ph img{animation:kenburns 14s ease-out forwards}
  @keyframes kenburns{from{transform:scale(1)}to{transform:scale(1.08)}}
  .meta{max-width:30vw}
  .name{font-size:2.6vw;line-height:1.18;color:#f6f1e7}
  .price{margin-top:2.2vh;font-size:2.1vw;color:#cda349;letter-spacing:.02em}
  .panel{position:absolute;right:3.2vw;bottom:3.6vh;display:flex;align-items:center;
    gap:1.5vw;background:rgba(0,0,0,.34);backdrop-filter:blur(3px);
    padding:1.6vh 1.6vw;border:1px solid rgba(205,163,73,.35);border-radius:16px}
  .qr{width:15vh;height:15vh;background:#fff;padding:8px;border-radius:10px}
  .panel .cta{font-size:1.45vw;line-height:1.3;max-width:18vw;color:#f3efe6}
  .brand{position:absolute;left:3.2vw;top:3.6vh;letter-spacing:.4em;
    font-size:1.5vw;color:#cda349;text-transform:uppercase}
  .brand .brandlogo{max-height:7vh;max-width:22vw;object-fit:contain;
    filter:brightness(0) invert(1) sepia(.3) saturate(3) hue-rotate(5deg);opacity:.92}
</style></head><body>
  <div class="brand">%s</div>
  <div class="stage">%s</div>
  <div class="panel">%s<div class="cta">%s</div></div>
  <script>
    var slides=document.querySelectorAll('.slide'),i=0;
    if(slides.length){slides[0].classList.add('on');
      setInterval(function(){slides[i].classList.remove('on');
        i=(i+1)%%slides.length;slides[i].classList.add('on');},%d);}
  </script>
</body></html>""" % (
            brand_html,
            ''.join(slides),
            qr_block,
            html.escape(heading or ''),
            interval_ms,
        )
        return Response(page, headers=_no_cache_headers())
