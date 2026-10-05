# Opción «otro tamaño»: el anillo se cobra sin centro y el diamante va en otro renglón del pedido.
env = env(context=dict(env.context, allowed_company_ids=[3], lang='es_MX'))
v = env['product.attribute.value'].browse(290)
nombre = 'Diamante de laboratorio · otro tamaño (sin centro)'
v.with_context(lang='es_MX').name = nombre
v.with_context(lang='en_US').name = nombre
print('opción:', v.name, '| oculta en web:', v.xb_ocultar_web)

ref = env['product.template'].browse(4657)          # Diamante LAB 1.00 ct: misma categoría e IVA
P = env['product.template']
t = P.search([('default_code', '=', 'DLAB-MEDIDA'), ('company_id', 'in', [3, False])], limit=1)
vals = {
    'name': 'Diamante de laboratorio a la medida (centro)',
    'default_code': 'DLAB-MEDIDA',
    'type': 'consu', 'is_storable': False, 'tracking': 'none',
    'sale_ok': True, 'purchase_ok': True, 'available_in_pos': True,
    'list_price': 0.0,
    'categ_id': ref.categ_id.id,
    'taxes_id': [(6, 0, ref.taxes_id.ids)],
    'pos_categ_ids': [(6, 0, env['pos.category'].search([('name', '=', 'Gema')], limit=1).ids)],
    'company_id': 3,
    'description_sale': 'Diamante de laboratorio para el centro de un anillo, en un tamaño fuera de los 5 de catálogo. '
                        'Anotar quilataje, color y pureza; el precio lo captura el asesor.',
}
if t:
    t.write(vals)
else:
    t = P.create(vals)
print('producto:', t.id, t.display_name, t.pos_categ_ids.mapped('name'), t.taxes_id.mapped('name'))
env.cr.commit()
