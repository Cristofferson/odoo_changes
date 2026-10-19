# -*- coding: utf-8 -*-
{
    "name": "Gems - Automatic name",
    "summary": "Names each gem from its data: type, LAB, shape, carats (GIA "
               "rounding, 2 decimals), clarity, color, cut and labs.",
    "description": """
Gems - Automatic name
=====================
Replaces the Studio automation "Calcular nombre de gema" (left inactive).
The name of a gem (category "Gema", tracked by serial number) is rebuilt
whenever one of its data changes::

    Diamante LAB MQ 1.24 VS1 E EX GIA

* Carats with 2 decimals, GIA rule: the weight is cut to the hundredth and
  only goes up when the third decimal is a 9 (0.899 -> 0.90, 0.898 -> 0.89).
* "N/A", "NA", "Otro" and "Ninguno" are left out; "LAB" marks lab-grown.
* Gems without serial number (accent stones, whose names the rings' price
  reads) and gems with "Nombre fijo" keep their name.
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
        "views/product_template_views.xml",
    ],
    "application": False,
    "installable": True,
}
