# odoo shell < acentos2.py — 5-oct: piedras de acento revisadas modelo por modelo (acentos2_propuesta.json).
# XB_SECO=1 (por omisión) solo simula y guarda precios antes/después; XB_REFS=ref,ref limita los modelos.
import json, os, re
SECO = os.environ.get('XB_SECO', '1') == '1'
REFS = [r for r in os.environ.get('XB_REFS', '').split(',') if r]
PROP = json.load(open('/opt/odoo/anbn_tmp/acentos2_propuesta.json'))
env = env(context=dict(env.context, allowed_company_ids=[3]))
PP = env['product.product']; T = env['product.template']; PTAV = env['product.template.attribute.value']
pl = env['product.pricelist'].browse(2)
ZIR = PP.browse(76945)
ES_ACENTO = re.compile(r'^Diamante (LAB|NAT) [\d.]+Qts (SI1|VS1) ')

def piedra(tipo, qt, forma):
    base = 'Diamante %s %sQts ' % (tipo, qt)
    cands = PP.search([('name', '=like', base + '%')])
    p = cands.filtered(lambda x: x.name.endswith(' ' + forma)) if forma else \
        cands.filtered(lambda x: not re.search(r'Baguette|Princesa|Marquesa', x.name))
    assert len(p) >= 1, (tipo, qt, forma)
    return p[0]

def combo(t, piedra_nombre):
    v = t.attribute_line_ids.product_template_value_ids
    metal = v.filtered(lambda x: x.attribute_id.id == 9 and '14' in x.name)[:1] or v.filtered(lambda x: x.attribute_id.id == 9)[:1]
    medida = v.filtered(lambda x: x.name == '6.0')[:1]
    pz = v.filtered(lambda x: x.attribute_id.id == 38 and x.name == piedra_nombre)[:1]
    return metal | medida | pz

def precios(t):
    out = {}
    for k, n in (('zir', 'Zirconia'), ('lab', 'Diamante de laboratorio 1.00 ct'), ('nat', 'Diamante natural')):
        c = combo(t, n)
        out[k] = round(pl._get_product_price(t.with_context(**t._get_product_price_context(c)), 1.0) * 1.16, 0)
    return out

res = {}
for ref, d in PROP.items():
    if REFS and ref not in REFS:
        continue
    for t in T.search([('xb_ref_modelo', '=', ref), ('active', '=', True), ('xb_precio_por_metal', '=', True)]):
        bom = env['mrp.bom'].search([('product_tmpl_id', '=', t.id), ('product_id', '=', False)], limit=1)
        antes = precios(t)
        viejas = bom.bom_line_ids.filtered(lambda l: l.product_id == ZIR or ES_ACENTO.match(l.product_id.name or ''))
        quitadas = [(l.product_id.name, l.product_qty) for l in viejas]
        viejas.unlink()
        v38 = t.attribute_line_ids.filtered(lambda a: a.attribute_id.id == 38).product_template_value_ids
        zir = v38.filtered(lambda x: x.name == 'Zirconia')
        lab = v38.filtered(lambda x: x.name.startswith('Diamante de laboratorio'))
        nat = v38.filtered(lambda x: x.name == 'Diamante natural')
        nuevas = []
        total = sum(q for q, _, _ in d['lineas'])
        if total:
            nuevas.append((0, 0, {'product_id': ZIR.id, 'product_qty': total, 'bom_product_template_attribute_value_ids': [(6, 0, zir.ids)]}))
            for q, qt, forma in d['lineas']:
                nuevas.append((0, 0, {'product_id': piedra('LAB', qt, forma).id, 'product_qty': q, 'bom_product_template_attribute_value_ids': [(6, 0, lab.ids)]}))
                nuevas.append((0, 0, {'product_id': piedra('NAT', qt, forma).id, 'product_qty': q, 'bom_product_template_attribute_value_ids': [(6, 0, nat.ids)]}))
            bom.write({'bom_line_ids': nuevas})
        t.invalidate_recordset(); bom.invalidate_recordset()
        res[t.id] = {'ref': ref, 'nombre': t.with_context(lang='es_MX').name,
                     'metal': combo(t, 'Zirconia').filtered(lambda x: x.attribute_id.id == 9).name,
                     'antes': antes, 'despues': precios(t), 'quitadas': quitadas,
                     'lineas': [(l.product_id.name, l.product_qty) for l in bom.bom_line_ids if l.product_id == ZIR or ES_ACENTO.match(l.product_id.name or '')]}
        print(t.id, ref, res[t.id]['nombre'][:30], antes, '→', res[t.id]['despues'])
json.dump(res, open('/opt/odoo/anbn_tmp/acentos2_sim.json', 'w'), ensure_ascii=False)
if SECO:
    env.cr.rollback(); print('SIMULACIÓN: no se guardó nada')
else:
    for t in T.browse([int(k) for k in res]):
        t.message_post(body='5-oct-2026: piedras de acento revisadas contra la foto. Ahora: %s' % (
            ', '.join('%d × %s' % (q, n) for n, q in res[t.id]['lineas']) or 'sin acentos'))
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO', len(res))
