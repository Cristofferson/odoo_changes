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
Gems without a public price are not touched. The dollar rate is taken
from the company that keeps USD rates.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Sales/Sales",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["rapaport_pricing"],
    "data": [
        "data/ir_cron_data.xml",
    ],
    "application": False,
    "installable": True,
}
