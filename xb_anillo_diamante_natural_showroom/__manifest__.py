# -*- coding: utf-8 -*-
{
    "name": "Anillos: el diamante natural elegido llega al muro",
    "version": "19.0.1.5.0",
    "summary": "Puente: al mandar al muro un anillo con «Diamante natural», viaja el diamante que eligió "
               "el cliente (precio montadura + diamante y sus datos)",
    "description": """
Une xb_anillo_diamante_natural (tienda y kiosco) con el muro (xb_showroom_wall):

* Desde la tienda (tableta del vendedor) y desde el kiosco, el anillo con «Diamante natural» llega al
  muro con el diamante elegido: el precio es montadura + diamante y los datos dicen forma, quilates,
  color, pureza, corte y certificado de ESE diamante.
* Sin diamante elegido todo sigue igual («se cotiza aparte»).
""",
    "category": "Website/eCommerce",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["xb_anillo_diamante_natural_self_order", "xb_showroom_wall_self_order"],
    "data": [],
    "assets": {
        "pos_self_order.assets": [
            "xb_anillo_diamante_natural_showroom/static/src/kiosk/*",
        ],
    },
    "auto_install": True,
    "installable": True,
    "application": False,
}
