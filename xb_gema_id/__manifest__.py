# -*- coding: utf-8 -*-
{
    "name": "Gems - Automatic gem ID and cloud folder",
    "summary": "Numbers each new gem (0441, 0442...) and creates its folder "
               "in Nextcloud.",
    "description": """
Gems - Automatic gem ID and cloud folder
========================================
When a gem is created by hand (a product of a category flagged "Assign gem
ID", tracked by serial number) its "ID Gema" gets the next number of the
"Gem ID" sequence, with 4 digits. Duplicating a gem gives the copy a new
number instead of repeating the old one.

Right after, a folder named after that number is created in Nextcloud
(WebDAV). If the cloud does not answer, the gem is saved anyway and an
hourly job retries the folder.

Settings (System Parameters):

* ``xb_gema_id.webdav_url``: folder that holds the gem folders, e.g.
  ``https://cloud.example.com/remote.php/dav/files/<user>/<path>``
* ``xb_gema_id.webdav_user`` and ``xb_gema_id.webdav_password``
  (an app password).
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Inventory/Inventory",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["stock"],
    "data": [
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "views/product_category_views.xml",
    ],
    "application": False,
    "installable": True,
}
