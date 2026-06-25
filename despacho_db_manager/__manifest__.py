{
    'name': 'Despacho - Administración de Bases de Datos',
    'version': '19.0.1.33.0',
    'summary': 'Inventario y operaciones (alta, censo multi-servidor, baja, respaldo, refresh de prueba) de las bases de datos de clientes, sobre la app nativa Databases',
    'description': """
Administración de bases de datos de clientes (XUBAX)
===================================================
Amplía la app nativa **Databases** de Odoo Enterprise para el despacho:

* **Inventario auto-descubierto** de las bases de datos de varios servidores
  (este servidor + servidores remotos por SSH, solo lectura): tamaño, filestore,
  dominio, módulos y último respaldo, como registros premise.
* **Alta de cliente nuevo** (BD + nginx + DNS + SSL + correo) desde un botón,
  reutilizando la infraestructura segura cola → systemd → script (Odoo nunca
  recibe privilegios de root).

Fase 1: alta + censo. Fase 2 (posterior): baja, respaldo, correo, refresh de test.
""",
    'category': 'Administration',
    'author': 'XUBAX',
    'license': 'LGPL-3',
    'depends': ['databases', 'sale_subscription'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/db_operation_views.xml',
        'views/project_project_views.xml',
        'views/db_dashboard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'despacho_db_manager/static/src/css/despacho_db_manager.css',
        ],
    },
    'application': False,
    'installable': True,
}
