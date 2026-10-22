{
    'name': 'XB Marketplace',
    'summary': 'Marketplace de piezas seminuevas: vendedores, anuncios moderados, verificación en taller y certificado digital',
    'description': """
Marketplace multivendedor para piezas únicas (joyería seminueva).

Núcleo (F4b):
- Vendedores particulares (marketplace.seller) con identidad protegida.
- Anuncios = product.template únicos con flujo de moderación y estados
  post-venta (taller → verificación → certificado → envío → inspección →
  liberación), según el proceso NOVADIAM.
- Wizard de publicación en portal (/marketplace/vender) + "Mis anuncios".
- Atributos nativos (Marca, Estilo, Metal, Color, Claridad, Corte,
  Certificadora, Origen) para filtros de tienda.

Fases siguientes: escrow contable, checkout con personalizaciones,
mensajería enmascarada y certificado digital público.
""",
    'category': 'Website/eCommerce',
    'version': '19.0.2.3.0',
    'author': 'XUBAX',
    'license': 'OPL-1',
    'price': 299.00,
    'currency': 'USD',
    'depends': ['website_sale', 'portal', 'mail', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/attributes.xml',
        'data/marketplace_data.xml',
        'data/products.xml',
        'data/cron.xml',
        'views/res_partner_views.xml',
        'views/marketplace_views.xml',
        'views/portal_templates.xml',
        'report/nv_avaluo_report.xml',
        'views/nv_avaluo_views.xml',
        'data/nv_avaluo_data.xml',
    ],
    'post_init_hook': '_post_init_marketplace',
    'application': True,
}
