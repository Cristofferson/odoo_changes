# -*- coding: utf-8 -*-
{
    "name": "Sales, Quotations & Layaway from POS",
    "version": "19.0.1.0.4",
    "category": "Point of Sale",
    "summary": "Create quotations, sale orders and layaways (apartados) directly "
               "from the Point of Sale, with detailed receipt and balance.",
    "description": """
Sales, Quotations & Layaway from POS
====================================
Create a Quotation, a confirmed Sale Order or a Layaway (apartado) directly from
the POS screen, print a detailed receipt with the order lines, total and pending
balance, and let the customer finish online or be recovered in-store through the
native Odoo quotation/order flow.

All features are optional and configured per Point of Sale.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "company": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "license": "OPL-1",
    "depends": [
        "point_of_sale",
        "pos_sale",
        "sale",
        "l10n_mx_edi",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "xb_sale_order_from_pos/static/src/app/control_buttons/control_buttons.js",
            "xb_sale_order_from_pos/static/src/app/control_buttons/control_buttons.xml",
            "xb_sale_order_from_pos/static/src/app/models/pos_order.js",
            "xb_sale_order_from_pos/static/src/app/models/pos_order_line.js",
            "xb_sale_order_from_pos/static/src/app/services/pos_store_settle.js",
            "xb_sale_order_from_pos/static/src/app/utils/order_payment_validation.js",
            "xb_sale_order_from_pos/static/src/app/screens/receipt_screen/receipt/order_receipt.js",
            "xb_sale_order_from_pos/static/src/app/screens/receipt_screen/receipt/order_receipt.xml",
            "xb_sale_order_from_pos/static/src/app/screens/receipt_screen/receipt/order_receipt.css",
        ],
        "web.assets_tests": [
            "xb_sale_order_from_pos/static/tests/tours/**/*",
        ],
    },
    "images": [
        "static/description/banner.png",
    ],
    # For a paid app on apps.odoo.com, set price/currency here, e.g.:
    # "price": 49.00,
    # "currency": "USD",
    "installable": True,
    "application": False,
    "auto_install": False,
    # Packaging: heal pre-existing sale.order.amount_unpaid on install over existing
    # data (mirrors the _compute_amount_unpaid per-line fix). See __init__.py.
    "post_init_hook": "post_init_hook",
}
