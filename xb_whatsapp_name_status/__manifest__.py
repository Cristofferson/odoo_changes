# -*- coding: utf-8 -*-
{
    "name": "XB WhatsApp — estado del nombre visible",
    "version": "19.0.1.0.0",
    "summary": "Muestra si Meta aprobó o rechazó el nombre visible de cada número, y por qué",
    "description": """
Meta revisa el nombre visible de cada número de WhatsApp y avisa el resultado con el
webhook ``phone_number_name_update`` (decisión y motivo del rechazo). El controlador
nativo de Odoo lo ignora en silencio: este módulo lo recibe, lo guarda en la cuenta de
WhatsApp, lo deja en su historial y avisa a los administradores.

También agrega el botón «Consultar nombre en Meta» para ver el estado en cualquier momento.

Hay que suscribir el campo ``phone_number_name_update`` en los webhooks de la app de Meta.
""",
    "category": "Productivity/WhatsApp",
    "author": "XUBAX",
    "license": "OPL-1",
    "depends": ["whatsapp"],
    "data": ["views/whatsapp_account_views.xml"],
    "installable": True,
    "application": False,
}
