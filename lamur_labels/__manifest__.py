{
    'name': 'LAMUR - Etiquetas de joyería',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Etiqueta ZPL tipo mariposa (89 x 17 mm) con logo y QR para LAMUR',
    'description': """
Etiqueta de joyería LAMUR
=========================

Agrega la opción **LAMUR (Mariposa 89 x 17 mm)** al desplegable *Plantilla ZPL*
del asistente de impresión de etiquetas de producto, sin alterar las cuatro
plantillas nativas de Odoo (Normal / Small / Alternative / Jewelry).

Es el diseño que la empresa usaba en Odoo 17 y que se perdió en la migración a
Odoo 19: nombre del producto a la izquierda, precio en vertical, código de
barras Code128 (con la referencia interna como respaldo cuando el producto no
tiene código de barras), logotipo LAMUR y código QR.
""",
    'author': 'XUBAX',
    'website': 'https://xubax.com',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'report/label_lamur_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
