# odoo shell < metales.py — 3-oct: metal fino, ligas y ALEACIONES (en gramos) para que la orden de fabricación descuente metal.
#  Aleación = producto intermedio con su lista de materiales (por 1 g): ley × metal fino + (1 − ley) × liga.
#  Bitono = ½ g de aleación amarilla + ½ g de blanca del mismo kilataje. Platino 999 se consume como fino.
#  Las aleaciones se pueden tener en existencia o fabricar sobre pedido (rutas MTO + Fabricar).
#  Cada valor de Metal queda ligado a su aleación (campo «Aleación que se consume»). Idempotente. XB_SECO=1 ensaya.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
cia = env['res.company'].browse(3)
T = env['product.template'].with_company(cia); PAV = env['product.attribute.value']
g = env.ref('uom.product_uom_gram')
def tasa(c):
    cur = env['res.currency'].with_context(active_test=False).search([('name', '=', c)], limit=1)
    return round(1 / cur.rate, 2) if cur.rate else 0.0
def prod(nombre, costo, desc, compra=True):
    t = T.search([('name', '=', nombre)], limit=1)
    vals = {'type': 'consu', 'is_storable': True, 'uom_id': g.id, 'sale_ok': False, 'purchase_ok': compra,
            'company_id': cia.id, 'description': desc}
    if 'uom_po_id' in T._fields:
        vals['uom_po_id'] = g.id
    if not t:
        t = T.create(dict(vals, name=nombre))
    else:
        t.write(vals)
    if costo is not None:
        t.with_company(cia).standard_price = costo
    return t.product_variant_id
fino = {'Oro': prod('Oro fino 24K (g)', tasa('XAU'), 'Oro puro .999, en gramos.'),
        'Plata': prod('Plata fina .999 (g)', tasa('XAG'), 'Plata pura .999, en gramos.'),
        'Platino': prod('Platino .999 (g)', tasa('XPT'), 'Platino puro .999, en gramos.')}
liga = {'amarillo': prod('Liga para oro amarillo (g)', None, 'Metales de aleación (plata/cobre) para oro amarillo.'),
        'blanco': prod('Liga para oro blanco (g)', None, 'Metales de aleación (paladio/níquel) para oro blanco.'),
        'plata': prod('Liga para plata (g)', None, 'Cobre para plata .925.')}
mto = env.ref('stock.route_warehouse0_mto')
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1)
fab = wh.manufacture_pull_id.route_id
Bom = env['mrp.bom']
def aleacion(nombre, lineas, desc):
    """lineas = [(producto, gramos por gramo de aleación)]"""
    p = prod(nombre, None, desc, compra=True)
    p.product_tmpl_id.write({'route_ids': [(4, mto.id), (4, fab.id)]})
    costo = sum(q * c.with_company(cia).standard_price for c, q in lineas)
    p.with_company(cia).standard_price = round(costo, 2)
    b = Bom.search([('product_tmpl_id', '=', p.product_tmpl_id.id)], limit=1)
    vals = {'product_tmpl_id': p.product_tmpl_id.id, 'product_qty': 1.0, 'product_uom_id': g.id, 'type': 'normal',
            'company_id': cia.id, 'bom_line_ids': [(5, 0, 0)] + [(0, 0, {'product_id': c.id, 'product_qty': q, 'product_uom_id': g.id}) for c, q in lineas]}
    b.write(vals) if b else Bom.create(vals)
    return p
A = {}
for color in ('amarillo', 'blanco'):
    for kt, ley in (('10K', 0.417), ('14K', 0.585), ('18K', 0.75)):
        A[(color, kt)] = aleacion('Oro %s %s (g)' % (color, kt), [(fino['Oro'], ley), (liga[color], round(1 - ley, 3))],
                                  'Aleación de oro %s %s: %.1f %% oro fino.' % (color, kt, ley * 100))
for kt in ('10K', '14K', '18K'):
    A[('bitono', kt)] = aleacion('Oro bitono %s (g)' % kt, [(A[('amarillo', kt)], 0.5), (A[('blanco', kt)], 0.5)],
                                 'Oro bitono %s: mitad aleación amarilla y mitad blanca.' % kt)
A[('plata', '925')] = aleacion('Plata .925 (g)', [(fino['Plata'], 0.925), (liga['plata'], 0.075)], 'Plata ley .925.')
MAPA = {116: ('amarillo', '10K'), 117: ('amarillo', '14K'), 110: ('amarillo', '18K'),
        113: ('blanco', '10K'), 114: ('blanco', '14K'), 115: ('blanco', '18K'),
        201: ('bitono', '10K'), 202: ('bitono', '14K'), 203: ('bitono', '18K'), 136: ('plata', '925')}
for vid, k in MAPA.items():
    PAV.browse(vid).xb_aleacion_id = A[k]
PAV.browse(118).xb_aleacion_id = fino['Platino']
for v in PAV.browse(list(MAPA) + [118]):
    print('  %-22s → %s ($%.2f/g)' % (v.name, v.xb_aleacion_id.name, v.xb_aleacion_id.with_company(cia).standard_price))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
