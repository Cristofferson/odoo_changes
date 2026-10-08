# -*- coding: utf-8 -*-
{
    "name": "POS Restaurant - Courses only for restaurants",
    "summary": "Fix: a POS that is not a restaurant no longer crashes after a payment "
               "when the Restaurant app is installed.",
    "description": """
POS Restaurant - Courses only for restaurants
=============================================
With the Restaurant app installed (for instance pulled in by the self-order kiosk),
every synced order is answered with its restaurant courses, also to a POS that is not
a restaurant and never loaded them. That POS crashes after each payment with
"Cannot read properties of undefined (reading 'triggerEvents')", although the order
is saved. This module sends the courses only to restaurant POS.

Installs by itself with the Restaurant app.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Point of Sale",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["pos_restaurant"],
    "data": [],
    "application": False,
    "installable": True,
    "auto_install": True,
}
