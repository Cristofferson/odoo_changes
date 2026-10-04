# odoo shell < metales_unificar.py — 3-oct (aprobado por el usuario):
#  · costos de ligas: amarilla $16/g, blanca $8/g, plata $5/g (referencia: Legor / Otto Frei, USD 18.32)
#  · el oro del taller ES «Oro suelto por gramo» (2965): unidad → gramo; sus variantes 10/14/18K amarillo/blanco,
#    bitono 10/14/18K (se agrega) y 24K = oro fino. Cada aleación lleva su LdM por variante (ley × 24K + liga).
#  · se archivan los productos de oro duplicados creados hoy («Oro fino 24K (g)», «Oro amarillo 14K (g)»…).
#  · plata y platino (no existían) se quedan como se crearon.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
cia = env['res.company'].browse(3)
T = env['product.template'].with_context(active_test=False); PAV = env['product.attribute.value']
PTAV = env['product.template.attribute.value']; Bom = env['mrp.bom']
g = env.ref('uom.product_uom_gram')
for n, c in (('Liga para oro amarillo (g)', 16.0), ('Liga para oro blanco (g)', 8.0), ('Liga para plata (g)', 5.0)):
    t = T.search([('name', '=', n)], limit=1); t.with_company(cia).standard_price = c
liga = {k: T.search([('name', '=', 'Liga para oro %s (g)' % k)], limit=1).product_variant_id for k in ('amarillo', 'blanco')}
oro = T.browse(2965)
vals = {'uom_id': g.id, 'is_storable': True, 'purchase_ok': True}
if 'uom_po_id' in oro._fields:
    vals['uom_po_id'] = g.id
oro.write(vals)
mto = env.ref('stock.route_warehouse0_mto')
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1)
oro.write({'route_ids': [(4, mto.id), (4, wh.manufacture_pull_id.route_id.id)]})
line = oro.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9)
line.write({'value_ids': [(4, v) for v in (201, 202, 203)]})
def var(vid):
    ptav = PTAV.search([('product_tmpl_id', '=', oro.id), ('product_attribute_value_id', '=', vid)], limit=1)
    return oro._create_product_variant(ptav)
fino = var(1)          # Oro Puro (24Kt)
xau = env['res.currency'].with_context(active_test=False).search([('name', '=', 'XAU')], limit=1)
fino.with_company(cia).standard_price = round(1 / xau.rate, 2)
LEY = {'10K': 0.417, '14K': 0.585, '18K': 0.75}
V = {('amarillo', '10K'): 116, ('amarillo', '14K'): 117, ('amarillo', '18K'): 110,
     ('blanco', '10K'): 113, ('blanco', '14K'): 114, ('blanco', '18K'): 115,
     ('bitono', '10K'): 201, ('bitono', '14K'): 202, ('bitono', '18K'): 203}
def receta(p, lineas):
    b = Bom.search([('product_id', '=', p.id)], limit=1)
    v = {'product_tmpl_id': oro.id, 'product_id': p.id, 'product_qty': 1.0, 'product_uom_id': g.id, 'type': 'normal',
         'company_id': cia.id, 'bom_line_ids': [(5, 0, 0)] + [(0, 0, {'product_id': c.id, 'product_qty': q, 'product_uom_id': g.id}) for c, q in lineas]}
    b.write(v) if b else Bom.create(v)
    p.with_company(cia).standard_price = round(sum(q * c.with_company(cia).standard_price for c, q in lineas), 2)
A = {}
for color in ('amarillo', 'blanco'):
    for kt, ley in LEY.items():
        p = var(V[(color, kt)]); A[(color, kt)] = p
        receta(p, [(fino, ley), (liga[color], round(1 - ley, 3))])
for kt in LEY:
    p = var(V[('bitono', kt)]); A[('bitono', kt)] = p
    receta(p, [(A[('amarillo', kt)], 0.5), (A[('blanco', kt)], 0.5)])
for k, vid in V.items():
    PAV.browse(vid).xb_aleacion_id = A[k]
# plata .925 con el costo nuevo de su liga
plata = T.search([('name', '=', 'Plata .925 (g)')], limit=1).product_variant_id
b = Bom.search([('product_id', '=', plata.id)], limit=1) or Bom.search([('product_tmpl_id', '=', plata.product_tmpl_id.id)], limit=1)
plata.with_company(cia).standard_price = round(sum(l.product_qty * l.product_id.with_company(cia).standard_price for l in b.bom_line_ids), 2)
# duplicados de hoy → archivados (con su LdM)
dup = T.search([('name', 'in', ['Oro fino 24K (g)'] + ['Oro %s %s (g)' % (c, k) for c in ('amarillo', 'blanco', 'bitono') for k in LEY])])
Bom.search([('product_tmpl_id', 'in', dup.ids)]).write({'active': False})
dup.write({'active': False})
print('archivados', dup.mapped('name'))
for vid in list(V.values()) + [136, 118]:
    v = PAV.browse(vid)
    print('  %-20s → %-45s $%.2f/g' % (v.name, v.xb_aleacion_id.display_name, v.xb_aleacion_id.with_company(cia).standard_price))
print('ligas', [(l.name, l.with_company(cia).standard_price) for l in T.search([('name', 'like', 'Liga para')])])
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
