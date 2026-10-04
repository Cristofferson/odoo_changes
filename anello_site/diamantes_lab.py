# odoo shell < diamantes_lab.py — 3-oct: el cliente elige el TAMAÑO del diamante de laboratorio central en la web.
#  1) 5 productos «Diamante LAB X.XXQts VVS2 E ID» (talla Ideal, color E, pureza VVS2, certificado ICERT) con su costo.
#  2) valores de «Piedra»: «Diamante de laboratorio 0.50 ct» … «2.00 ct». El genérico «Diamante de laboratorio» (290)
#     se OCULTA en la web (sigue en caja y Ventas para cotizar a mano).
#  3) a cada anillo con «Piedra»: los 5 tamaños + línea de LdM con su diamante central + los acentos LAB también aplican.
#  XB_SECO=1 ensaya.
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
TAM = [('0.50', 3000.0), ('0.75', 4900.0), ('1.00', 7000.0), ('1.50', 11300.0), ('2.00', 16000.0)]
PT = env['product.template'].with_company(3); PP = env['product.product']
PAV = env['product.attribute.value']; PTAV = env['product.template.attribute.value']
molde = PP.browse(76923).product_tmpl_id   # Diamante LAB 0.02Qts SI1 G VG
prods = {}
for qt, costo in TAM:
    nombre = 'Diamante LAB %sQts VVS2 E ID' % qt
    t = PT.search([('name', '=', nombre)], limit=1)
    if not t:
        t = molde.copy({'name': nombre, 'default_code': 'LAB-%s-VVS2-E-ID' % qt.replace('.', ''), 'sale_ok': False,
                        'description_sale': 'Diamante creado en laboratorio de %s ct · talla Ideal · color E · pureza VVS2 · certificado ICERT' % qt})
        for lg in ('es_MX', 'en_US'):
            t.with_context(lang=lg).name = nombre
    t.with_company(3).standard_price = costo
    prods[qt] = t.product_variant_id
    print('producto', t.id, nombre, t.with_company(3).standard_price)
vals = {}
base = PAV.browse(290)
for k, (qt, _c) in enumerate(TAM):
    nm = 'Diamante de laboratorio %s ct' % qt
    v = PAV.search([('attribute_id', '=', 38), ('name', '=', nm)], limit=1) or PAV.create(
        {'attribute_id': 38, 'name': nm, 'sequence': (base.sequence or 0) + 1 + k})
    vals[qt] = v
base.xb_ocultar_web = True
fichas = PT.search([('active', '=', True), ('attribute_line_ids.attribute_id', '=', 38)])
print('fichas con Piedra', len(fichas))
for t in fichas:
    line = t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 38)
    line.write({'value_ids': [(4, v.id) for v in vals.values()]})
    nuevos = {qt: PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', '=', v.id)], limit=1) for qt, v in vals.items()}
    lab290 = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id', '=', 290)], limit=1)
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', t.id), ('product_id', '=', False)], limit=1)
    if not bom:
        bom = env['mrp.bom'].create({'product_tmpl_id': t.id, 'product_qty': 1, 'type': 'normal', 'company_id': t.company_id.id})
    # acentos LAB: también con cualquier tamaño de laboratorio
    for l in bom.bom_line_ids.filtered(lambda l: lab290 in l.bom_product_template_attribute_value_ids):
        l.bom_product_template_attribute_value_ids = [(4, p.id) for p in nuevos.values()]
    # diamante central, una línea por tamaño
    for qt, ptav in nuevos.items():
        if not bom.bom_line_ids.filtered(lambda l: l.product_id == prods[qt]):
            bom.write({'bom_line_ids': [(0, 0, {'product_id': prods[qt].id, 'product_qty': 1,
                                                 'bom_product_template_attribute_value_ids': [(6, 0, ptav.ids)]})]})
# muestra de precios
pl = env['product.pricelist'].browse(2)
for ref in ('373721', '373307'):
    t = PT.search([('xb_ref_modelo', '=', ref), ('active', '=', True)], limit=1)
    if not t:
        continue
    met = t.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9).product_template_value_ids.filtered(lambda v: '14' in v.name)[:1]
    med = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id.name', '=', '4.0')], limit=1)
    for pz in ['Zirconia'] + ['Diamante de laboratorio %s ct' % q for q, _ in TAM]:
        p = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id.name', '=', pz)], limit=1)
        comb = met | med | p
        print('  %s %-32s $%10.2f' % (t.name[:20], pz, pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0) * 1.16))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO')
