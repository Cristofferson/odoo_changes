# xb_support_agent 1.23.0: tope de largo de cada respuesta por agente (decisión del usuario 23-oct).
topes = {2: ("Anello", 350), 6: ("DIAMANE", 350), 3: ("XUBAX", 450)}
for acc_id, (nombre, tope) in topes.items():
    acc = env["whatsapp.account"].sudo().browse(acc_id)
    assert acc.name == nombre, (acc_id, acc.name)
    acc.xb_sa_max_chars = tope
    print("OK", nombre, "tope", acc.xb_sa_max_chars, "| en el prompt:", f"máximo {tope} caracteres" in acc._xb_sa_system_prompt())
