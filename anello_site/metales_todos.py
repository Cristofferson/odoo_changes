# odoo shell < metales_todos.py — 3-oct: TODAS las opciones de Metal con ley (no solo las de la web: la caja vende todas)
#  quedan ligadas a su aleación en «Oro suelto por gramo» (o plata/platino) con su LdM, costo y regla de fundido.
#  Liga por color: blanco → liga blanca; rosa → liga rosa (nueva, $16/g); amarillo/florentino/«Oro 21Kt» → liga amarilla;
#  bitono → ½ amarilla + ½ blanca del mismo kilataje. Sin ley (Oro, Plata, baños) o sin metal precioso: no se consume metal.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
cia = env['res.company'].browse(3)
T = env['product.template'].with_context(active_test=False); PAV = env['product.attribute.value']
PTAV = env['product.template.attribute.value']; Bom = env['mrp.bom']; OP = env['stock.warehouse.orderpoint'].with_company(cia)
g = env.ref('uom.product_uom_gram')
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1); fab = wh.manufacture_pull_id.route_id
oro = T.browse(2965)
def liga(nombre, costo):
    t = T.search([('name', '=', nombre)], limit=1)
    if not t:
        molde = T.search([('name', '=', 'Liga para oro amarillo (g)')], limit=1)
        t = molde.copy({'name': nombre, 'description': 'Metales de aleación para oro rosa (más cobre).'})
        t.with_company(cia).standard_price = costo
    return t.product_variant_id
L = {'amarillo': liga('Liga para oro amarillo (g)', 16), 'blanco': liga('Liga para oro blanco (g)', 8), 'rosa': liga('Liga para oro rosa (g)', 16.0)}
valores = PAV.search([('attribute_id', '=', 9), ('active', '=', True), ('x_metal', '=', 'Oro'), ('x_ley', '>', 0)])
line = oro.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9)
line.write({'value_ids': [(4, v.id) for v in valores]})
def var(v):
    return oro._create_product_variant(PTAV.search([('product_tmpl_id', '=', oro.id), ('product_attribute_value_id', '=', v.id)], limit=1))
fino = var(PAV.browse(1))
def color(v):
    n = v.name.lower()
    return 'blanco' if 'blanco' in n else 'rosa' if 'rosa' in n else 'bitono' if 'bitono' in n else 'amarillo'
def receta(p, lineas):
    b = Bom.search([('product_id', '=', p.id)], limit=1)
    vals = {'product_tmpl_id': oro.id, 'product_id': p.id, 'product_qty': 1.0, 'product_uom_id': g.id, 'type': 'normal', 'company_id': cia.id,
            'bom_line_ids': [(5, 0, 0)] + [(0, 0, {'product_id': c.id, 'product_qty': q, 'product_uom_id': g.id}) for c, q in lineas]}
    b.write(vals) if b else Bom.create(vals)
    p.with_company(cia).standard_price = round(sum(q * c.with_company(cia).standard_price for c, q in lineas), 2)
    o = OP.search([('product_id', '=', p.id), ('warehouse_id', '=', wh.id)], limit=1)
    ov = {'product_id': p.id, 'warehouse_id': wh.id, 'location_id': wh.lot_stock_id.id, 'product_min_qty': 0, 'product_max_qty': 0,
          'trigger': 'auto', 'route_id': fab.id, 'company_id': cia.id}
    o.write(ov) if o else OP.create(ov)
hechas = {}
ley = {}
# primero las que no son bitono (el bitono se arma con ellas)
for v in valores.sorted(lambda x: color(x) == 'bitono'):
    if v.id == 1:
        v.xb_aleacion_id = fino; continue
    p = var(v); c = color(v)
    if c == 'bitono':
        # ½ amarilla + ½ blanca del kilataje más cercano (el bitono trae ley 0.418 vs 0.417)
        a = min((x for k, x in hechas.items() if k[0] == 'amarillo'), key=lambda x: abs(ley[x.id] - v.x_ley))
        b = min((x for k, x in hechas.items() if k[0] == 'blanco'), key=lambda x: abs(ley[x.id] - v.x_ley))
        receta(p, [(a, 0.5), (b, 0.5)])
    else:
        receta(p, [(fino, v.x_ley), (L[c], round(1 - v.x_ley, 3))])
        ley[p.id] = v.x_ley
        hechas[(c, v.x_ley, v.id)] = p
    v.xb_aleacion_id = p
# plata con ley y platino
plata925 = T.search([('name', '=', 'Plata .925 (g)')], limit=1).product_variant_id
for v in PAV.search([('attribute_id', '=', 9), ('active', '=', True), ('x_metal', '=', 'Plata'), ('x_ley', '>', 0)]):
    v.xb_aleacion_id = plata925
PAV.browse(118).xb_aleacion_id = T.search([('name', '=', 'Platino .999 (g)')], limit=1).product_variant_id
for v in PAV.search([('attribute_id', '=', 9), ('active', '=', True)], order='x_metal, name'):
    a = v.xb_aleacion_id
    print('  %-22s ley %-5s → %s' % (v.name, v.x_ley, ('%s ($%.2f/g)' % (a.display_name, a.with_company(cia).standard_price)) if a else '— sin consumo de metal'))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
