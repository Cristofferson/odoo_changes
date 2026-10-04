# odoo shell < metal_suelto_precio.py — 4-oct: oro/plata/platino suelto por gramo se venden a COSTO + 8 % (aprobado).
#  · reglas de «Anello (Retail)» y «PreCompra»: fórmula sobre costo +8 % (antes «precio fijo $0» en el oro)
#  · tarea diaria (después de que Odoo baja XAU/XAG/XPT): costo de los finos = precio del día; aleaciones = su receta.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
T = env['product.template'].with_context(active_test=False); Item = env['product.pricelist.item']
metales = T.search([('name', 'in', ['Oro suelto por gramo', 'Plata suelta por gramo', 'Platino suelto por gramo'])])
for pl in env['product.pricelist'].browse([2, 7]):
    for t in metales:
        Item.search([('pricelist_id', '=', pl.id), ('product_tmpl_id', '=', t.id)]).unlink()
        Item.create({'pricelist_id': pl.id, 'applied_on': '1_product', 'product_tmpl_id': t.id, 'compute_price': 'formula',
                     'base': 'standard_price', 'price_markup': 8.0})
CODE = '''# Costo del día de los metales sueltos (finos = tipo de cambio XAU/XAG/XPT; aleaciones = su receta por 1000 g)
cia = env['res.company'].browse(3)
T = env['product.template']
def tasa(c):
    cur = env['res.currency'].with_context(active_test=False).search([('name', '=', c)], limit=1)
    return (1.0 / cur.rate) if cur and cur.rate else 0.0
FINO = {'Oro Puro (24Kt)': 'XAU', 'Plata Pura (999)': 'XAG', 'Platino Puro (999)': 'XPT'}
vars = T.search([('name', 'in', ['Oro suelto por gramo', 'Plata suelta por gramo', 'Platino suelto por gramo'])]).product_variant_ids
for p in vars:
    nombres = p.product_template_attribute_value_ids.mapped('name')
    for n, c in FINO.items():
        if n in nombres and tasa(c):
            p.with_company(cia).write({'standard_price': round(tasa(c), 2)})
Bom = env['mrp.bom']
# dos vueltas: el bitono se arma con aleaciones amarilla y blanca
for vuelta in (1, 2):
    for p in vars:
        b = Bom.search([('product_id', '=', p.id)], limit=1)
        if not b:
            continue
        costo = sum(l.product_qty * l.product_id.with_company(cia).standard_price for l in b.bom_line_ids) / (b.product_qty or 1.0)
        p.with_company(cia).write({'standard_price': round(costo, 2)})
'''
act = env['ir.actions.server'].search([('name', '=', 'Anello: costo del día de los metales sueltos')], limit=1)
vals = {'name': 'Anello: costo del día de los metales sueltos', 'model_id': env.ref('product.model_product_template').id,
        'state': 'code', 'code': CODE}
act.write(vals) if act else act.create(vals)
act = env['ir.actions.server'].search([('name', '=', 'Anello: costo del día de los metales sueltos')], limit=1)
cron = env['ir.cron'].with_context(active_test=False).search([('ir_actions_server_id', '=', act.id)], limit=1)
import datetime
cvals = {'ir_actions_server_id': act.id, 'interval_number': 1, 'interval_type': 'days', 'active': True,
         'nextcall': datetime.datetime.now().replace(hour=18, minute=30, second=0, microsecond=0) + datetime.timedelta(days=0 if datetime.datetime.now().hour < 18 else 1)}
cron.write(cvals) if cron else env['ir.cron'].create(cvals)
act.run()     # una vez ahora
pl = env['product.pricelist'].browse(2)
for t in metales:
    for p in t.product_variant_ids.sorted(lambda x: x.display_name)[:30]:
        if p.with_company(3).standard_price:
            print('  %-50s costo $%9.2f → venta $%9.2f /g' % (p.display_name, p.with_company(3).standard_price, pl._get_product_price(p, 1.0)))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit(); print('GUARDADO')
