# odoo shell < pieza_medida.py — 5-oct: «Pieza a la medida por gramo» reemplaza las 9 hechuras de metal (SERV ORO/PLATA/PLATINO … Y MANO DE OBRA).
#  · por gramo (UdM g), opción Metal = cualquier aleación; precio = metal a su precio de venta + mano de obra × 2.28; IVA 16 %.
#  · mano de obra (costo por gramo, opción A = la del catálogo): amarillo/rosa/florentino/24K $270, blanco/bitono $345,
#    platino $460, plata $120.
#  · receta por variante: 1000 g de pieza = 1000 g de su aleación → la orden de fabricación descuenta el metal.
#  · servicios de solo mano de obra y extraurgente: + IVA. Las 9 hechuras de metal se ARCHIVAN.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
cia = env['res.company'].browse(3)
T = env['product.template'].with_context(active_test=False); PAV = env['product.attribute.value']
PTAV = env['product.template.attribute.value']; Bom = env['mrp.bom']; Item = env['product.pricelist.item']
g = env.ref('uom.product_uom_gram'); iva = env['account.tax'].browse(12)
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1); fab = wh.manufacture_pull_id.route_id
mto = env.ref('stock.route_warehouse0_mto')
viejo = T.browse(4038)   # SERV ORO 14K… (para copiar categoría de caja)
valores = PAV.search([('attribute_id', '=', 9), ('active', '=', True), ('xb_aleacion_id', '!=', False)])
vals = {'name': 'Pieza a la medida por gramo', 'type': 'consu', 'is_storable': False, 'uom_id': g.id, 'sale_ok': True,
        'purchase_ok': False, 'available_in_pos': True, 'xb_por_gramo': True, 'company_id': False,
        'categ_id': viejo.categ_id.id, 'taxes_id': [(6, 0, iva.ids)], 'route_ids': [(6, 0, [mto.id, fab.id])],
        'description_sale': 'Pieza elaborada a la medida en el taller de Anello. Precio por gramo del metal elegido, mano de obra incluida.'}
if 'uom_po_id' in T._fields:
    vals['uom_po_id'] = g.id
if 'pos_categ_ids' in T._fields:
    vals['pos_categ_ids'] = [(6, 0, viejo.pos_categ_ids.ids)]
t = T.search([('name', '=', 'Pieza a la medida por gramo')], limit=1)
if t:
    t.write(vals); t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9).write({'value_ids': [(6, 0, valores.ids)]})
else:
    t = T.create(dict(vals, attribute_line_ids=[(0, 0, {'attribute_id': 9, 'value_ids': [(6, 0, valores.ids)]})]))
for lg in ('es_MX', 'en_US'):
    t.with_context(lang=lg).name = 'Pieza a la medida por gramo'
def mano(v):
    n = v.name.lower()
    if 'platino' in n: return 460.0
    if 'plata' in n: return 120.0
    if 'blanco' in n or 'bitono' in n: return 345.0
    return 270.0
bom = Bom.search([('product_tmpl_id', '=', t.id), ('product_id', '=', False)], limit=1)
lineas = []
for v in valores:
    p = t._create_product_variant(PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', '=', v.id)], limit=1))
    p.with_company(cia).standard_price = mano(v)
    ptav = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', '=', v.id)], limit=1)
    lineas.append((0, 0, {'product_id': v.xb_aleacion_id.id, 'product_qty': 1000.0, 'product_uom_id': g.id,
                          'bom_product_template_attribute_value_ids': [(6, 0, ptav.ids)]}))
bvals = {'product_tmpl_id': t.id, 'product_qty': 1000.0, 'product_uom_id': g.id, 'type': 'normal', 'company_id': cia.id,
         'bom_line_ids': [(5, 0, 0)] + lineas}
bom.write(bvals) if bom else Bom.create(bvals)
for pl in env['product.pricelist'].browse([2, 7]):
    Item.search([('pricelist_id', '=', pl.id), ('product_tmpl_id', '=', t.id)]).unlink()
    Item.create({'pricelist_id': pl.id, 'applied_on': '1_product', 'product_tmpl_id': t.id, 'compute_price': 'formula',
                 'base': 'standard_price', 'price_markup': 128.0})
serv = T.browse([4022, 3025, 3026, 3027])
serv.write({'taxes_id': [(6, 0, iva.ids)]})
viejos = T.browse([4052, 4046, 4038, 4040, 4051, 4041, 4087, 4047, 4053])
viejos.write({'active': False})
print('pieza', t.id, '| variantes', len(t.product_variant_ids), '| servicios con IVA', serv.mapped('name'))
print('archivadas', viejos.mapped('name'))
e = env(context=dict(env.context, allowed_company_ids=[3]))
plr = e['product.pricelist'].browse(2)
for p in e['product.template'].browse(t.id).product_variant_ids.sorted('display_name'):
    if any(k in p.display_name for k in ('10kt', '14kt', '14Kt', '18kt', '925', 'Platino')):
        print('  %-55s mano $%3.0f → precio $%7.2f/g + IVA = $%7.2f' % (p.display_name, p.with_company(cia).standard_price, plr._get_product_price(p, 1.0), plr._get_product_price(p, 1.0) * 1.16))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
