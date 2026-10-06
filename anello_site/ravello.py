# odoo shell < ravello.py — 6-oct: el 373379 pasa a ficha de ciudad «Ravello»: argolla abombada con 8 brillantes
#   incrustados a ras, SIN piedra central. Ficha blanca (4329) + gemela amarilla. XB_SECO=1 (default) ensaya.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
env = env(context=dict(env.context, allowed_company_ids=[3]))
P = env['product.template'].with_context(active_test=False)
PTAV = env['product.template.attribute.value']; PAV = env['product.attribute.value']; PP = env['product.product']
REF, PESO, ANCHO = '373379', '1.8', '3'
NOMBRE = 'Ravello · Argolla abombada con brillantes incrustados'
DESC = ('Argolla abombada de interior cómodo con ocho brillantes incrustados a ras, repartidos alrededor de la banda. '
        'Brilla desde cualquier ángulo y no se atora con nada: perfecta para usarse todos los días.')
MOLDE = P.browse(4394)
BLANCO = [113, 114, 115, 118, 136]; AMARILLO = [110, 116, 117]
MEDIDA = [173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183]
CAT = {'blanco': 21, 'amarillo': 22}

def valor(nombre, seq):
    v = PAV.search([('attribute_id', '=', 38), ('name', '=', nombre)], limit=1)
    return v or PAV.create({'attribute_id': 38, 'name': nombre, 'sequence': seq})
LAB = valor('Diamantes de laboratorio', 27); NAT = valor('Diamantes naturales', 31)
PIEDRA = [289, LAB.id, NAT.id]
ZIR = PP.browse(76945)
LAB02 = PP.search([('name', '=', 'Diamante LAB 0.02Qts SI1 G VG')], limit=1)
NAT02 = PP.search([('name', '=', 'Diamante NAT 0.02Qts SI1 G VG')], limit=1)
assert LAB02 and NAT02

def ficha(t, color):
    for lg in ('es_MX', 'en_US'):
        t.with_context(lang=lg).write({'name': NOMBRE, 'x_studio_descripcion': DESC})
    t.write({'categ_id': MOLDE.categ_id.id, 'public_categ_ids': [(6, 0, [CAT[color]])], 'xb_precio_por_metal': True,
             'available_in_pos': True, 'sale_ok': True, 'is_storable': True, 'tracking': MOLDE.tracking,
             'allow_out_of_stock_order': True, 'taxes_id': [(6, 0, MOLDE.taxes_id.ids)], 'xb_ref_modelo': REF,
             'x_studio_peso_joya': PESO, 'x_studio_ancho_joya': ANCHO, 'xb_showroom_enabled': True,
             'optional_product_ids': [(6, 0, MOLDE.optional_product_ids.ids)], 'description_sale': False, 'list_price': 0.0})
    if 'xb_sin_central' in t._fields:
        t.xb_sin_central = True
    want = {9: BLANCO if color == 'blanco' else AMARILLO, 26: MEDIDA, 38: PIEDRA}
    for l in t.attribute_line_ids:
        if l.attribute_id.id not in want:
            l.unlink()
    for a, vals in want.items():
        l = t.attribute_line_ids.filtered(lambda x: x.attribute_id.id == a)
        if l: l.write({'value_ids': [(6, 0, vals)]})
        else: t.write({'attribute_line_ids': [(0, 0, {'attribute_id': a, 'value_ids': [(6, 0, vals)]})]})
    Item = env['product.pricelist.item']
    for r in Item.search([('product_tmpl_id', '=', MOLDE.id)]):
        if not Item.search([('product_tmpl_id', '=', t.id), ('pricelist_id', '=', r.pricelist_id.id)]):
            r.copy({'product_tmpl_id': t.id, 'pricelist_id': r.pricelist_id.id})
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', t.id), ('product_id', '=', False)], limit=1)
    if not bom:
        # hechura del molde AMARILLO (Riomaggiore 4529), con sus filtros de metal llevados a esta ficha
        molde_bom = env['mrp.bom'].search([('product_tmpl_id', '=', 4529)], limit=1)
        bom = env['mrp.bom'].create({'product_tmpl_id': t.id, 'product_qty': 1, 'type': 'normal', 'company_id': t.company_id.id})
        mios = t.attribute_line_ids.product_template_value_ids
        for op in molde_bom.operation_ids:
            filtro = mios.filtered(lambda x: x.product_attribute_value_id in op.bom_product_template_attribute_value_ids.product_attribute_value_id)
            op.copy({'bom_id': bom.id, 'bom_product_template_attribute_value_ids': [(6, 0, filtro.ids)]})
    bom.bom_line_ids.unlink()
    t.invalidate_recordset()
    v38 = t.attribute_line_ids.filtered(lambda a: a.attribute_id.id == 38).product_template_value_ids
    pt = lambda vid: v38.filtered(lambda x: x.product_attribute_value_id.id == vid).ids
    bom.write({'bom_line_ids': [
        (0, 0, {'product_id': ZIR.id, 'product_qty': 8, 'bom_product_template_attribute_value_ids': [(6, 0, pt(289))]}),
        (0, 0, {'product_id': LAB02.id, 'product_qty': 8, 'bom_product_template_attribute_value_ids': [(6, 0, pt(LAB.id))]}),
        (0, 0, {'product_id': NAT02.id, 'product_qty': 8, 'bom_product_template_attribute_value_ids': [(6, 0, pt(NAT.id))]}),
    ]})
    if not t.with_context(active_test=True).product_variant_ids:
        t._create_product_variant(t._get_first_possible_combination())
    t.with_context(active_test=True).product_variant_ids[:1].default_code = f"{REF}/{'BCO' if color == 'blanco' else 'AMA'}"
    return t, bom

b, bb = ficha(P.browse(4329), 'blanco')
a = b.alternative_product_ids.filtered(lambda x: CAT['amarillo'] in x.public_categ_ids.ids)[:1]
if not a:
    a = b.copy({'is_published': False})
    a.product_template_image_ids.unlink()
a, ab = ficha(a, 'amarillo')
b.alternative_product_ids = [(4, a.id)]; a.alternative_product_ids = [(4, b.id)]
b.is_published = False; a.is_published = False

pl = env['product.pricelist'].browse(2)
for t, bom in ((b, bb), (a, ab)):
    t.invalidate_recordset()
    print('FICHA', t.id, t.with_context(lang='es_MX').name, '| ops', bom.operation_ids.mapped('name'), '| lineas', [(l.product_id.name, l.product_qty, l.bom_product_template_attribute_value_ids.mapped('name')) for l in bom.bom_line_ids])
    v = t.attribute_line_ids.product_template_value_ids
    for mv in t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9).product_template_value_ids.filtered('ptav_active'):
        for pz in v.filtered(lambda x: x.attribute_id.id == 38 and x.ptav_active):
            comb = mv | v.filtered(lambda x: x.name == '6.0') | pz
            p = pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0)
            peso = t._xb_proyectar_ptavs(comb)[0]
            if '14' in mv.name or pz.name == 'Zirconia':
                print(f'   {mv.name:20} {pz.name:26} ${p*1.16:>10,.2f}  {peso:.2f} g')
if SECO:
    env.cr.rollback(); print('ENSAYO: no se guardó nada')
else:
    b.message_post(body='6-oct-2026: el 373379 pasa a «Ravello»: argolla abombada con 8 brillantes de 0.02 qt incrustados, sin piedra central. Peso 1.8 g en 14K (hoja del taller), ancho 3 mm. Gemela amarilla: ficha %s.' % a.id)
    a.message_post(body='6-oct-2026: versión en oro amarillo de Ravello (ficha %s).' % b.id)
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO', b.id, a.id)
