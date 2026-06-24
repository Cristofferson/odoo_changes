# -*- coding: utf-8 -*-
{
    'name': 'Xibo Connector',
    'version': '19.0.1.6.2',
    'category': 'Marketing/Digital Signage',
    'summary': 'Manage Xibo CMS digital signage from Odoo: displays, media, datasets, layouts, broadcasts.',

    'description': """
Xibo Connector for Odoo 19
===========================

The professional bridge between your Odoo and your Xibo CMS digital signage
network. Manage screens, upload media, schedule layouts and trigger real-time
content updates without leaving Odoo.

This is the **base module** of the Xibo Connector Suite. Add-on modules for
Point of Sale, Frontdesk, Sales, eCommerce and Daily Content Feeds are sold
separately.

Key Features
------------
* Multi-server, multi-company configuration (OAuth2 client_credentials)
* Automatic token caching and refresh
* Sync displays, display groups, layouts and DataSets from Xibo
* Upload, edit and delete media (images, videos, audio) to the Xibo Library
* **Sync** existing Library media metadata from Xibo (read-only references)
* **Quick Display**: turn any image into a one-click on-screen message
* Schedule layouts via the Broadcast model (overlay, fullscreen, ticker)
* Day-of-week and time-of-day filters
* Recurrence (minutely, hourly, daily, weekly, monthly, yearly)
* Trigger real-time refresh via the CMS REST API (no port 9505 exposure)
* Full audit trail of every Xibo API call
* Open-in-Xibo deep links from every relevant record
* Granular access rights (User / Manager)
* English and Spanish (Mexico) translations

Compatibility
-------------
* Odoo 19.0
* Xibo CMS v3.0 or newer (older versions may have reduced functionality)

Prerequisites
-------------
* A running Xibo CMS you administer
* OAuth2 application credentials in Xibo (Administration -> Applications)
* Python ``requests`` library on the Odoo server

Support
-------
soporte@xubax.com

Changelog
---------
19.0.1.6.2 (2026-05)
~~~~~~~~~~~~~~~~~~~~
* New helper ``xibo.server._dataset_insert_row(dataset_xibo_id, row_data)``:
  thin wrapper around ``POST /api/dataset/data/{datasetId}`` that accepts
  ``row_data`` as a ``{column_heading: value}`` dict and internally resolves
  each heading to its ``dataSetColumnId_X`` form using the synced column
  metadata. Enables direct-XMR scenarios (e.g. POS AI Thank-You Camino B)
  without going through the Broadcast scheduler.
* No schema changes; safe upgrade from 19.0.1.6.1.

19.0.1.6.1 (2026-05)
~~~~~~~~~~~~~~~~~~~~
* AI nickname automation on res.partner (native ai.agent + base.automation).
* XMR ``changeLayout`` / ``revertToSchedule`` (Xibo 3.x+ name).
* ``change_layout()`` accepts ``campaign_xibo_id`` (stable across publishes).
* Privacy field ``xibo_show_in_public_screens`` on res.partner.
    """,

    'author': 'Cristofferson Reyes Rodriguez',
    'maintainer': 'Cristofferson Reyes Rodriguez',
    'website': 'https://www.xubax.com',
    'support': 'soporte@xubax.com',
    'license': 'OPL-1',
    'price': 18.00,
    'currency': 'USD',

    'depends': [
        'base',
        'mail',
        'ai',
        'base_automation',
    ],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/xibo_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/ai_server_actions.xml',
        'data/ai_automation.xml',
        'views/xibo_server_views.xml',
        'views/xibo_display_group_views.xml',
        'views/xibo_display_views.xml',
        'views/xibo_media_views.xml',
        'views/xibo_layout_views.xml',
        'views/xibo_dataset_views.xml',
        'views/xibo_broadcast_views.xml',
        'views/xibo_event_log_views.xml',
        'views/res_partner_views.xml',
        'views/xibo_menus.xml',
        'wizards/xibo_media_upload_wizard_views.xml',
        'wizards/xibo_quick_display_wizard_views.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
