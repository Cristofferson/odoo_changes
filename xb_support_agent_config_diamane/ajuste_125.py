# Ajuste 125 (29-oct-2026): identificación y certificación de piedras para cualquier persona + respuesta a 👽.
# Se corre con odoo shell con INSTRUCCIONES y KB ya inyectados arriba (ver ~/scripts/xbsa_125_certificacion.sh).
D = env["whatsapp.account"].sudo().browse(6)
assert D.name == "DIAMANE"
Kn = env["xb.support.knowledge"].sudo()
for kind, nombre, contenido in KB:
    if nombre not in ("Solo joyeros", "Identificación y certificación de piedras"):
        continue
    k = Kn.search([("name", "=", nombre), ("account_ids", "in", D.ids)], limit=1)
    vals = {"kind": kind, "name": nombre, "content": contenido, "account_ids": [(6, 0, D.ids)]}
    k.write(vals) if k else Kn.create(vals)
D.xb_sa_instructions = INSTRUCCIONES
print("OK certificación en instrucciones:", "2c. Si quiere que evaluemos" in D.xb_sa_instructions,
      "| conocimientos:", Kn.search_count([("account_ids", "in", D.ids), ("name", "=", "Identificación y certificación de piedras")]))
ch = env["discuss.channel"].sudo().browse(440)
# canal 440: el cliente que preguntó por la certificación (el número no se guarda en el repo)
ch._xb_sa_send("¡Claro! Así funciona: traes la piedra a una cita en nuestra oficina en Morelia y ahí la evaluamos; "
               "la evaluación toma unas 2 horas. Es un servicio de identificación y certificación: nosotros no compramos piedras. "
               "El costo te lo confirmamos al agendar tu cita. ¿Qué día y a qué hora te acomoda traerla? 💎")
ch.xb_sa_paused_until = False
print("OK 👽")
