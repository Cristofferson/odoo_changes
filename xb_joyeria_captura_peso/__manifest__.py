# -*- coding: utf-8 -*-
{
    "name": "XB Joyería · captura de pesos",
    "version": "19.0.1.0.0",
    "summary": "Pantalla para capturar el peso de cada joya; al guardarlo la joya se cotiza "
               "sola por metal, con su hechura",
    "description": """
Una lista editable (Ventas › Productos › Captura de pesos) con las joyas de una
categoría —de entrada las argollas—: foto, referencia, a qué metal, talla y ancho
se pesa la pieza, el peso, la hechura y el precio «desde» que resulta.

Al capturar el peso:

* se enciende «Cotizar por peso de metal» (si la joya ofrece un metal con ley);
* si la joya no tiene lista de materiales se le crea una con la hechura estándar
  (parámetro ``xb_joyeria_captura_peso.hechura``, 600 de entrada).
""",
    "category": "Sales/Sales",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["xb_joyeria_peso_precio", "mrp", "sale"],
    "data": [
        "data/ir_config_parameter.xml",
        "views/product_views.xml",
    ],
    "installable": True,
    "application": False,
}
