# odoo shell < fabricacion_pedido.py — 3-oct: vender un anillo crea su ORDEN DE FABRICACIÓN (si no hay pieza en existencia).
#  · activa «Rutas de varios pasos» (para poder usar rutas por producto)
#  · reactiva «Reabastecer sobre pedido (MTO)» y la regla del almacén Anello PFC en modo «de existencias, si no, sobre pedido»
#  · reactiva «Anello: Fabricación (1 paso)»
#  · pone esas dos rutas en todos los anillos cotizados por metal
#  · XB_PRUEBA=1: crea una venta de prueba (Matera o el primer anillo con diamante LAB) y muestra la orden; luego deshace.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
PRUEBA = os.environ.get('XB_PRUEBA', '0') == '1'
cia = env['res.company'].browse(3)
s = env['res.config.settings'].with_company(cia).create({})
if not s.group_stock_adv_location:
    s.group_stock_adv_location = True
    s.execute()
Route = env['stock.route'].with_context(active_test=False)
mto = env.ref('stock.route_warehouse0_mto')
mto.active = True
wh = env['stock.warehouse'].search([('company_id', '=', 3)], limit=1)
fab = wh.manufacture_pull_id.route_id
fab.active = True
if not wh.manufacture_to_resupply:
    wh.manufacture_to_resupply = True
reglas = mto.rule_ids.filtered(lambda r: r.company_id == cia or r.warehouse_id == wh)
reglas.write({'procure_method': 'mts_else_mto'})
print('almacén', wh.name, '| ruta fab', fab.name, fab.active, '| reglas MTO', [(r.name, r.procure_method) for r in reglas])
T = env['product.template']
anillos = T.search([('xb_precio_por_metal', '=', True), ('active', '=', True), ('company_id', 'in', [3, False])])
anillos.write({'route_ids': [(4, mto.id), (4, fab.id)]})
print('anillos con rutas', len(anillos))
if PRUEBA:
    PTAV = env['product.template.attribute.value']
    t = T.search([('xb_ref_modelo', '=', '373721'), ('active', '=', True)], limit=1) or anillos.filtered(lambda a: a.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 38))[:1]
    lab = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id.name', '=', 'Diamante de laboratorio 1.00 ct')], limit=1)
    comb = lab
    for line in t.attribute_line_ids.filtered(lambda l: l.attribute_id.id != 38):
        comb |= line.product_template_value_ids[:1]
    var = t._create_product_variant(comb)
    cli = env['res.partner'].search([('company_id', 'in', [3, False]), ('customer_rank', '>', 0)], limit=1)
    so = env['sale.order'].with_company(cia).create({'partner_id': cli.id, 'company_id': 3, 'warehouse_id': wh.id,
        'order_line': [(0, 0, {'product_id': var.id, 'product_uom_qty': 1})]})
    so.action_confirm()
    mos = env['mrp.production'].search([('origin', '=', so.name)])
    print('VENTA', so.name, var.display_name, '| entregas', so.picking_ids.mapped('name'))
    for mo in mos:
        print('  ORDEN', mo.name, mo.state, mo.product_id.display_name, '| seguimiento anillo', mo.product_id.tracking)
        for mv in mo.move_raw_ids:
            print('     componente', mv.product_id.name, mv.product_uom_qty, '| serie al terminar:', mv.product_id.tracking)
        print('     operaciones', [(w.name, w.workcenter_id.name) for w in mo.workorder_ids])
    if not mos:
        print('  ⚠️ no se creó orden de fabricación')
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
# la serie del diamante (y del anillo) se escribe al fabricar, sin tenerla de antemano
if not SECO or PRUEBA:
    pt = wh.manu_type_id
    pt.write({'use_create_components_lots': True, 'use_create_lots': True, 'use_existing_lots': True})
    print('operación', pt.name, '| crear series de componentes', pt.use_create_components_lots)
    if not SECO:
        env.cr.commit()
