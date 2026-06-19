{
    "name": "Novadiam - Etiquetas de Diamante (ZPL)",
    "version": "19.0.1.2.8",
    "category": "Inventory",
    "summary": "Plantillas ZPL para etiquetas de producto: Joyeria (mejorada) y Diamond Papers (certificado de diamante)",
    "author": "Diamane / Cristofferson Reyes",
    "license": "LGPL-3",
    # Depende de print_direct_odoo para cargar DESPUES y ganar la redefinicion
    # de la plantilla stock.label_product_product_view (que print_direct dejo plana/rota).
    "depends": ["stock", "product", "print_direct_odoo"],
    "data": [
        "views/product_label_zpl.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
