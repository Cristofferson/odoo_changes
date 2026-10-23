# Configura el agente de WhatsApp de GR Consteladores Familiares (BD grconsteladores). Se corre con odoo shell.
# Las llaves de IA llegan por variables de entorno (XB_ANTHROPIC, XB_OPENAI): no viven en el repo.
import os
from odoo.addons.xb_business_agent.models.whatsapp_account import XB_DEFAULT_INSTRUCTIONS_ES
RUTA = os.environ.get("XB_GRC_CFG", os.path.dirname(os.path.abspath("config.py")))
acc = env["whatsapp.account"].sudo().search([("phone_uid", "=", "1370884546106814")], limit=1)
assert acc, "No está la cuenta de WhatsApp del 443 379 5031"
jorge = env["res.users"].sudo().browse(5)
ns = {}
exec(open(os.path.join(RUTA, "kb.py"), encoding="utf-8").read(), ns)
Kn = env["xb.business.knowledge"].sudo()
for i, (kind, nombre, contenido) in enumerate(ns["KB"]):
    k = Kn.with_context(active_test=False).search([("name", "=", nombre)], limit=1)
    vals = {"kind": kind, "name": nombre, "content": contenido, "sequence": 10 + i, "active": True, "account_ids": [(6, 0, acc.ids)]}
    k.write(vals) if k else Kn.create(vals)
vals = {
    "xb_ba_company_name": "GR Consteladores Familiares",
    "xb_ba_instructions": XB_DEFAULT_INSTRUCTIONS_ES + (
        "\nLARGO DE CADA MENSAJE (regla firme): máximo 300 caracteres, unos 4 renglones en el celular. Una sola idea y, si hace "
        "falta, UNA pregunta al final. No repitas lo que ya dijiste (precios, dirección, fecha del taller), no agregues lo que no "
        "pidió y no cierres con relleno. Si hay mucho que decir, da lo esencial y pregunta si quiere el detalle."),
    "xb_ba_user_ids": [(6, 0, jorge.ids)], "xb_ba_team_id": env.ref("sales_team.team_sales_department").id,
    "xb_ba_model": "claude-sonnet-5-5", "xb_ba_effort": "medium", "xb_ba_pause_hours": 12,
    "xb_ba_hold_message": "Gracias por escribir a GR Consteladores Familiares. Ya le avisé a Gicela y Raúl y le responderán en cuanto puedan.",
    # Prueba: contesta de verdad solo al celular de Raúl; los demás clientes no reciben nada.
    "xb_ba_shadow": False, "xb_ba_only_numbers": "+524432667677", "xb_ba_enabled": True,
}
if os.environ.get("XB_ANTHROPIC"):
    vals["xb_ba_api_key"] = os.environ["XB_ANTHROPIC"]
if os.environ.get("XB_OPENAI"):
    vals["xb_ba_openai_key"] = os.environ["XB_OPENAI"]
acc.write(vals)
print("OK agente:", acc.id, acc.xb_ba_company_name, "| encendido:", acc.xb_ba_enabled, "| ensayo:", acc.xb_ba_shadow, "| solo a:", acc.xb_ba_only_numbers,
      "| llave:", "sí" if acc.xb_ba_api_key else "NO", "| voz:", "sí" if acc.xb_ba_openai_key else "NO",
      "| conocimientos:", Kn.search_count([]), "| citas:", acc.xb_ba_appointment_type_ids.mapped("name"), "| atiende:", acc.xb_ba_user_ids.mapped("name"))
