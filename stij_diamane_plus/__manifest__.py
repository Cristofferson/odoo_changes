# -*- coding: utf-8 -*-
{
    "name": "DIAMANE STIJ Plus — Seguridad y Vistas",
    "summary": "Trampa de pieza robada y conteo de vistas de cliente sobre el visor STIJ",
    "description": """
Extensión DIAMANE-específica sobre STIJ (stij_website). Módulo COMPAÑERO: no
modifica el repo de Gerardo, lo extiende por herencia.

Fase 0 — Vista de cliente por pieza:
  Cuenta cada apertura del visor por un cliente (no staff) en stock.lot.

Fase 1 — Trampa de pieza robada:
  Cuando una pieza Robada/Extraviada se escanea, registra el avistamiento
  (scan_alert con IP/geoip) y alerta al dueño y a la tienda. Modo señuelo o
  disuasivo configurable.
""",
    "version": "19.0.1.2.0",
    "category": "Inventory",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "company": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["stij_website", "stock", "mail"],
    "data": [
        "views/res_company_views.xml",
        "views/stock_lot_views.xml",
    ],
    "installable": True,
    "application": False,
}
