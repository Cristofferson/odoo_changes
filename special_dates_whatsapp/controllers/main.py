# -*- coding: utf-8 -*-
"""Public opt-out endpoint for the anniversary email.

The email carries a signed link ``/anello/aniversario/baja?r=<id>&t=<token>``.

Because email security scanners (Outlook SafeLinks, Proofpoint, …) routinely
*follow* GET links, the opt-out is a two-step flow: the link (GET) only shows
a confirmation page, and the greeting is stopped only when the customer
presses the button, which POSTs back. That press has the exact same effect as
tapping "Ya no celebro esta fecha" on WhatsApp: it flags the contact as a
NOVADIAM prospect and schedules the follow-up.
"""
from markupsafe import Markup

from odoo import http, _
from odoo.http import request
from odoo.tools import consteq


class AnelloAnniversaryController(http.Controller):

    @http.route("/anello/aniversario/baja", type="http", auth="public",
                methods=["GET", "POST"], csrf=False, sitemap=False)
    def anniversary_optout(self, r=None, t=None, **kw):
        if not r or not t:
            return request.not_found()
        try:
            rid = int(r)
        except (TypeError, ValueError):
            return request.not_found()

        env = request.env
        expected = env["xb.wish.reminders"]._xb_optout_token(env, rid)
        if not consteq(t, expected):
            return request.not_found()

        reminder = env["xb.wish.reminders"].sudo().browse(rid)
        if not reminder.exists() or not reminder.partner_id:
            return request.not_found()

        # GET → confirmation page only (safe against link scanners).
        if request.httprequest.method != "POST":
            return self._page(self._confirm_body(rid, t))

        # POST → perform the opt-out.
        reminder.partner_id._xb_anniv_optout(
            reminder.company_id, reminder=reminder)
        return self._page(self._thank_you_body())

    # ------------------------------------------------------------------
    def _page(self, inner):
        return request.make_response(
            Markup(
                """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Anello</title></head>
<body style="margin:0;font-family:Arial,Helvetica,sans-serif;background:#faf7f2;">
  <div style="max-width:520px;margin:10vh auto;padding:40px 32px;background:#fff;
              border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.06);text-align:center;">
    {inner}
  </div>
</body></html>"""
            ).format(inner=inner),
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    def _confirm_body(self, rid, token):
        return Markup(
            """<div style="font-size:44px;">💍</div>
    <h1 style="font-size:22px;color:#2b2b2b;margin:12px 0;">¿Ya no celebras esta fecha?</h1>
    <p style="font-size:15px;color:#555;line-height:1.6;">
      Si lo confirmas, dejaremos de escribirte por tu aniversario de bodas.
    </p>
    <form method="post" action="/anello/aniversario/baja" style="margin-top:22px;">
      <input type="hidden" name="r" value="{rid}"/>
      <input type="hidden" name="t" value="{token}"/>
      <button type="submit" style="background:#b08d57;color:#fff;border:none;
              padding:12px 28px;border-radius:30px;font-weight:bold;font-size:15px;
              cursor:pointer;">Sí, dejar de recibirlo</button>
    </form>
    <p style="font-size:12px;color:#aaa;margin-top:18px;">
      Si fue un error, simplemente cierra esta ventana.
    </p>"""
        ).format(rid=rid, token=token)

    def _thank_you_body(self):
        return Markup(
            """<div style="font-size:44px;">💛</div>
    <h1 style="font-size:22px;color:#2b2b2b;margin:12px 0;">Listo, gracias</h1>
    <p style="font-size:15px;color:#555;line-height:1.6;">
      No volveremos a escribirte por tu aniversario de bodas.
      Si algún día quieres unas argollas nuevas o un regalo especial,
      aquí estaremos con gusto.
    </p>
    <p style="font-size:15px;color:#555;margin-top:20px;">— El equipo de Anello</p>"""
        )
