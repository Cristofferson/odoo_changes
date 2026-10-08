# -*- coding: utf-8 -*-
{
    "name": "POS Order List Filters - WhatsApp",
    "summary": "Bridge: the WhatsApp \"Notify\" button also shows on the POS order list "
               "of POS Order List – Newest First and Filters.",
    "description": """
POS Order List Filters - WhatsApp
=================================
POS Order List – Newest First and Filters gives the Point of Sale its own list of
sale orders. This bridge adds to that list the "Notify" / "Notified" button of
Sales, Quotations & Layaway from POS - WhatsApp, right after the customer, so the
cashier can send WhatsApp notices from the POS again.

Installs by itself when both modules are present.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Point of Sale",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": [
        "xb_pos_order_list_filters",
        "xb_sale_order_from_pos_whatsapp",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": True,
}
