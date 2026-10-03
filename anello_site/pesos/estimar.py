import json, math
# ref: (w ancho medio mm, t grueso mm, k perfil, cabeza mm3, extra mm3, confianza, nota)
E = {
'373203':(2.4,1.3,1.0,28,15,'media','6 garras, banda grabada de ~2.4 mm'),
'373204':(2.2,1.1,1.0,30,20,'media','catedral con grabado, banda ~2.2 mm'),
'373206':(3.0,1.3,0.95,22,25,'baja','hombros escalonados anchos que se afinan'),
'373207':(3.0,1.3,0.9,22,20,'baja','una sola foto; banda acanalada catedral'),
'373208':(3.0,1.2,0.9,35,0,'media','hombros anchos, canasta bitono'),
'373209':(2.6,1.1,0.9,45,20,'media','semibisel envolvente'),
'373210':(3.2,1.2,1.0,35,20,'media','hombros anchos acanalados, galería en S'),
'373211':(2.3,1.16,0.9,40,0,'media','cabeza con lazo bitono'),
'373212':(3.5,1.2,0.9,40,0,'media','hombros muy anchos que se afinan'),
'373214':(2.3,1.45,0.6,28,0,'alta','aro en filo (perfil triangular)'),
'373215':(3.0,1.28,1.0,20,0,'alta','banda plana de 3 mm con perlado'),
'373216':(2.8,1.35,0.95,20,10,'media','banda grabada ondulada'),
'373217':(3.0,1.4,0.75,20,30,'baja','espirales caladas'),
'373218':(4.0,1.1,1.0,30,20,'media','banda plana ancha con 2 biseles'),
'373219':(2.6,1.0,1.0,28,15,'media','banda grabada, catedral ligera'),
'373220':(1.9,1.25,0.85,20,0,'alta','aro fino redondeado'),
'373221':(2.6,1.1,0.9,25,20,'media','princesa catedral'),
'373222':(2.4,1.1,0.9,22,20,'media','catedral'),
'373223':(3.2,1.3,0.95,30,15,'baja','hombros estriados anchos, cabeza bitono'),
'373224':(5.0,1.7,1.0,40,20,'baja','banda ancha con canal de princesas y barras'),
'373225':(3.2,1.2,1.0,25,20,'media','princesa con baguettes'),
'373226':(1.8,1.2,0.85,20,15,'media','pavé fino'),
'373227':(2.0,1.2,0.85,20,20,'media','pavé marcado'),
'373228':(3.2,1.3,0.8,20,20,'baja','dos aros trenzados con pavé'),
'373229':(2.8,1.4,1.0,30,35,'media','catedral con canal'),
'373230':(2.6,1.4,0.95,22,20,'media','piedras graduadas en garra compartida'),
'373231':(2.8,1.4,1.0,22,25,'media','princesas en barras'),
'373232':(2.2,1.33,0.95,28,20,'alta','6 acentos en garra compartida'),
'373233':(3.6,1.3,1.0,35,45,'media','galería calada y canal'),
'373234':(4.0,1.3,1.0,30,20,'media','doble hilera en canal, banda ancha'),
'373235':(3.6,1.2,0.9,25,20,'media','princesa, banda ancha que se afina'),
'373236':(2.8,1.4,0.9,28,20,'media','catedral'),
'373239':(4.0,1.5,1.0,28,25,'baja','doble canal de princesas'),
'373240':(4.5,1.5,1.0,28,20,'baja','banda doble bitono con pavé'),
'373241':(3.8,1.3,1.0,30,35,'media','princesas y filigrana'),
'373242':(2.6,1.2,0.95,50,15,'media','tres piedras con pavé'),
'373243':(4.0,1.2,0.75,28,15,'media','banda abombada ancha'),
'373245':(2.8,1.3,0.9,28,20,'media','catedral clásico'),
'373246':(3.5,1.5,1.0,30,60,'baja','catedral con 3 hileras de pavé'),
'373247':(3.5,1.5,1.0,30,40,'baja','doble pavé y galería'),
'373248':(4.0,1.4,1.0,30,45,'media','catedral con baguettes y pavé'),
'373249':(3.5,1.3,1.0,30,45,'media','catedral con baguettes'),
'373250':(2.6,1.3,0.95,28,25,'media','piedras graduadas en el aro'),
'373251':(4.0,2.2,0.9,10,20,'baja','tensión en espiral, banda gruesa'),
'373253':(4.0,1.8,0.95,20,0,'baja','tensión de hombros anchos'),
'373254':(3.5,2.0,1.0,15,0,'baja','engaste en barras, banda gruesa'),
'373256':(3.5,1.8,0.95,20,0,'baja','princesa en tensión bypass'),
'373257':(2.4,1.16,0.9,35,20,'media','cruzado con canasta bitono'),
'373258':(2.2,1.0,0.85,25,15,'alta','princesa de aro fino'),
'373259':(4.0,1.1,1.0,28,10,'media','banda ancha que se afina'),
'373261':(2.6,1.12,0.9,22,20,'alta','catedral 4 garras'),
'373262':(2.0,1.0,0.85,28,15,'alta','aro cónico fino'),
'373263':(5.5,1.8,1.0,20,20,'baja','tensión envolvente con canal de princesas'),
'373264':(3.8,1.6,1.0,15,0,'baja','tensión geométrica'),
'373265':(5.0,1.6,0.95,20,0,'baja','tensión de cintas cruzadas'),
'373266':(4.0,1.6,0.9,60,25,'baja','trilogía en bisel con doble pavé'),
'373267':(4.0,1.8,1.0,10,40,'baja','bypass con 2 biseles'),
'373268':(5.0,1.6,0.95,15,30,'baja','oval cruzado con pavé'),
'373269':(3.5,2.0,1.0,10,10,'baja','tensión angular con acento'),
'373270':(5.5,1.6,0.95,10,0,'baja','tensión de banda muy ancha'),
'373271':(3.0,1.21,1.0,28,70,'media','racimos en bisel y baguettes'),
'373273':(3.0,1.3,1.0,30,20,'media','pavé curvo en canal'),
'373275':(2.6,1.32,0.95,28,35,'media','filigrana y pavé'),
'373277':(3.0,1.12,1.0,28,40,'alta','baguettes en canal, catedral'),
'373278':(2.6,1.22,0.95,28,30,'alta','laterales en garra compartida'),
'373280':(2.5,1.3,0.9,30,30,'media','pavé generoso'),
'373282':(2.4,1.3,0.9,28,60,'baja','piedras en bisel alrededor'),
'373284':(2.2,1.04,0.95,28,25,'alta','laterales graduados'),
'373285':(2.8,1.31,1.0,28,40,'alta','cinco piedras'),
'373287':(3.5,1.39,1.0,30,45,'media','catedral con canal'),
'373289':(3.6,1.4,1.0,30,45,'media','canal de princesas, catedral'),
'373290':(3.5,1.38,1.0,25,20,'alta','princesa con canal de princesas'),
'373292':(3.0,1.25,1.0,28,20,'alta','canal de princesas'),
'373294':(3.6,1.34,1.0,30,25,'alta','baguettes laterales'),
'373296':(3.0,1.43,1.0,28,25,'alta','tres piedras, banda acanalada'),
'373297':(3.5,1.2,1.0,28,20,'alta','canal de pavé'),
'373299':(2.4,1.5,0.9,60,30,'media','trilogía princesa con eternidad'),
'373301':(3.0,1.1,1.0,50,15,'alta','cabeza con 4 biseles y pavé'),
'373302':(3.5,1.5,1.0,25,15,'alta','pavé clásico, banda ancha'),
'373307':(3.6,1.33,1.0,25,20,'alta','pavé en hombros anchos'),
'373309':(3.0,1.35,1.0,28,15,'media','canal de brillantes'),
'373311':(4.0,1.6,0.95,30,0,'baja','semibisel tipo tensión, banda ancha'),
'373312':(2.6,1.32,0.9,25,15,'alta','princesa 4 garras'),
'373313':(3.6,1.2,0.85,35,40,'media','banda dividida con pavé'),
'373314':(3.4,1.3,0.85,30,40,'media','banda dividida con pavé'),
'373315':(2.6,1.1,0.85,22,20,'alta','catedral de aro afilado'),
'373319':(6.0,1.8,0.95,10,0,'media','banda ancha bitono con tensión'),
'373324':(2.6,1.2,0.9,22,30,'media','hombros en voluta'),
'373327':(2.0,1.2,0.85,20,10,'media','solitario fino'),
'373331':(2.2,1.3,0.85,20,10,'media','bypass fino'),
'373333':(2.0,1.38,0.85,30,10,'alta','4 garras alto'),
'373334':(2.8,1.4,0.9,70,0,'baja','trilogía en cascada'),
'373335':(1.8,1.0,0.85,35,0,'alta','tulipa de 6 garras, aro fino'),
'373336':(2.0,1.0,0.85,30,10,'alta','corazón en garras'),
'373338':(3.0,1.27,1.0,40,0,'alta','trilogía en carril'),
'373339':(2.4,1.35,0.85,45,0,'alta','tres piedras con lazo'),
'373340':(4.0,1.5,0.8,50,0,'baja','flor calada, banda dividida'),
'373341':(2.6,1.3,0.9,45,0,'media','marquesas laterales'),
'373342':(4.5,1.55,0.75,25,0,'media','banda dividida abombada'),
'373343':(2.6,1.4,0.85,28,10,'media','aro liso'),
'373344':(2.0,1.0,0.85,25,15,'alta','princesa catedral fina'),
'373345':(2.0,1.13,0.85,22,15,'alta','aro fino catedral'),
'373346':(4.5,1.4,0.75,0,15,'media','banda abombada con puntos en bisel'),
'373347':(2.0,1.2,0.85,20,0,'alta','aro en uve'),
'373348':(2.6,1.2,0.8,30,0,'media','doble aro fino'),
'373349':(2.4,1.29,0.85,50,0,'alta','engaste cuadrado'),
'373350':(4.0,1.5,0.85,30,0,'media','bisel sobre banda ancha'),
'373351':(2.0,1.15,0.85,22,15,'alta','catedral fino'),
'373352':(2.2,1.0,0.85,20,10,'alta','aro partido fino'),
'373353':(2.4,1.2,0.85,30,0,'media','bypass con semibisel'),
'373354':(2.0,1.2,0.85,20,5,'media','ondulado'),
'373356':(2.4,1.2,0.85,45,0,'alta','corona calada'),
'373357':(2.4,1.3,0.9,25,0,'alta','barras sobre aro fino'),
'373358':(2.0,1.0,0.85,28,0,'alta','6 garras clásico'),
'373359':(4.0,1.67,0.85,60,0,'media','racimo de cinco, banda dividida'),
'373360':(7.0,1.6,0.9,0,30,'baja','banda muy ancha con baguettes'),
'373361':(2.6,1.1,0.9,40,0,'alta','cinco piedras en barras'),
'373362':(4.0,1.27,0.95,15,0,'media','banda ancha con barras'),
'373363':(1.8,1.08,0.85,40,0,'alta','bisel en aro fino'),
'373364':(5.0,1.4,1.0,20,25,'baja','princesa en tensión con canal'),
'373365':(3.5,2.2,0.8,10,0,'media','tensión, banda redonda gruesa'),
'373366':(4.5,1.8,1.0,10,0,'baja','tensión de doble aro'),
'373367':(4.0,1.8,0.95,10,20,'baja','tensión con pavé'),
'373368':(3.0,2.3,0.8,10,0,'media','tensión asimétrica, banda redonda'),
'373370':(2.2,1.3,0.7,35,0,'alta','6 garras alto, aro en filo'),
'373371':(3.0,1.4,1.0,25,35,'media','doble hilera de pavé'),
'373372':(3.4,1.3,0.85,25,40,'media','banda dividida con pavé'),
'373373':(3.0,1.4,0.75,0,5,'alta','banda fina abombada con puntos'),
'373721':(4.2,1.7,0.95,0,20,'media','tensión, banda ancha'),
}
D = 14.86; DENS = 13.1
def bruto(r):
    w,t,k,c,x,_,_ = E[r]
    return (math.pi*(D+t)*w*t*k + c + x) * DENS / 1000
CAD = {'373254': 2.70, '373280': 2.58, '373290': 2.89}
mods = {m['ref']: m for m in json.load(open('modelos.json'))}
for r,v in CAD.items(): print('CAD', r, mods[r]['nombre'][:30], 'mío %.2f' % bruto(r), 'CAD', v, 'Odoo', mods[r]['peso'])

def calibrado(r):
    w,t,k,c,x,_,_ = E[r]
    t = min(t, 1.7)
    f = 0.92 if w <= 2.6 else (0.71 if w >= 3.5 else 0.92 - (w-2.6)/(0.9)*0.21)
    if w > 3.5: f = 0.65
    return (math.pi*(D+t)*w*t*k*f + c + x) * DENS / 1000
for r,v in CAD.items(): print('CAL', r, '%.2f' % calibrado(r), 'CAD', v)
out = []
for r, m in mods.items():
    odoo = float(m['peso']) if m['peso'] and '/' not in m['peso'] else None
    v19 = float(m['viejo_peso']) if m['viejo_peso'] else None
    if r in CAD:
        est, prop, conf, nota = CAD[r], CAD[r], 'exacta', 'peso calculado del archivo 3D (solo metal)'
        accion = 'cambiar' if abs(prop-odoo)/odoo > 0.05 else 'igual'
    elif r in E:
        est = round(max(calibrado(r), 1.8), 2); conf, nota = ('media' if m['frente'] else 'baja'), E[r][6]
        dif = (est - odoo) / odoo
        if abs(dif) <= 0.25:
            prop, accion = odoo, 'igual'
        else:
            prop, accion = round(est, 1), 'cambiar'
    else:
        est, prop, conf, nota, accion = None, odoo, 'sin fotos', 'sin fotos para revisar; se deja igual', 'igual'
    out.append({'ref': r, 'nombre': m['nombre'] or ('Modelo ' + r), 'ids': m['ids'], 'odoo': odoo, 'v2019': v19,
                'estimado': est, 'propuesta': prop, 'confianza': conf, 'nota': nota, 'accion': accion, 'medido': bool(m['frente'])})
json.dump(out, open('propuesta.json', 'w'), ensure_ascii=False)
from collections import Counter
print(Counter(o['accion'] for o in out), Counter(o['confianza'] for o in out if o['accion']=='cambiar'))
for o in sorted(out, key=lambda o: -abs((o['propuesta'] or 0)-(o['odoo'] or 0))):
    if o['accion']=='cambiar': print(o['ref'], o['nombre'][:38].ljust(38), o['odoo'], '→', o['propuesta'], '| 2019', o['v2019'], '|', o['confianza'])
