# -*- coding: utf-8 -*-
{
    "name": "Self-Order Kiosk - Anello Style",
    "summary": "The self-order kiosk with the look of anello.mx: large product photos, "
               "serif names, gold accents and compact option chips.",
    "description": """
Self-Order Kiosk - Anello Style
===============================
Restyles the self-order kiosk after the anello.mx shop:

* Product list: two columns of large square photos on the shop's light grey, product
  names in Cormorant Garamond, "From" price as on the website.
* Categories: spaced capitals with a gold underline instead of pills.
* Product page: white header, editorial mosaic (video on top, photos two by two),
  serif title, options as compact chips.
* Buttons: gold, spaced capitals, square corners.
* Installable app: manifest, icons and service worker, opens full screen; in a plain
  browser tab the first touch switches to full screen.

Fonts: Cormorant Garamond and Jost (SIL Open Font License), shipped with the module.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Point of Sale",
    "version": "19.0.1.3.0",
    "license": "LGPL-3",
    "depends": ["pos_self_order"],
    "data": [
        "views/pos_self_order_index.xml",
    ],
    "assets": {
        "pos_self_order.assets": [
            "xb_self_order_theme_anello/static/src/js/kiosk_app.js",
            "xb_self_order_theme_anello/static/src/js/mosaic_video.js",
            "xb_self_order_theme_anello/static/src/js/kiosk_labels.js",
            "xb_self_order_theme_anello/static/src/scss/anello_kiosk.scss",
            "xb_self_order_theme_anello/static/src/xml/anello_kiosk.xml",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
}
