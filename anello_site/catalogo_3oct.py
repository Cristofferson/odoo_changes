# odoo shell < catalogo_3oct.py — 3-oct (decisiones del usuario):
#  A) archiva repetidos: Mantua 373235 y Génova 373258 (se queda Merano 373221), Orvieto 373289 (se queda Cefalú 373287)
#  B) bitono → metal «Oro bitono 10/14/18Kt», categoría web «Bitono», hechura $900
#  C) quita el color del nombre (el metal va en el atributo)
#  D) quita el atributo Ancho de los anillos de compromiso y guarda el ancho estimado de la banda en x_studio_ancho_joya
import json, os, re
SECO = os.environ.get('XB_SECO', '1') == '1'
T = env['product.template'].with_context(active_test=False)
PTAV = env['product.template.attribute.value']
fichas = T.search([('xb_precio_por_metal', '=', True), ('active', '=', True)])
# A
rep = T.search([('xb_ref_modelo', 'in', ['373235', '373258', '373289']), ('active', '=', True)])
print('A archivar', [(t.id, t.name) for t in rep])
rep.write({'active': False, 'is_published': False})
fichas -= rep
# B
Cat = env['product.public.category']
bit_cat = Cat.search([('name', '=', 'Bitono'), ('parent_id', '=', 18)], limit=1) or Cat.create({'name': 'Bitono', 'parent_id': 18, 'website_id': False})
BIT = [201, 202, 203]
molde_op = env['mrp.bom'].search([('product_tmpl_id', '=', 4394)], limit=1).operation_ids.filtered(lambda o: o.name == 'Hechura oro blanco')[:1]
bitono = fichas.filtered(lambda t: re.search(r'·\s*Bitono\s*$', t.with_context(lang='es_MX').name or ''))
print('B bitono', len(bitono))
for t in bitono:
    line = t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9)
    line.write({'value_ids': [(6, 0, BIT)]})
    t.write({'public_categ_ids': [(6, 0, [bit_cat.id])]})
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', t.id)], limit=1)
    vals = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', 'in', BIT)])
    if bom and not bom.operation_ids.filtered(lambda o: o.name == 'Hechura bitono'):
        molde_op.copy({'bom_id': bom.id, 'name': 'Hechura bitono', 'bom_product_template_attribute_value_ids': [(6, 0, vals.ids)]})
    v = t.with_context(active_test=True).product_variant_ids[:1]
    if v and v.default_code and re.search(r'/(AMA|BCO)$', v.default_code):
        v.default_code = re.sub(r'/(AMA|BCO)$', '/BIT', v.default_code)
# C
SUF = r'\s*·\s*(Oro blanco|Oro amarillo|Bitono|White gold|Yellow gold|Two-tone|White Gold|Yellow Gold)\s*$'
n = 0
for t in fichas:
    for lg in ('es_MX', 'en_US'):
        nm = t.with_context(lang=lg).name or ''
        nuevo = re.sub(SUF, '', nm)
        if nuevo != nm:
            t.with_context(lang=lg).write({'name': nuevo}); n += 1
print('C nombres cambiados', n)
# D
anchos = json.load(open('/opt/odoo/anbn_tmp/anchos.json'))
quitadas = 0
for t in fichas:
    l = t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 25)
    if l and t.categ_id.complete_name == 'Anillo / Montadura':
        l.unlink(); quitadas += 1
    a = anchos.get(t.xb_ref_modelo or '')
    if a:
        t.x_studio_ancho_joya = ('%.1f' % a).rstrip('0').rstrip('.')
print('D ancho quitado en', quitadas, '| ancho guardado en', len(fichas.filtered('x_studio_ancho_joya')))
# muestra de precios tras el cambio
pl = env['product.pricelist'].browse(2)
for t in bitono[:3] | fichas.filtered(lambda x: x.xb_ref_modelo == '373721')[:1]:
    comb = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id.name', 'in', ['Oro bitono 14Kt', 'Oro blanco 14Kt', '4.0', 'Zirconia'])])
    print('  ', t.id, t.with_context(lang='es_MX').name, '| metales', t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9).value_ids.mapped('name'),
          '| 14K $%.2f' % (pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0) * 1.16), '| ancho', t.x_studio_ancho_joya,
          '| attrs', t.attribute_line_ids.mapped('attribute_id.name'))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO')
