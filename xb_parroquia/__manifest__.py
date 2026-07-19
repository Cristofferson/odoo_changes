{
    'name': 'XUBAX Gestión Parroquial',
    'version': '19.0.2.1.0',
    'category': 'Services',
    'summary': 'Misas, intenciones y hoja de intenciones imprimible para la notaría parroquial.',
    'description': """
XUBAX Gestión Parroquial
========================

Digitaliza el día a día de la notaría parroquial:

* Catálogo de **lugares de celebración** (templo parroquial, capillas y
  comunidades).
* **Celebraciones** (misas diarias, dominicales, especiales, funerales,
  bodas, XV años, clausuras, presentaciones de matrimonio) con fecha, hora,
  lugar y celebrante.
* **Intenciones de misa** por celebración, agrupadas como las escribe la
  notaría: intención destacada, vivos, por la salud de, familias, difuntos
  (aniversarios luctuosos, fin de novenario) y desaparecidos.
* **Hoja de intenciones** imprimible por día o rango de fechas, con el mismo
  formato de tabla (CELEBRA | HORA | LUGAR | INTENCIONES) que la parroquia
  lleva al templo cada día.

Fase 2 (módulo puente POS): venta de intenciones, certificados y boletas en
el punto de venta; solo las intenciones pagadas entran a la hoja.
""",
    'author': 'XUBAX',
    'website': 'https://xubax.com',
    'license': 'OPL-1',
    'depends': ['base', 'mail'],
    'data': [
        'security/parroquia_security.xml',
        'security/ir.model.access.csv',
        'data/parroquia_lugar_data.xml',
        'views/parroquia_lugar_views.xml',
        'views/parroquia_celebracion_views.xml',
        'views/parroquia_intencion_views.xml',
        'wizard/hoja_intenciones_wizard_views.xml',
        'report/hoja_intenciones_report.xml',
        'report/hoja_intenciones_templates.xml',
        'report/certificado_report.xml',
        'report/certificado_templates.xml',
        'views/parroquia_partida_views.xml',
        'views/parroquia_menus.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
}
