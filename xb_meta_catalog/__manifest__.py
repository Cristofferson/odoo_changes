# -*- coding: utf-8 -*-
{
    "name": "Anello — Catálogo para Meta / WhatsApp",
    "version": "19.0.1.0.1",
    "summary": "Feed de productos a nivel MODELO para el catálogo de "
               "WhatsApp / Commerce Manager.",
    "description": """
Catálogo de Meta a nivel modelo, no a nivel talla
==================================================

Por que NO se usa el feed nativo
--------------------------------
``website_sale`` ya trae un ``product.feed`` (formato Google Merchant Center,
ruta ``/gmc.xml``) y **se probo primero**. No sirve para esta joyeria:

* trabaja a nivel **variante**: las 194 plantillas publicadas de Anello
  explotan a **17,136 variantes** (una sola argolla llega a 897 combinaciones
  de talla x kilataje x ancho);
* Odoo mismo lo rechaza: ``_check_product_limit`` topa en **5,000** por feed;
* y aunque cupiera, un catalogo de WhatsApp con 17 mil SKUs de tallas es
  **inservible para navegar**: nadie escoge talla en un carrusel.

Para joyeria lo correcto es **una entrada por modelo** y acordar la talla en el
chat, que es como se vende de todos modos.

Formato
-------
Se emite el **mismo XML de Google Merchant Center** (RSS 2.0 + namespace ``g:``)
porque Commerce Manager de Meta acepta ese formato tal cual, y asi el feed
sirve igual si algun dia se conecta a Google.

Guardarrailes
-------------
* **piso de precio** (``min_price``, default 1): de aqui salieron los 63
  productos a $0/$1 que estuvieron comprables en anello.mx. Nada por debajo
  del piso entra al catalogo, pase lo que pase en la ficha del producto;
* solo publicados y **solo con foto** (Meta rechaza items sin imagen);
* precio redondeado a 2 decimales (la BD trae cosas como ``8704.567386``);
* ruta protegida por **token en la URL** (``ir.config_parameter``), el mismo
  patron ya adoptado para los bridges MCP.

Configuracion (``ir.config_parameter``)
---------------------------------------
=====================================  ==========  =========================
Parametro                              Default     Que hace
=====================================  ==========  =========================
``xb_meta_catalog.token``              (generado)  secreto de la URL
``xb_meta_catalog.website_id``         ``1``       sitio Anello
``xb_meta_catalog.min_price``          ``1``       piso de precio
``xb_meta_catalog.brand``              ``Anello``  marca del feed
=====================================  ==========  =========================
""",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "category": "Website/eCommerce",
    "license": "OPL-1",
    "depends": ["website_sale"],
    "data": ["data/ir_config_parameter.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
