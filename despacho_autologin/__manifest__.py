{
    'name': 'Despacho - Auto-login (magic link)',
    'version': '1.0.2',
    'summary': 'Inicio de sesion por magic-link firmado para el "Conectar" del despacho XUBAX',
    'description': """
Auto-login del despacho (compañero de despacho_db_manager)
==========================================================
Modulo MINUSCULO que se instala en CADA base de datos gestionada por el despacho.

Expone el endpoint ``/despacho/autologin?token=...``. El manager
(``despacho_db_manager``, en la BD del despacho) genera un token:

* **firmado con HMAC-SHA256** usando un secreto propio de esta BD
  (``ir.config_parameter`` ``despacho_autologin.secret``),
* de **vida corta** (~30 s) y de **un solo uso** (nonce registrado),

y el boton "Conectar" del listado de Databases redirige aqui. El controlador
valida la firma/caducidad/unicidad y abre la sesion del usuario indicado
(normalmente admin) sin pedir contraseña, redirigiendo a ``/odoo``.

Sin el secreto correcto el endpoint nunca inicia sesion: solo redirige al login.
Compatible con Odoo 17.2+ (usa ``request.session.finalize``).
""",
    'category': 'Administration',
    'author': 'XUBAX',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'application': False,
    'installable': True,
}
