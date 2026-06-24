# -*- coding: utf-8 -*-
{
    'name': 'Xibo Connector — POS Videowall Showcase',
    'version': '19.0.1.1.0',
    'category': 'Marketing/Digital Signage',
    'summary': 'Idle videowall content: rotating online-catalog gallery + QR to the web store, driven from the POS.',
    'description': """
Xibo Connector — POS Videowall Showcase
=======================================

When the counter videowall is idle, show a rotating luxury gallery of your
online catalog plus a QR code that opens the web store on the customer's phone
("Escanea y arma tu selección"). First step of the self-service "build your
selection" experience.

* Public endpoint ``/xibo/showcase/<config_id>`` serving a self-contained HTML
  page (QR generated server-side, product images from this Odoo server, no
  external CDN).
* Configurable per POS: on/off, QR target URL, optional eCommerce category,
  number of pieces, seconds per piece, and the call-to-action text.

This is an add-on of the Xibo Connector suite. Requires the POS connector and
the eCommerce (Website Sale) app.
""",
    'author': 'Cristofferson',
    'website': 'https://www.xubax.com',
    'license': 'OPL-1',
    'depends': [
        'xibo_connector_pos',
        'website_sale',
    ],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'pre_init_hook': 'pre_init_showcase_schema',
    'installable': True,
    'application': False,
    'auto_install': False,
}
