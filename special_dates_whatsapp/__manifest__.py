# -*- coding: utf-8 -*-
{
    "name": "Special Dates – WhatsApp Integration",
    "summary": "Send Special Dates greetings through WhatsApp.",
    "description": """
Adds WhatsApp as a channel to the Communication Schedule of every
Special Date Type. Requires Odoo Enterprise with the ``whatsapp``
module installed and a configured Meta Business API account.
""",
    "author": "Cristofferson Reyes",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Sales/Sales",
    "version": "19.0.1.0.0",
    "license": "OPL-1",
    "depends": [
        "special_dates",
        "whatsapp",
    ],
    "data": [
        "views/xb_wish_schedule_views.xml",
    ],
    "images": [],
    "auto_install": True,
    "installable": True,
    "price": 0.00,
    "currency": "USD",
}
