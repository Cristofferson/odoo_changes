# -*- coding: utf-8 -*-
{
    'name': 'POS Receipt without VAT breakdown (Anello)',
    'version': '19.0.1.0.0',
    'summary': 'The POS ticket (printed or sent by WhatsApp) no longer prints the '
               'Subtotal / VAT breakdown lines; it keeps the Total.',
    'description': """
        Anello prices already include VAT, so the ticket does not break the VAT
        out. This removes only the "Subtotal + tax group" block of the native POS
        receipt (point_of_sale.OrderReceipt); lines, total, payments and the rest
        of the ticket stay. Per-database module (same pattern as
        anello_pos_order_button_label): other databases keep the native ticket.
    """,
    'author': 'XUBAX',
    'category': 'Point of Sale',
    'depends': ['point_of_sale', 'xb_sale_order_from_pos'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'anello_pos_receipt_sin_iva/static/src/xml/order_receipt.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
