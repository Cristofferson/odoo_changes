{
    'name': 'XUBAX Gestión Parroquial — Sitio Web',
    'version': '19.0.1.2.1',
    'category': 'Website',
    'summary': 'Sitio público de la parroquia: horarios de misa, avisos '
               'parroquiales y servicios.',
    'description': """
XUBAX Gestión Parroquial — Sitio Web
====================================

* **Avisos parroquiales**: se capturan en la app Parroquia, se publican en
  el sitio y se imprime la hoja que se lee el fin de semana.
* **/horarios**: horarios de misa de los próximos días, tomados en vivo de
  las celebraciones agendadas (sin intenciones).
* **/avisos**: avisos vigentes.
* **/sacramentos**: requisitos y tarifas de la notaría.
* Portada editable con la identidad de la parroquia.
""",
    'author': 'XUBAX',
    'website': 'https://xubax.com',
    'license': 'OPL-1',
    'depends': ['xb_parroquia', 'website'],
    'data': [
        'security/ir.model.access.csv',
        'data/parroquia_aviso_data.xml',
        'views/parroquia_aviso_views.xml',
        'views/parroquia_dia_liturgico_views.xml',
        'data/dia_liturgico_cron.xml',
        'report/avisos_report.xml',
        'report/avisos_templates.xml',
        'views/website_templates.xml',
        'data/website_pages_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'xb_parroquia_website/static/src/css/forja.css',
        ],
    },
    'installable': True,
    'application': False,
}
