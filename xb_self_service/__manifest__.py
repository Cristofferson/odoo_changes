# -*- coding: utf-8 -*-
{
    'name': 'Self-Service: Reserve or Book by Value',
    'version': '19.0.1.0.0',
    'category': 'Website/eCommerce',
    'summary': 'On the web store, route the customer by basket value: reserve low-value pieces for counter pickup, or book an advisor for high-value ones.',
    'description': """
Self-Service — Reserve or Book by Value
=======================================

Turns the online store into a self-service counter assistant. When a customer
(e.g. from the videowall QR) assembles a selection, a configurable threshold
routes them:

* **Below the threshold → "Reserve in store"**: the cart is kept as a
  quotation tagged for a salesperson, who closes it at the counter. No online
  payment.
* **At/above the threshold → "Book an advisor"**: the customer is sent to the
  appointment page to be assisted with a high-value piece.

Configurable per website: on/off, threshold amount, appointment URL, and the
sales team that receives reservations. Designed for jewelry and other
high-touch, high-value catalogs.
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
