# -*- coding: utf-8 -*-
{
    "name": "Delivery Receipt Signature - POS Bridge",
    "version": "19.0.1.2.1",
    "category": "Point of Sale",
    "summary": "Capture the customer's received signature inside the Point of "
               "Sale, at hand-over time.",
    "description": """
Delivery Receipt Signature - POS Bridge
=======================================
Bridge between **Delivery Receipt Signature** (xb_delivery_signature) and the
Point of Sale.

When enabled per Point of Sale, a native signature pad pops up right after the
order is validated, so the customer signs the reception on the cashier's
tablet. The signature is stored on the POS order and, optionally, mirrored to
the linked Sale Order (for POS orders created as quotations / sale orders /
layaways).

Installs automatically when both Delivery Receipt Signature and Point of Sale
are present.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "company": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "license": "OPL-1",
    "depends": [
        "xb_delivery_signature",
        "point_of_sale",
        "pos_sale",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "xb_delivery_signature_pos/static/src/app/signature_popup/signature_popup.js",
            "xb_delivery_signature_pos/static/src/app/signature_popup/signature_popup.xml",
            "xb_delivery_signature_pos/static/src/app/order_payment_validation.js",
            "xb_delivery_signature_pos/static/src/app/pos_store_signature.js",
            "xb_delivery_signature_pos/static/src/app/order_receipt.xml",
        ],
    },
    "images": [
        "static/description/banner.png",
    ],
    # Free bridge: the paid value lives in the base module (xb_delivery_signature).
    # It auto-installs alongside Point of Sale, so POS users get it at no extra cost.
    "price": 0.00,
    "currency": "USD",
    "installable": True,
    "application": False,
    # Auto-install once both dependencies (xb_delivery_signature + point_of_sale)
    # are installed.
    "auto_install": True,
}
