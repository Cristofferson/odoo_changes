# 5-oct: la piedra central de zirconia no estaba en la lista de materiales. Se crea por forma (mismo costo que la
# zirconia de acento) y se agrega 1 por anillo en la opción «Zirconia».
import os
SECO = os.environ.get('XB_SECO', '1') == '1'
env = env(context=dict(env.context, allowed_company_ids=[3]))
PP = env['product.product']; T = env['product.template']
ACENTO = PP.browse(76945)
FORMAS = {'redonda': 'Zirconia central redonda', 'princesa': 'Zirconia central princesa',
          'oval': 'Zirconia central oval', 'corazón': 'Zirconia central corazón'}
prods = {}
for f, n in FORMAS.items():
    p = PP.search([('name', '=', n)], limit=1)
    if not p:
        p = ACENTO.product_tmpl_id.copy({'name': n}).product_variant_id
    p.standard_price = ACENTO.standard_price
    prods[f] = p
def forma(t):
    n = t.with_context(lang='es_MX').name.lower()
    return 'princesa' if 'princesa' in n else 'oval' if 'oval' in n else 'corazón' if 'coraz' in n else 'redonda'
from collections import Counter
c = Counter(); hechos = 0
centrales = PP.browse([p.id for p in prods.values()])
for t in T.search([('xb_precio_por_metal', '=', True), ('active', '=', True)]):
    zir = t.attribute_line_ids.filtered(lambda a: a.attribute_id.id == 38).product_template_value_ids.filtered(lambda v: v.name == 'Zirconia')
    bom = env['mrp.bom'].search([('product_tmpl_id', '=', t.id), ('product_id', '=', False)], limit=1)
    if not zir or not bom:
        print('SALTO', t.id, t.name, bool(zir), bool(bom)); continue
    bom.bom_line_ids.filtered(lambda l: l.product_id in centrales).unlink()
    f = forma(t); c[f] += 1
    bom.write({'bom_line_ids': [(0, 0, {'product_id': prods[f].id, 'product_qty': 1,
                                         'bom_product_template_attribute_value_ids': [(6, 0, zir.ids)]})]})
    hechos += 1
print('fichas', hechos, dict(c), 'costo', ACENTO.standard_price)
if SECO:
    env.cr.rollback(); print('SIMULACIÓN')
else:
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO')
