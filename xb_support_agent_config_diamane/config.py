# Configura el agente de WhatsApp de DIAMANE (cuenta 6). Se corre con odoo shell; RUTA = carpeta de este archivo.
import os
RUTA = os.environ.get("XB_DIAMANE_CFG", "/home/ubuntu/repos/odoo_changes/xb_support_agent_config_diamane")
D = env["whatsapp.account"].sudo().browse(6)
A = env["whatsapp.account"].sudo().browse(2)
assert D.name == "DIAMANE" and A.name == "Anello"
yo = env["res.users"].sudo().browse(2)
lista = env["product.pricelist"].sudo().browse(3)
assert lista.name == "DIAMANE"
# Cita: videollamada con DIAMANE (copia de la de Anello, con Cristofferson y en el sitio de DIAMANE)
Tipo = env["appointment.type"].sudo()
cita = Tipo.with_context(active_test=False).search([("name", "=", "Videollamada con DIAMANE")], limit=1)
if not cita:
    cita = Tipo.browse(6).copy({"name": "Videollamada con DIAMANE"})
cita.write({"name": "Videollamada con DIAMANE", "staff_user_ids": [(6, 0, yo.ids)], "website_id": 3, "is_published": True, "active": True})
# Base de conocimiento solo para DIAMANE
ns = {}
exec(open(os.path.join(RUTA, "kb.py"), encoding="utf-8").read(), ns)
Kn = env["xb.support.knowledge"].sudo()
# Los datos para transferir no viven en el repo: salen del método de pago «Transferencia bancaria» de Odoo.
import re
transferencia = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(env["payment.provider"].sudo().browse(19).pending_msg or "")))
transferencia = transferencia.replace("Use los siguientes detalles de transferencia", "").replace("Cuentas bancarias", "").strip()
assert "CLABE" in transferencia, "Sin datos de transferencia en el método de pago 19"
Kn.search([("name", "=", "Compras, pagos y envíos"), ("account_ids", "in", D.ids)]).write({"active": False})
for kind, nombre, contenido in ns["KB"]:
    contenido = contenido.replace("{DATOS_TRANSFERENCIA}", transferencia)
    k = Kn.search([("name", "=", nombre), ("account_ids", "in", D.ids)], limit=1)
    vals = {"kind": kind, "name": nombre, "content": contenido, "account_ids": [(6, 0, D.ids)]}
    k.write(vals) if k else Kn.create(vals)
# Verificación de joyeros: una sola etiqueta para WhatsApp y para la tienda de diamane.mx
Cat = env["res.partner.category"].sudo()
verificado = Cat.search([("name", "=", "Joyero verificado")], limit=1) or Cat.create({"name": "Joyero verificado"})
compradores = env["sale.order"].sudo().search([("company_id", "=", 4), ("state", "=", "sale")]).partner_id.commercial_partner_id
compradores.write({"category_id": [(4, verificado.id)]})
web = env["website"].browse(3)
if "xb_b2b_category_id" in web._fields:
    web.write({"xb_b2b_category_id": verificado.id,
               "xb_b2b_denied_url": "https://wa.me/524437337427?text=Hola%2C%20quiero%20verificar%20mi%20joyer%C3%ADa%20con%20DIAMANE"})
D.write({
    "xb_sa_store_b2b_category_id": verificado.id,
    "xb_sa_profile": "tienda", "xb_sa_company_name": "DIAMANE",
    "xb_sa_instructions": open(os.path.join(RUTA, "instrucciones.txt"), encoding="utf-8").read().strip(),
    "xb_sa_api_key": A.xb_sa_api_key, "xb_sa_openai_key": A.xb_sa_openai_key,
    "xb_sa_model": A.xb_sa_model, "xb_sa_effort": A.xb_sa_effort,
    "xb_sa_support_user_ids": [(6, 0, yo.ids)], "xb_sa_sales_user_ids": [(6, 0, yo.ids)], "xb_sa_demo_user_ids": [(6, 0, yo.ids)],
    "xb_sa_appointment_type_id": cita.id, "xb_sa_video_appointment_type_id": False,
    "xb_sa_store_pricelist_id": lista.id, "xb_sa_store_autonomous": True, "xb_sa_store_prepayment": 0.10, "xb_sa_pause_hours": 3,
    "xb_sa_hold_message": "Gracias por escribir a DIAMANE 💎. Ya le avisé a una persona del equipo y te contestará lo antes posible.",
    "xb_sa_only_numbers": False, "xb_sa_shadow": True, "xb_sa_enabled": True,
})
print("OK agente DIAMANE:", D.xb_sa_profile, "| encendido:", D.xb_sa_enabled, "| ensayo:", D.xb_sa_shadow,
      "| llave:", "sí" if D.xb_sa_api_key else "NO", "| cita:", cita.id, cita.name,
      "| conocimientos:", Kn.search_count([("account_ids", "in", D.ids)]), "| lista:", D.xb_sa_store_pricelist_id.name, "| vende solo:", D.xb_sa_store_autonomous, D.xb_sa_store_prepayment)
print("OK verificación:", verificado.name, "| ya verificados:", ", ".join(compradores.mapped("name")) or "—",
      "| tienda diamane.mx:", web.xb_b2b_category_id.name if "xb_b2b_category_id" in web._fields else "módulo no instalado")
