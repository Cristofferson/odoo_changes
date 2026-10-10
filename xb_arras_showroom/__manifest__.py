# -*- coding: utf-8 -*-
{
    "name": "XB Arras 3888 en el muro del showroom",
    "version": "19.0.1.1.0",
    "summary": "Pantalla propia de Arras 3888 en el videowall: frente, vuelta, tamaños y precios",
    "description": """
Puente entre ``xb_arras`` y ``xb_showroom_wall``. Cuando el muro recibe una ficha de Arras 3888
la dibuja en tres pantallas: el frente en grande, la vuelta elegida (con los 13 valores si los
lleva) y una tercera con los tres tamaños a escala, la tabla de precios por metal y tamaño
(con la elección marcada) y el QR.
""",
    "category": "Website/Website",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["xb_arras", "xb_showroom_wall"],
    "auto_install": True,
    "installable": True,
}
