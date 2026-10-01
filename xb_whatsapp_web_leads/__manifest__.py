# -*- coding: utf-8 -*-
{
    "name": "XB WhatsApp — prospectos desde el sitio web y anuncios",
    "version": "19.0.1.0.0",
    "summary": "Cuenta los clics al botón de WhatsApp del sitio, convierte esas conversaciones y las de anuncios "
               "Click-to-WhatsApp en prospectos de CRM, y avisa por WhatsApp de los carritos abandonados",
    "description": """
* **Clics**: el botón de WhatsApp del sitio registra cada clic (página y producto).
* **Prospectos**: cuando llega a WhatsApp un mensaje que salió del sitio (lleva la
  liga del sitio) o de un anuncio Click-to-WhatsApp de Meta (trae ``referral``),
  se crea —o se reutiliza— un prospecto en CRM con el producto, el origen y la
  etiqueta, y la conversación queda ligada a él.
* **Carrito abandonado**: cada hora busca carritos del sitio con cliente
  identificado y teléfono, sin moverse desde hace N horas, y les manda UNA vez
  la plantilla configurada en el sitio web.
Todo se configura por sitio web y nace APAGADO.
""",
    "category": "Productivity/WhatsApp",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["whatsapp", "website_sale", "crm", "utm"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/xb_wa_click_views.xml",
        "views/website_views.xml",
    ],
    "installable": True,
    "application": False,
}
