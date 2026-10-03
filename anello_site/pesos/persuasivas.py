import json, re, hashlib
exec(open('descripciones.py').read())   # D
POOLS = [
 (r'tensi', ['Un anillo moderno y seguro de sí mismo, para quien no quiere un compromiso convencional.',
             'La piedra parece flotar: un diseño que se nota desde el primer instante.',
             'Arquitectura y brillo en una sola pieza, pensada para durar toda una vida.']),
 (r'pav[eé]|\bcanal\b|hileras|brillantes', ['Cada piedra suma luz: brilla desde cualquier ángulo, de día y de noche.',
             'Más destellos en cada movimiento de la mano, sin perder elegancia.',
             'Un brillo generoso que convierte el momento de la propuesta en algo inolvidable.']),
 (r'grabad|filigrana|vintage|volut|espiral|perlad', ['El encanto de las joyas de antes, hecho a mano hoy por orfebres mexicanos.',
             'Un detalle artesanal que cuenta una historia: romántico, distinto y para siempre.']),
 (r'tres piedras|trilog|cinco piedras|racimo|flor', ['Varias piedras que cuentan su historia juntos: pasado, presente y futuro.',
             'Una composición llena de significado y de brillo, para un sí que se recuerde.']),
 (r'princesa', ['Líneas rectas y un brillo intenso: elegancia contemporánea para una propuesta segura.',
             'La talla princesa en su versión más pura, para quien prefiere lo moderno.']),
 (r'bisel|semibisel|engaste cuadrado', ['La piedra va protegida por el metal: ideal para el día a día sin perder sofisticación.',
             'Práctico y elegante: un engaste que cuida la piedra y se ve impecable.']),
 (r'bypass|cruzad|envolvente|ondulad|uve|corazón', ['Un trazo con movimiento que se siente personal y lleno de intención.',
             'Original sin ser exagerado: un diseño que se reconoce en cuanto lo ves.']),
 (r'banda ancha|hombros anchos|abombad|muy ancha', ['Presencia y carácter en el dedo: una pieza que se siente sólida y especial.',
             'Una banda con presencia para una piedra protagonista.']),
 (r'catedral', ['Los arcos elevan la piedra para que capture toda la luz: el clásico que nunca falla.',
             'Elegancia atemporal con la piedra elevada como protagonista.']),
 (r'', ['El solitario de siempre, hecho para ser el protagonista de su historia.',
        'Sencillo, luminoso y eterno: el anillo que nunca pasa de moda.',
        'Pura elegancia: deja que la piedra hable por sí sola.']),
]
out = {}
for ref, d in D.items():
    for pat, pool in POOLS:
        if re.search(pat, d.lower()):
            k = int(hashlib.md5(ref.encode()).hexdigest(), 16) % len(pool)
            out[ref] = d + ' ' + pool[k]; break
json.dump(out, open('descripciones.json', 'w'), ensure_ascii=False)
for r in list(out)[:8]: print(r, out[r])
print(len(out), max(len(v) for v in out.values()))
