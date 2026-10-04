# odoo shell < plata_platino_suelto.py — 4-oct: plata y platino igual que el oro: UN producto por metal, que se vende en caja
#  y del que el taller descuenta. «Plata suelta por gramo» (pura 999, 950, 925) y «Platino suelto por gramo» (999).
#  Las aleaciones (950, 925) llevan LdM por variante (ley × plata pura + liga) y se funden solas; la pura y el platino se compran.
#  Se archivan «Plata fina .999 (g)», «Plata .925 (g)» y «Platino .999 (g)» creados el 3-oct. XB_SECO=1 ensaya.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
cia = env['res.company'].browse(3)
T = env['product.template'].with_context(active_test=False); PAV = env['product.attribute.value'].with_context(active_test=False)
PTAV = env['product.template.attribute.value']; Bom = env['mrp.bom'].with_context(active_test=False)
OP = env['stock.warehouse.orderpoint'].with_company(cia).with_context(active_test=False)
g = env.ref('uom.product_uom_gram')
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1); fab = wh.manufacture_pull_id.route_id
buy = env.ref('purchase_stock.route_warehouse0_buy')
oro = T.browse(2965)
PAV.browse([228, 229]).write({'active': True})          # plata pura 999 y 950 (se habían archivado por no usarse)
def suelto(nombre, valores):
    t = T.search([('name', '=', nombre)], limit=1)
    vals = {'name': nombre, 'type': 'consu', 'is_storable': True, 'tracking': 'none', 'uom_id': g.id, 'sale_ok': True,
            'purchase_ok': True, 'available_in_pos': True, 'categ_id': oro.categ_id.id, 'company_id': False,
            'taxes_id': [(6, 0, oro.taxes_id.ids)], 'route_ids': [(6, 0, [fab.id, buy.id])]}
    if 'uom_po_id' in T._fields:
        vals['uom_po_id'] = g.id
    if 'pos_categ_ids' in T._fields:
        vals['pos_categ_ids'] = [(6, 0, oro.pos_categ_ids.ids)]
    if not t:
        t = T.create(dict(vals, attribute_line_ids=[(0, 0, {'attribute_id': 9, 'value_ids': [(6, 0, valores)]})]))
    else:
        t.write(vals)
    return t
def var(t, vid):
    return t._create_product_variant(PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', '=', vid)], limit=1))
def regla(p, ruta):
    o = OP.search([('product_id', '=', p.id), ('warehouse_id', '=', wh.id)], limit=1)
    v = {'product_id': p.id, 'warehouse_id': wh.id, 'location_id': wh.lot_stock_id.id, 'product_min_qty': 0, 'product_max_qty': 0,
         'trigger': 'auto', 'route_id': ruta.id, 'company_id': cia.id, 'active': True}
    o.write(v) if o else OP.create(v)
def tasa(c):
    cur = env['res.currency'].with_context(active_test=False).search([('name', '=', c)], limit=1)
    return round(1 / cur.rate, 2)
liga_plata = T.search([('name', '=', 'Liga para plata (g)')], limit=1).product_variant_id
plata = suelto('Plata suelta por gramo', [228, 229, 136])
pura = var(plata, 228); pura.with_company(cia).standard_price = tasa('XAG'); regla(pura, buy)
for vid in (229, 136):
    p = var(plata, vid); ley = PAV.browse(vid).x_ley
    b = Bom.search([('product_id', '=', p.id)], limit=1)
    # por 1000 g: las cantidades se guardan con 2 decimales y 0.925 g quedaba en 0.93 (≈1 % de más)
    bv = {'product_tmpl_id': plata.id, 'product_id': p.id, 'product_qty': 1000.0, 'product_uom_id': g.id, 'type': 'normal', 'company_id': cia.id,
          'bom_line_ids': [(5, 0, 0), (0, 0, {'product_id': pura.id, 'product_qty': round(ley * 1000, 2), 'product_uom_id': g.id}),
                           (0, 0, {'product_id': liga_plata.id, 'product_qty': round((1 - ley) * 1000, 2), 'product_uom_id': g.id})]}
    b.write(bv) if b else Bom.create(bv)
    p.with_company(cia).standard_price = round(ley * pura.with_company(cia).standard_price + (1 - ley) * liga_plata.with_company(cia).standard_price, 2)
    regla(p, fab)
    PAV.browse(vid).xb_aleacion_id = p
PAV.browse(228).xb_aleacion_id = pura
platino = suelto('Platino suelto por gramo', [118])
pt = var(platino, 118); pt.with_company(cia).standard_price = tasa('XPT'); regla(pt, buy)
PAV.browse(118).xb_aleacion_id = pt
viejos = T.search([('name', 'in', ['Plata fina .999 (g)', 'Plata .925 (g)', 'Platino .999 (g)'])])
Bom.search([('product_tmpl_id', 'in', viejos.ids)]).write({'active': False})
OP.search([('product_id', 'in', viejos.product_variant_ids.ids)]).write({'active': False})
viejos.write({'active': False})
print('archivados', viejos.mapped('name'))
for vid in (228, 229, 136, 118):
    v = PAV.browse(vid); a = v.xb_aleacion_id
    print('  %-20s → %-48s $%.2f/g | LdM %s' % (v.name, a.display_name, a.with_company(cia).standard_price,
          [(l.product_id.display_name, l.product_qty) for l in Bom.search([('product_id', '=', a.id)], limit=1).bom_line_ids]))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
