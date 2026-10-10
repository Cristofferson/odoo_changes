# -*- coding: utf-8 -*-
{
    "name": "XB Arras 3888",
    "version": "19.0.1.5.1",
    "summary": "Arras personalizadas (juego de 13): peso por frente y tamaño, imitación sin metal fino "
               "y metales solo-arras visibles en la tienda",
    "description": """
Arras 3888: 18 frentes × 8 vueltas × 3 tamaños × 9 metales, vendidas en juego de 13.

* Cada frente es una plantilla con ``xb_arras`` y la cotización por metal de
  ``xb_joyeria_peso`` (metal del día + hechura con el margen de la lista).
* El tamaño cambia el peso con un **factor por plantilla** (``xb_factor_peso`` en el valor
  de atributo de la plantilla): cada frente lleva distinto metal según su relieve.
* Imitación no tiene metal fino: el costo es solo la lista de materiales (material + baño).
* Metales ocultos en la web (imitación, plata, 22K) se muestran en las arras.
""",
    "category": "Sales/Sales",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["xb_joyeria_peso_precio", "website_sale", "point_of_sale", "mrp"],
    "data": [
        "views/product_views.xml",
        "views/templates.xml",
        "views/page_arras.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "xb_arras/static/src/arras.css",
            "xb_arras/static/src/arras.js",
        ],
    },
    "installable": True,
    "application": False,
}
