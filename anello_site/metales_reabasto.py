# odoo shell < metales_reabasto.py — 3-oct: «Oro suelto por gramo» sin serie y sin ruta «sobre pedido» (se le pegaba también al 24K).
#  Reabastecimiento por kilataje: las aleaciones (oro 10/14/18K amarillo/blanco/bitono y plata .925) se FUNDEN solas cuando una
#  orden las pide y no hay (regla mín 0 / máx 0, automática, ruta Fabricar); el metal fino (oro 24K, plata fina, platino) se COMPRA.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
cia = env['res.company'].browse(3)
T = env['product.template'].with_context(active_test=False); PAV = env['product.attribute.value']
OP = env['stock.warehouse.orderpoint'].with_company(cia)
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1)
mto = env.ref('stock.route_warehouse0_mto'); fab = wh.manufacture_pull_id.route_id
buy = env.ref('purchase_stock.route_warehouse0_buy', raise_if_not_found=False)
oro = T.browse(2965)
oro.write({'tracking': 'none', 'route_ids': [(3, mto.id), (4, fab.id)]})
plata = T.search([('name', '=', 'Plata .925 (g)')], limit=1)
plata.write({'route_ids': [(3, mto.id), (4, fab.id)]})
aleaciones = env['product.product']
for vid in (116, 117, 110, 113, 114, 115, 201, 202, 203, 136):
    aleaciones |= PAV.browse(vid).xb_aleacion_id
finos = T.search([('name', 'in', ['Plata fina .999 (g)', 'Platino .999 (g)'])]).product_variant_id
finos |= oro.product_variant_ids.filtered(lambda p: p.product_template_attribute_value_ids.product_attribute_value_id.ids == [1])
if buy:
    (finos.product_tmpl_id).write({'route_ids': [(4, buy.id)]})
def regla(p, ruta):
    o = OP.search([('product_id', '=', p.id), ('warehouse_id', '=', wh.id)], limit=1)
    v = {'product_id': p.id, 'warehouse_id': wh.id, 'location_id': wh.lot_stock_id.id, 'product_min_qty': 0.0,
         'product_max_qty': 0.0, 'trigger': 'auto', 'company_id': cia.id}
    if ruta:
        v['route_id'] = ruta.id
    o.write(v) if o else OP.create(v)
for p in aleaciones:
    regla(p, fab)
for p in finos:
    regla(p, buy)
print('reglas', [(o.product_id.display_name, o.route_id.name, o.trigger) for o in OP.search([('product_id', 'in', (aleaciones | finos).ids)])])
print('oro suelto: serie', oro.tracking, '| rutas', oro.route_ids.mapped('name'))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
