# -*- coding: utf-8 -*-
{
    "name": "Jewelry Priced by Metal - Self-Order Kiosk",
    "summary": "Bridge: the self-order kiosk shows and charges the real price of jewels "
               "priced by their metal (gold of the day and chosen options).",
    "description": """
Jewelry Priced by Metal - Self-Order Kiosk
==========================================
Jewels priced by their metal (xb_joyeria_peso_precio) have no fixed price: it depends
on the gold of the day and on the options the customer picks. The self-order kiosk
cannot compute it and showed them at $0.

* Product list: the "from" price, as the website shows it.
* Product page: the price is asked to the server every time the options change.
* Cart: the line goes in with that price.
* Server: when the kiosk sends the order, the price of those lines is computed again
  from the chosen options, so the order never keeps a wrong price.

The kiosk needs a price list (the one of the shop's POS).
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Point of Sale",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "depends": ["xb_joyeria_peso_precio", "pos_self_order"],
    "assets": {
        "pos_self_order.assets": [
            "xb_joyeria_peso_precio/static/src/app/pos_models_patch.js",
            "xb_joyeria_peso_precio_self_order/static/src/app/xb_precio_joya.js",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": True,
}
