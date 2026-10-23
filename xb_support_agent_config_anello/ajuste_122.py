# xb_support_agent 1.22.0 — cambios puntuales sobre las instrucciones VIVAS (no se sube el archivo completo: el del repo
# trae «complementos», que nunca se activó). Anello: a la medida + otra forma de piedra; XUBAX: usuarios extra.
A = env["whatsapp.account"].sudo().browse(2); X = env["whatsapp.account"].sudo().browse(3)
assert A.name == "Anello" and X.name == "XUBAX"
viejo = "- Diseño propio, reparación o algo especial: sí se puede por ser fabricantes; recoge lo que quiere y pasa a una persona."
nuevo = ("- Pieza que NO está en el catálogo (diseño propio, nombre o letras, imagen religiosa, copiar una foto): sí se puede por ser fabricantes. "
         "Junta TODO lo necesario (pieza, metal y kilataje, piedras, medidas o largo, texto, para qué fecha, si recoge o se envía, y su nombre "
         "completo) y usa cotizacion_a_la_medida: el equipo le pone precio y, al autorizarla, le llega sola por aquí. No uses pasar_a_humano para eso.\n"
         "- Un modelo del catálogo con OTRA FORMA de piedra en zirconia (oval, pera, princesa…): NO es a la medida. Cotiza ese mismo modelo con "
         "crear_cotizacion y pon la forma en la nota (p. ej. «zirconia oval»); el precio es el mismo. Si es con diamante, la piedra cambia de "
         "precio: usa cotizacion_a_la_medida.\n"
         "- Reparación o ajuste: recoge lo que quiere (con foto) y pasa a una persona.")
txt = A.xb_sa_instructions or ""
if viejo in txt:
    A.xb_sa_instructions = txt.replace(viejo, nuevo)
elif "cotizacion_a_la_medida" not in txt:
    raise Exception("No encontré el renglón de «Diseño propio» en las instrucciones de Anello")
A.xb_sa_quote_approver_ids = [(6, 0, [2, 13])]   # Cristofferson y Jacky
viejo = "usa registrar_interes_compra y dile que un asesor le prepara la cotización."
nuevo = ("si son MÁS USUARIOS y lo pide el titular, haz tú la cotización con cotizar_usuarios_extra y mándale la liga; "
         "para lo demás usa registrar_interes_compra y dile que un asesor le prepara la cotización.")
txt = X.xb_sa_instructions or ""
if viejo in txt:
    X.xb_sa_instructions = txt.replace(viejo, nuevo)
elif "cotizar_usuarios_extra" not in txt:
    raise Exception("No encontré el renglón de ventas en las instrucciones de XUBAX")
print("OK Anello a la medida:", "cotizacion_a_la_medida" in A.xb_sa_instructions, "| autorizan:", A.xb_sa_quote_approver_ids.mapped("name"),
      "| XUBAX usuarios extra:", "cotizar_usuarios_extra" in X.xb_sa_instructions)
