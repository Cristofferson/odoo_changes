# -*- coding: utf-8 -*-
{
    "name": "Anillos: elegir el diamante natural en el kiosco",
    "version": "19.0.1.0.0",
    "summary": "Puente: en el kiosco, al elegir «Diamante natural» el cliente escoge el diamante y "
               "el pedido lleva el anillo y ese diamante",
    "description": """
Igual que en la tienda en línea (xb_anillo_diamante_natural), en el kiosco:

* Al elegir «Diamante natural» en un anillo aparece la lista de diamantes naturales con existencia,
  de cualquier forma, con su precio. La selección muestra montadura + diamante.
* Sin diamante elegido no se puede agregar el anillo. Al agregarlo entran dos renglones: el anillo
  (cantidad 1) y el diamante.
* El kiosco carga esos diamantes aunque su categoría no esté en el kiosco (no se muestran en la
  lista de productos).
* El servidor rechaza un pedido con más anillos «Diamante natural» que diamantes naturales.
""",
    "category": "Point of Sale",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["xb_anillo_diamante_natural", "xb_joyeria_peso_precio_self_order"],
    "data": [],
    "assets": {
        "pos_self_order.assets": [
            "xb_anillo_diamante_natural/static/src/scss/diamante_natural.scss",
            "xb_anillo_diamante_natural_self_order/static/src/app/diamante_natural_kiosco.js",
            "xb_anillo_diamante_natural_self_order/static/src/app/diamante_natural_kiosco.xml",
        ],
    },
    "auto_install": True,
    "installable": True,
    "application": False,
}
