# -*- coding: utf-8 -*-
{
    "name": "Gems - Sale price from Rapaport",
    "summary": "Sets each gem's sale price from its Rapaport public price "
               "(USD, VAT included) converted to pesos.",
    "description": """
Gems - Sale price from Rapaport
===============================
``rapaport_pricing`` quotes every diamond and the "Precio público" field
adds the surcharges, in US dollars and with VAT included, but nothing
copied it to the sale price. This module does:

    sale price = Precio público (USD) x USD rate of the day / 1.16

so the shop, which adds the 16 % VAT, shows the public price in pesos.

It runs whenever a gem is quoted or one of the fields of its public price
changes, and every week (after the Rapaport jobs) to follow the dollar.
Gems without a public price, and gems without serial number tracking
(accent stones, priced by hand and used by the rings' price), are not
touched. The dollar rate is taken
from the company that keeps USD rates.

Lab-grown diamonds marked "Costo LAB por quilate" get their cost from a
fixed price in dollars per carat (parameter
``xb_gema_precio_rapaport.lab_usd_quilate``, 180) and the dollar of the
day, every week. They sell at that cost times
``xb_gema_precio_rapaport.factor_lab`` (3.88): accent stones on their own,
and inside the jewels priced by metal (``xb_joyeria_peso_precio``), instead
of the jewel's own margin.

Accent diamonds (gems without serial number) are sold only at the point
of sale and in Sales: they are kept unpublished and out of the kiosk.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Sales/Sales",
    "version": "19.0.1.3.0",
    "license": "LGPL-3",
    "depends": ["rapaport_pricing", "website_sale", "pos_self_order"],
    "data": [
        "data/ir_cron_data.xml",
        "data/ir_config_parameter_data.xml",
        "views/product_template_views.xml",
    ],
    "application": False,
    "installable": True,
}
