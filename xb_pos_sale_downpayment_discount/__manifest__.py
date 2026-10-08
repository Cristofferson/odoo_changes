# -*- coding: utf-8 -*-
{
    "name": "POS Down Payment Discount on the Sale Order",
    "summary": "A discount given at the POS on a down payment of a sale order is added "
               "to the sale order, so its balance matches what the customer paid.",
    "description": """
POS Down Payment Discount on the Sale Order
===========================================
When the cashier pays part of a sale order at the Point of Sale (down payment) and gives
the customer a discount on that line, Odoo only lowers what the ticket charges: the
sale order keeps its full price and shows a balance the customer never owed.

This module gives the sale order the same discount, at the moment the ticket is
synced: a "POS discount (ticket ...)" line made with the Sales discount wizard (fixed
amount, taxes included), plus a note in the order's chatter. Each POS line is carried
only once.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Point of Sale",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["pos_sale"],
    "data": [],
    "application": False,
    "installable": True,
    "auto_install": False,
}
