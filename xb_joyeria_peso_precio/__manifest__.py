# -*- coding: utf-8 -*-
{
    "name": "XB Joyería por peso — precio en la tienda y en la caja",
    "version": "19.0.1.0.0",
    "summary": "Las joyas cotizadas por metal (xb_precio_por_metal) muestran «Desde» en la tienda "
               "y la caja cobra el mismo precio que la web, calculado en el servidor",
    "description": """
Las joyas con ``xb_precio_por_metal`` se cotizan con el costo de su combinación
(metal del día + lista de materiales) y la lista de precios. Eso solo se puede
calcular en el servidor, así que:

* **Tienda**: en la lista de productos se muestra «Desde» con el precio en el oro
  de menor kilataje (en lugar de $0 / sin precio).
* **Caja**: al agregar la joya al ticket se pide el precio al servidor con la
  combinación elegida y la lista de precios de la orden (antes cobraba $0 porque
  el TPV usaba el costo de la ficha, que es 0).
""",
    "category": "Sales/Point of Sale",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["xb_joyeria_peso", "website_sale", "point_of_sale"],
    "data": ["views/templates.xml"],
    "assets": {
        "point_of_sale._assets_pos": ["xb_joyeria_peso_precio/static/src/app/pos_store_patch.js"],
    },
    "installable": True,
    "application": False,
}
