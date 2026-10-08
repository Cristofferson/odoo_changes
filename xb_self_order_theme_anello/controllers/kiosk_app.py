# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request

from odoo.addons.pos_self_order.controllers.self_entry import PosSelfKiosk

SERVICE_WORKER = """// XUBAX - lets the browser install the kiosk as an app (it needs a fetch handler).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
    if (event.request.mode === "navigate") {
        event.respondWith(fetch(event.request));
    }
});
"""


class XbKioskApp(PosSelfKiosk):

    @http.route("/xb-kiosk/<int:config_id>/manifest.webmanifest", auth="public", type="http", website=True, sitemap=False)
    def xb_kiosk_manifest(self, config_id, access_token=None):
        """Web app manifest: the kiosk can be installed on the tablet and opens full screen."""
        pos_config, _, token = self._verify_entry_access(str(config_id), access_token)
        company = pos_config.sudo().company_id
        manifest = {
            "name": "%s · Kiosco" % company.name,
            "short_name": company.name,
            "start_url": "/pos-self/%s?access_token=%s" % (pos_config.id, access_token),
            "scope": "/pos-self/",
            "id": "/pos-self/%s" % pos_config.id,
            "display": "fullscreen",
            "orientation": "portrait",
            "background_color": "#ffffff",
            "theme_color": "#ffffff",
            "icons": [
                {"src": "/xb_self_order_theme_anello/static/img/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/xb_self_order_theme_anello/static/img/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        return request.make_response(json.dumps(manifest), headers=[
            ("Content-Type", "application/manifest+json"),
            ("Cache-Control", "no-cache"),
        ])

    @http.route("/xb-kiosk/sw.js", auth="public", type="http", sitemap=False)
    def xb_kiosk_service_worker(self):
        return request.make_response(SERVICE_WORKER, headers=[
            ("Content-Type", "text/javascript"),
            ("Service-Worker-Allowed", "/pos-self/"),
            ("Cache-Control", "no-cache"),
        ])
