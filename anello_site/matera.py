# odoo shell -d <BD> < matera.py — la montadura 2869 pasa a ficha de anillo de ciudad «Matera» (2-oct).
#   Mismo tratamiento que Riomaggiore (4394/4529): nombre, categoría, metales, medidas, piedra, peso, precio, ficha gemela en amarillo.
#   XB_SECO=1 (default) ensaya y deshace. Idempotente.
import os, re
SECO = os.environ.get('XB_SECO', '1') == '1'
P = env['product.template'].with_context(active_test=False)
PTAV = env['product.template.attribute.value']
REF, PESO, BASE = '373721', '3.8', 'Matera · Princesa en punta en tensión'
MOLDE = P.browse(4394)                       # Riomaggiore blanco: de aquí se copian reglas y extras
BLANCO = [113, 114, 115, 118, 136]; AMARILLO = [110, 116, 117]
MEDIDA = [173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183]; PIEDRA = [289, 290, 291]
CAT = {'blanco': 21, 'amarillo': 22}; SUF = {'blanco': 'Oro blanco', 'amarillo': 'Oro amarillo'}

def lineas(t, metales):
    want = {9: metales, 26: MEDIDA, 38: PIEDRA}
    for l in t.attribute_line_ids:
        if l.attribute_id.id not in want:
            l.unlink()
    for a, vals in want.items():
        l = t.attribute_line_ids.filtered(lambda x: x.attribute_id.id == a)
        if l:
            l.write({'value_ids': [(6, 0, vals)]})
        else:
            t.write({'attribute_line_ids': [(0, 0, {'attribute_id': a, 'value_ids': [(6, 0, vals)]})]})
    # recargos de la piedra central iguales al molde
    for m in PTAV.search([('product_tmpl_id', '=', MOLDE.id), ('attribute_id', '=', 38)]):
        PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', '=', m.product_attribute_value_id.id)]).price_extra = m.price_extra

def ficha(t, color):
    nombre = f'{BASE} · {SUF[color]}'
    for lg in ('es_MX', 'en_US'):
        t.with_context(lang=lg).write({'name': nombre})
    t.write({'categ_id': MOLDE.categ_id.id, 'public_categ_ids': [(6, 0, [CAT[color]])], 'xb_precio_por_metal': True,
             'available_in_pos': True, 'sale_ok': True, 'is_storable': True, 'tracking': MOLDE.tracking,
             'taxes_id': [(6, 0, MOLDE.taxes_id.ids)], 'xb_ref_modelo': REF, 'x_studio_peso_joya': PESO,
             'xb_showroom_enabled': True, 'optional_product_ids': [(6, 0, MOLDE.optional_product_ids.ids)],
             'description_sale': False, 'list_price': 0.0})
    lineas(t, BLANCO if color == 'blanco' else AMARILLO)
    # reglas de precio (Anello Retail ×2, PreCompra) como el molde
    Item = env['product.pricelist.item']
    for r in Item.search([('product_tmpl_id', '=', MOLDE.id)]):
        if not Item.search([('product_tmpl_id', '=', t.id), ('pricelist_id', '=', r.pricelist_id.id)]):
            r.copy({'product_tmpl_id': t.id, 'pricelist_id': r.pricelist_id.id})
    if not env['mrp.bom'].search([('product_tmpl_id', '=', t.id)]):
        env['mrp.bom'].create({'product_tmpl_id': t.id, 'product_qty': 1, 'type': 'normal', 'company_id': t.company_id.id})
    if not t.with_context(active_test=True).product_variant_ids:
        t._create_product_variant(t._get_first_possible_combination())
    v = t.with_context(active_test=True).product_variant_ids[:1]
    v.default_code = f"{REF}/{'BCO' if color == 'blanco' else 'AMA'}"
    return t

b = ficha(P.browse(2869), 'blanco')
for im in b.product_template_image_ids:
    im.name = 'Otra vista'
a = b.alternative_product_ids.filtered(lambda x: CAT['amarillo'] in x.public_categ_ids.ids)[:1]
if not a:
    a = b.copy({'is_published': False})
    a.product_template_image_ids.unlink()
    a.image_1920 = False             # 🚨 la foto es del anillo BLANCO: la amarilla espera su imagen
a = ficha(a, 'amarillo')
b.alternative_product_ids = [(4, a.id)]; a.alternative_product_ids = [(4, b.id)]
b.is_published = True; a.is_published = False

pl = env['product.pricelist'].browse(2)
for t in (b, a):
    t.invalidate_recordset()
    for mv in t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9).product_template_value_ids:
        comb = mv | PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', 'in', [175, 289])])
        p = pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0)
        peso, fino, metal = t._xb_proyectar_ptavs(comb)
        print(f'  {t.id} {mv.name:22} talla 4 zirconia: ${p * 1.16:,.2f} con IVA | {peso:.2f} g')
    print('FICHA', t.id, t.with_context(lang='es_MX').name, '| web', t.public_categ_ids.mapped('name'), '| pub', t.is_published,
          '| var', t.with_context(active_test=True).product_variant_ids.mapped('default_code'), '| alt', t.alternative_product_ids.ids,
          '| foto', bool(t.image_1920), '| attrs', [(l.attribute_id.name, len(l.value_ids)) for l in t.attribute_line_ids])
if SECO:
    env.cr.rollback(); print('ENSAYO: no se guardó nada')
else:
    b.message_post(body='2-oct-2026: la montadura sin clave pasa a ficha «Matera» (clave 373721 asignada, peso 3.8 g en 14K ESTIMADO, no pesado). Gemela en amarillo: ficha %s, sin publicar hasta tener imagen.' % a.id)
    a.message_post(body='2-oct-2026: versión en oro amarillo de Matera (ficha %s). Sin publicar: falta su imagen.' % b.id)
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO')
