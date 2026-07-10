{
    'name': 'NOVADIAM Theme',
    'description': 'Tema NOVADIAM — marketplace de anillos de compromiso seminuevos (novadiam.mx)',
    'category': 'Theme/eCommerce',
    'summary': 'Anillos de compromiso seminuevos: compra protegida, verificación GIA y certificado digital',
    'version': '19.0.1.0.0',
    'author': 'XUBAX',
    'license': 'OPL-1',
    'depends': ['website_sale', 'website_crm'],
    'data': [
        'views/footer.xml',
        'views/menus.xml',
        'views/pages.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'theme_novadiam/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'theme_novadiam/static/src/scss/theme.scss',
        ],
    },
}
