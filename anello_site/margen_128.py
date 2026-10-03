# odoo shell < margen_128.py — 3-oct: (a) margen de anillos por metal en «Anello (Retail)» 100% → 128% (× 2.28)
#   (b) activa «Órdenes de trabajo» (pestaña Operaciones de la LdM = hechura). XB_SECO=1 ensaya.
import json, os
SECO = os.environ.get('XB_SECO', '1') == '1'
MARGEN = 128.0
T = env['product.template'].with_context(active_test=False)
anillos = T.search([('xb_precio_por_metal', '=', True)])
reglas = env['product.pricelist.item'].search([('pricelist_id', '=', 2), ('base', '=', 'standard_price'), ('product_tmpl_id', 'in', anillos.ids)])
print('reglas', len(reglas), '| markups actuales', sorted(set(reglas.mapped('price_markup'))), '| anillos sin regla', len(anillos - reglas.mapped('product_tmpl_id')))
bk = '/opt/odoo/anbn_tmp/respaldo_margen_%s.json' % env.cr.dbname
if not os.path.exists(bk):
    json.dump({r.id: [r.price_markup, r.price_discount] for r in reglas}, open(bk, 'w'))
pl = env['product.pricelist'].browse(2); PTAV = env['product.template.attribute.value']
t = T.browse(2869); comb = PTAV.search([('product_tmpl_id', '=', 2869), ('product_attribute_value_id.name', 'in', ['Oro blanco 14Kt', '4.0', 'Zirconia'])])
antes = pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0)
reglas.write({'price_markup': MARGEN})
despues = pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0)
print('regla ejemplo', reglas[:1].read(['price_markup', 'price_discount']))
print('Matera 14K con IVA: antes %.2f → ahora %.2f' % (antes * 1.16, despues * 1.16))
grp = env.ref('mrp.group_mrp_routings')
s = env['res.config.settings'].with_company(env['res.company'].browse(3)).create({})
print('órdenes de trabajo antes', s.group_mrp_routings)
s.group_mrp_routings = True
s.execute()
print('usuarios internos con el grupo', env['res.users'].search_count([('share', '=', False), ('group_ids', 'in', grp.id)]) if 'group_ids' in env['res.users']._fields else env['res.users'].search_count([('groups_id', 'in', grp.id)]))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates', 'orm_signaling_registry'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO')
