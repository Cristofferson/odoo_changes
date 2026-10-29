# Anello: diamante de LABORATORIO de otra forma = mismo precio que el redondo (decisión del usuario 28-oct). Solo el natural va a la medida.
A = env["whatsapp.account"].sudo().browse(2)
assert A.name == "Anello"
viejo = ("- Un modelo del catálogo con OTRA FORMA de piedra en zirconia (oval, pera, princesa…): NO es a la medida. Cotiza ese mismo modelo con "
         "crear_cotizacion y pon la forma en la nota (p. ej. «zirconia oval»); el precio es el mismo. Si es con diamante, la piedra cambia de "
         "precio: usa cotizacion_a_la_medida.")
nuevo = ("- Un modelo del catálogo con OTRA FORMA de piedra (oval, pera, princesa, esmeralda…) en zirconia o en DIAMANTE DE LABORATORIO: NO es a la "
         "medida. Cotiza ese mismo modelo con crear_cotizacion, con la piedra y el quilataje que pidió (el laboratorio cuesta lo mismo en "
         "cualquier forma), y pon la forma en la nota (p. ej. «diamante de laboratorio oval 1 ct»). Solo si es DIAMANTE NATURAL de otra forma, "
         "la piedra cambia de precio: usa cotizacion_a_la_medida.")
txt = A.xb_sa_instructions or ""
if viejo in txt:
    A.xb_sa_instructions = txt.replace(viejo, nuevo)
elif nuevo not in txt:
    raise Exception("No encontré el renglón de OTRA FORMA en las instrucciones de Anello")
print("OK laboratorio cualquier forma:", nuevo in A.xb_sa_instructions)
