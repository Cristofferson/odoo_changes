# -*- coding: utf-8 -*-
{
    "name": "Website - Ring Size Guide Link",
    "summary": "A link to the website's size guide next to the size option of the "
               "product page.",
    "description": """
Website - Ring Size Guide Link
==============================
Each website can point to its own size guide page (Website settings). When set, the
product page shows "? Size guide" next to the size option
(attribute named Medida, Talla or Size). Websites without a guide show nothing.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Website/Website",
    "version": "19.0.1.1.0",
    "license": "LGPL-3",
    "depends": ["website_sale"],
    "data": [
        "views/templates.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "xb_website_size_guide/static/src/scss/size_guide.scss",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
}
