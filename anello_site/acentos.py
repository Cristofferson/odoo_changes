# odoo shell < acentos.py — 3-oct: corrige las piedras de acento de 12 modelos (24 fichas) que recibieron por error
#   la lista de Amalfi (80 piedras). Lee acentos_propuesta.json. XB_SECO=1 solo simula precios (rollback).
import json, os
SECO = os.environ.get('XB_SECO', '1') == '1'
PROP = json.load(open('/opt/odoo/anbn_tmp/acentos_propuesta.json'))
PP = env['product.product']
ZIR = PP.browse(76945)
def piedra(tipo, qt):
    n = 'Diamante %s %sQts' % (tipo, qt)
    p = PP.search([('name', 'ilike', n)], limit=1)
    assert p, n
    return p
T = env['product.template']; PTAV = env['product.template.attribute.value']; pl = env['product.pricelist'].browse(2)
def precios(t):
    out = {}
    m = '14Kt' if 'blanco' in (t.with_context(lang='es_MX').name or '').lower() else '14kt'
    for pz in ('Zirconia', 'Diamante de laboratorio', 'Diamante natural'):
        comb = PTAV.search([('product_tmpl_id', '=', t.id), ('product_attribute_value_id.name', 'in', ['Oro blanco 14Kt', 'Oro amarillo 14kt', '4.0', pz])])
        out[pz] = round(pl._get_product_price(t.with_context(**t._get_product_price_context(comb)), 1.0) * 1.16, 2)
    return out
res = {}
bk = '/opt/odoo/anbn_tmp/respaldo_acentos_%s.json' % env.cr.dbname
respaldo = {}
for ref, d in PROP.items():
    for t in T.search([('xb_ref_modelo', '=', ref), ('active', '=', True), ('xb_precio_por_metal', '=', True)]):
        bom = env['mrp.bom'].search([('product_tmpl_id', '=', t.id)], limit=1)
        respaldo[t.id] = [(l.product_id.id, l.product_qty, l.bom_product_template_attribute_value_ids.ids) for l in bom.bom_line_ids]
        antes = precios(t)
        bom.bom_line_ids.unlink()
        pz = {v: PTAV.search([('product_tmpl_id', '=', t.id), ('attribute_id', '=', 38), ('product_attribute_value_id.name', '=', v)], limit=1)
              for v in ('Zirconia', 'Diamante de laboratorio', 'Diamante natural')}
        total = sum(q for q, _ in d['lineas'])
        nuevas = []
        if total:
            nuevas.append((0, 0, {'product_id': ZIR.id, 'product_qty': total, 'bom_product_template_attribute_value_ids': [(6, 0, pz['Zirconia'].ids)]}))
            for q, qt in d['lineas']:
                nuevas.append((0, 0, {'product_id': piedra('LAB', qt).id, 'product_qty': q, 'bom_product_template_attribute_value_ids': [(6, 0, pz['Diamante de laboratorio'].ids)]}))
                nuevas.append((0, 0, {'product_id': piedra('NAT', qt).id, 'product_qty': q, 'bom_product_template_attribute_value_ids': [(6, 0, pz['Diamante natural'].ids)]}))
        if nuevas:
            bom.write({'bom_line_ids': nuevas})
        t.invalidate_recordset(); bom.invalidate_recordset()
        res[t.id] = {'ref': ref, 'nombre': t.with_context(lang='es_MX').name, 'antes': antes, 'despues': precios(t),
                     'lineas': [(l.product_id.name, l.product_qty) for l in bom.bom_line_ids]}
        print(t.id, res[t.id]['nombre'][:40], antes, '→', res[t.id]['despues'])
json.dump(res, open('/tmp/acentos_sim.json', 'w'), ensure_ascii=False)
if SECO:
    env.cr.rollback(); print('SIMULACIÓN: no se guardó nada')
else:
    if not os.path.exists(bk):
        json.dump(respaldo, open(bk, 'w'))
    for t in T.browse([int(k) for k in res]):
        t.message_post(body='3-oct-2026: piedras de acento corregidas (traía por error las 80 de Amalfi). Ahora: %s' % (', '.join('%d × %s' % (q, n) for n, q in res[t.id]['lineas']) or 'sin acentos'))
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO')
