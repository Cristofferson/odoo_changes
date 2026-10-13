# -*- coding: utf-8 -*-
{
    "name": "XB Support Reader",
    "version": "1.0.0",
    "summary": "Puerta cerrada para que el agente de soporte de XUBAX consulte (solo lectura) las bases de este servidor.",
    "description": "Módulo de servidor (server_wide_modules): no se instala en ninguna base. Recibe consultas firmadas "
                   "(HMAC) del agente de WhatsApp de XUBAX y las ejecuta con los mismos candados de solo lectura.",
    "author": "XUBAX",
    "license": "LGPL-3",
    "depends": ["base"],
    "installable": True,
    "application": False,
}
