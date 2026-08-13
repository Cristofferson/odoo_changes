# -*- coding: utf-8 -*-
{
    'name': 'Self-Service: Reserve or Book',
    'version': '19.0.1.1.0',
    'category': 'Website/eCommerce',
    'summary': 'On the web store, let the customer choose: reserve in store for counter pickup, or book an advisor. No online payment.',
    'description': """
Self-Service — Reserve or Book
==============================

Turns the online store into a self-service counter assistant. When a customer
(e.g. from the videowall QR) assembles a selection, the cart shows two
call-to-action buttons and lets the customer choose how to continue:

* **"Reserve in store"**: the cart is kept as a quotation tagged for a
  salesperson, who closes it at the counter. No online payment.
* **"Book an advisor"**: the customer is sent to the appointment page to be
  assisted in person.

Both paths end with a human closing the sale at the store — there is no online
payment. Configurable per website: on/off, appointment URL, and the sales team
that receives reservations. Designed for jewelry and other high-touch catalogs.
""",
    'author': 'Cristofferson',
    'website': 'https://www.xubax.com',
    'license': 'OPL-1',
    'depends': [
        'website_sale',
    ],
    'data': [
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],
    'pre_init_hook': 'pre_init_self_service_schema',
    'installable': True,
    'application': False,
    'auto_install': False,
}
