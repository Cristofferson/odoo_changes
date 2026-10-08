# -*- coding: utf-8 -*-
{
    "name": "Sales, Quotations & Layaway from POS - Print the Ticket",
    "summary": "Print > Ticket on quotations and orders: the same ticket the quotation is "
               "sent with by WhatsApp, as an 80 mm PDF.",
    "description": """
Sales, Quotations & Layaway from POS - Print the Ticket
=======================================================
Adds *Ticket* to the Print menu of quotations and sale orders. It gives the very
ticket the WhatsApp add-on sends (logo, lines, total, QR to the online quotation),
as a PDF 80 mm wide, ready for a receipt printer or to download, without having to
send it by WhatsApp first. A confirmed order is titled with its kind (order, layaway)
instead of "Quotation".

Installs by itself with Sales, Quotations & Layaway from POS - WhatsApp.
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Sales",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["xb_sale_order_from_pos_whatsapp"],
    "data": [
        "report/sale_order_ticket_report.xml",
    ],
    "application": False,
    "installable": True,
    "auto_install": True,
}
