# odoo shell < matera_hechura.py — la LdM de Matera (2869/4648) nació VACÍA (sin hechura). Copia las operaciones de
# hechura del molde Riomaggiore (4394): oro blanco $900, platino $1,200, estándar $700. 2-oct. Idempotente.
PTAV = env['product.template.attribute.value']
molde = env['mrp.bom'].search([('product_tmpl_id', '=', 4394)], limit=1)
for tid in (2869, 4648):
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', tid)], limit=1)
    if bom.operation_ids:
        print(tid, 'ya tiene', bom.operation_ids.mapped('name')); continue
    for op in molde.operation_ids:
        vals = PTAV.search([('product_tmpl_id', '=', tid),
                            ('product_attribute_value_id', 'in', op.bom_product_template_attribute_value_ids.product_attribute_value_id.ids)])
        if vals:
            op.copy({'bom_id': bom.id, 'bom_product_template_attribute_value_ids': [(6, 0, vals.ids)]})
    print(tid, [(o.name, o.cost, o.bom_product_template_attribute_value_ids.mapped('name')) for o in bom.operation_ids])
env.cr.commit()
pl = env['product.pricelist'].browse(2); P = env['product.template']
for tid, metal in ((2869, 'Oro blanco 10kt'), (2869, 'Oro blanco 14Kt'), (2869, 'Platino Puro (999)'), (4648, 'Oro amarillo 14kt')):
    t = P.browse(tid)
    comb = PTAV.search([('product_tmpl_id', '=', tid), ('product_attribute_value_id.name', 'in', [metal, '4.0', 'Zirconia'])])
    print(tid, metal, 'costo', round(t._xb_costo_combinacion(comb), 2), '| con IVA', round(pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0) * 1.16, 2))
