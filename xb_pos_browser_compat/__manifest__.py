# -*- coding: utf-8 -*-
{
    "name": "POS & Kiosk - Older Browsers",
    "summary": "The self-order kiosk and the POS open on browsers older than Chrome 122 "
               "(Set methods polyfill).",
    "description": """
POS & Kiosk - Older Browsers
============================
Odoo 19's Point of Sale and self-order kiosk use the new JavaScript Set methods
(``Set.prototype.difference``...), which Chrome only has since version 122 (Safari 17,
Firefox 127). On an older browser the kiosk stays blank, without any error on screen.

This module adds those methods before anything else in the kiosk and POS bundles, only
when the browser lacks them: up-to-date browsers are untouched.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Point of Sale",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "pos_self_order"],
    "assets": {
        "pos_self_order.assets": [
            ("prepend", "xb_pos_browser_compat/static/src/set_methods_polyfill.js"),
        ],
        "point_of_sale._assets_pos": [
            ("prepend", "xb_pos_browser_compat/static/src/set_methods_polyfill.js"),
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
}
