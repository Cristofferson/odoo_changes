# -*- coding: utf-8 -*-
{
    "name": "Tienda en línea solo para clientes verificados",
    "version": "19.0.1.0.0",
    "summary": "La tienda de un sitio solo se abre a contactos con una etiqueta (p. ej. «Joyero verificado»).",
    "description": """
Tienda B2B de verdad
====================

Con «solo usuarios con sesión» Odoo deja entrar a la tienda a CUALQUIER usuario
que no sea el público. Como los sitios de una misma base comparten usuarios, quien
se registra gratis en otro sitio entra también a la tienda B2B.

Este módulo agrega al sitio la opción «Tienda solo para contactos con la etiqueta»:
si se llena, la tienda (catálogo, ficha, carrito y menú) solo se abre a usuarios
internos y a contactos (o su empresa) con esa etiqueta. A los demás, ya con sesión,
se les manda a la liga de «a dónde mandar a quien no está verificado».
""",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "category": "Website/eCommerce",
    "license": "OPL-1",
    "depends": ["website_sale"],
    "data": ["views/website_views.xml"],
    "installable": True,
    "application": False,
}
