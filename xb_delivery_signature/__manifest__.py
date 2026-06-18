# -*- coding: utf-8 -*-
{
    "name": "Delivery Receipt Signature",
    "version": "19.0.1.2.0",
    "category": "Inventory/Inventory",
    "summary": "Capture the customer's signature when a delivery is handed over "
               "(on a tablet at validation, or self-signed from the portal) and "
               "store it on the delivery and the sale order.",
    "description": """
Delivery Receipt Signature
==========================
Request a digital "received" signature from the customer when a delivery order
(stock.picking) is handed over:

* On the operator's phone/tablet, with a native signature pad that pops up when
  the delivery is validated (optionally mandatory: the delivery cannot be
  completed until it is signed).
* From the customer's own device, through a portal self-sign link secured by the
  sale order's access token.

The signature is stored per delivery (so partial deliveries each keep their own)
and, optionally, mirrored to the Sale Order's native signature fields.

All behaviour is optional and configured per company under
Settings > Inventory.

A Point of Sale bridge (xb_delivery_signature_pos) adds the same capture inside
the POS at hand-over time; it installs automatically when Point of Sale is
present.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "company": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "license": "OPL-1",
    "depends": [
        "stock",
        "sale_stock",
        "portal",
        "website",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/delivery_signature_wizard_views.xml",
        "views/stock_picking_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/delivery_portal_templates.xml",
        "views/report_deliveryslip.xml",
    ],
    "images": [
        "static/description/banner.png",
    ],
    "price": 28.00,
    "currency": "USD",
    "installable": True,
    "application": False,
    "auto_install": False,
}
