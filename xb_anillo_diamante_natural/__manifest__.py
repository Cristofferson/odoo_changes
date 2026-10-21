# -*- coding: utf-8 -*-
{
    "name": "Anillos: elegir el diamante natural en la tienda",
    "version": "19.0.1.0.0",
    "summary": "Al elegir «Diamante natural» en un anillo, el cliente escoge un diamante del inventario "
               "y el carrito lleva el anillo y ese diamante",
    "description": """
Anillos cotizados por metal (``xb_precio_por_metal``) con la opción de piedra «Diamante natural»:

* **Ficha del anillo (web)**: al elegir «Diamante natural» aparece la lista de diamantes naturales
  publicados y con existencia (cualquier forma), con forma, quilates, color, pureza, certificado y
  precio. El precio que se ve pasa a ser montadura + diamante.
* **Carrito**: el anillo y el diamante elegido entran juntos; el diamante queda ligado al anillo
  (si se quita el anillo, se quita el diamante). Cada anillo con diamante natural es una pieza única
  (cantidad 1).
* **Sin diamante elegido** no se puede agregar el anillo al carrito, y un carrito con un anillo
  «Diamante natural» sin su diamante no se puede pagar.
""",
    "category": "Website/eCommerce",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["website_sale_stock", "xb_joyeria_peso_precio", "xb_gema_ficha_web"],
    "data": [],
    "assets": {
        "web.assets_frontend": [
            "xb_anillo_diamante_natural/static/src/scss/diamante_natural.scss",
            "xb_anillo_diamante_natural/static/src/js/diamante_natural.js",
        ],
    },
    "installable": True,
    "application": False,
}
