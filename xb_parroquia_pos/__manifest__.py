{
    'name': 'XUBAX Gestión Parroquial — POS',
    'version': '19.0.1.1.0',
    'category': 'Point of Sale',
    'summary': 'Venta de intenciones de misa, certificados y boletas en el '
               'punto de venta de la notaría parroquial.',
    'description': """
XUBAX Gestión Parroquial — puente POS
=====================================

Conecta la notaría parroquial con el punto de venta:

* Productos precargados con el tarifario parroquial (intención de misa,
  misa especial, certificados, boletas de bautismo / 1.ª comunión /
  confirmación, micas y diezmo).
* Al vender un producto marcado como **intención**, el POS abre un diálogo
  para elegir la misa (fecha · hora · lugar), el tipo de intención y los
  nombres tal como deben imprimirse.
* Al cobrar el ticket se crea automáticamente la **intención pagada** en la
  celebración elegida: solo lo pagado entra a la hoja de intenciones.
* El detalle queda como nota en la línea, visible en pantalla y en el
  ticket impreso.
""",
    'author': 'XUBAX',
    'website': 'https://xubax.com',
    'license': 'OPL-1',
    'depends': ['point_of_sale', 'xb_parroquia'],
    'data': [
        'security/ir.model.access.csv',
        'data/pos_products_data.xml',
        'data/diocesano_data.xml',
        'report/diocesano_reports.xml',
        'report/diocesano_templates.xml',
        'views/product_template_views.xml',
        'views/diocesano_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'xb_parroquia_pos/static/src/app/popups/intencion_popup.js',
            'xb_parroquia_pos/static/src/app/popups/intencion_popup.xml',
            'xb_parroquia_pos/static/src/app/services/pos_store_patch.js',
        ],
    },
    'installable': True,
    'application': False,
}
