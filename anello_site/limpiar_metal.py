# odoo shell -d <BD> < limpiar_metal.py — limpieza del atributo Metal (id 9). Idempotente. NO toca monedas.
#   1) Quita las opciones «Oro NKt» duplicadas de los productos que ya tienen su equivalente «Oro amarillo NKt»
#      (misma ley y densidad → mismo precio). Odoo archiva las variantes que las usaban; el historial queda.
#   2) Donde el producto NO tiene el equivalente, cambia la duplicada por el equivalente.
#   3) Archiva los valores que ya no usa ningún producto.
#   4) Oculta en la web los materiales que no son oro ni platino (siguen en caja y Ventas).
# Variable SECO = True: solo informa, no escribe.
import json, os
SECO = os.environ.get('XB_SECO', '1') == '1'
DB = env.cr.dbname
D = '/opt/odoo/anbn_tmp/'
PAV = env['product.attribute.value'].sudo().with_context(active_test=False)
T = env['product.template'].sudo().with_context(active_test=False)
PAR = {222: 221, 223: 116, 224: 117, 225: 110, 226: 2, 227: 146}   # duplicada → equivalente
for d, e in PAR.items():
    a, b = PAV.browse(d), PAV.browse(e)
    assert a.attribute_id.id == b.attribute_id.id == 9 and (a.x_ley, a.x_densidad) == (b.x_ley, b.x_densidad), (a.name, b.name)

# Montefalco (4270): anillo de compromiso BLANCO que quedó en la categoría Argolla con 22K y duplicados.
#   Se deja como los demás blancos (molde Amalfi 4322): categoría Montadura, web «Oro blanco», metales blancos.
BLANCO = [113, 114, 115, 118, 136]
mont = T.browse(4270)
if mont.exists() and mont.categ_id.id != 86:
    print('Montefalco: categoría', mont.categ_id.name, '→ Anillo / Montadura; web → Oro blanco; metales → blanco')
    if not SECO:
        mont.write({'categ_id': 86, 'public_categ_ids': [(6, 0, [21])]})
        mline = mont.attribute_line_ids.filtered(lambda l: l.attribute_id.id == 9)
        mline.write({'value_ids': [(6, 0, BLANCO)]})
        for lg in ('es_MX', 'en_US'):
            n = mont.with_context(lang=lg).name or ''
            if not n.endswith('· Oro blanco'):
                mont.with_context(lang=lg).write({'name': n.strip() + ' · Oro blanco'})
        mont.with_context(active_test=True).product_variant_ids.write({'default_code': '373232/BCO'})
        env.cr.commit()

MONEDAS = T.search([('categ_id.name', '=', 'Centenario')]) | T.search([('name', 'ilike', 'moneda')])
lineas = env['product.template.attribute.line'].sudo().search([('attribute_id', '=', 9)])
quitar, cambiar = [], []
for l in lineas:
    if l.product_tmpl_id in MONEDAS:
        continue
    vals = set(l.value_ids.ids)
    for d, e in PAR.items():
        if d in vals:
            (quitar if e in vals else cambiar).append((l, d, e))

usados = set(lineas.mapped('value_ids').ids)
OCULTAR = PAV.search([('attribute_id', '=', 9), '|', '|', '|', ('name', 'ilike', 'imitaci'), ('name', 'ilike', 'tumbaga'),
                      ('name', 'ilike', 'acero'), ('name', 'ilike', 'plata')]) | PAV.browse([145, 146])   # 22K: solo oculto en la web

print('quitar duplicada (ya tiene equivalente):', len(quitar), '| cambiar por equivalente:', len(cambiar))
for l, d, e in cambiar:
    print('   cambiar', l.product_tmpl_id.id, l.product_tmpl_id.name, ':', PAV.browse(d).name, '→', PAV.browse(e).name)
print('monedas excluidas:', MONEDAS.mapped('name'))
print('ocultar en web:', sorted(OCULTAR.mapped('name')))

if not SECO:
    bk = D + 'respaldo_metal_%s.json' % DB
    if not os.path.exists(bk):
        json.dump({'lineas': {l.id: l.value_ids.ids for l in lineas},
                   'activos': PAV.search([('attribute_id', '=', 9)]).filtered('active').ids,
                   'ocultos': PAV.search([('attribute_id', '=', 9), ('xb_ocultar_web', '=', True)]).ids}, open(bk, 'w'))
    for l, d, e in quitar:
        l.write({'value_ids': [(3, d)]})
    for l, d, e in cambiar:
        l.write({'value_ids': [(3, d), (4, e)]})
    OCULTAR.write({'xb_ocultar_web': True})
    env.cr.commit()
    usados = set(env['product.template.attribute.line'].sudo().search([('attribute_id', '=', 9)]).mapped('value_ids').ids)
    archivar = PAV.search([('attribute_id', '=', 9), ('active', '=', True)]).filtered(lambda v: v.id not in usados)
    archivar.write({'active': False})
    env.cr.commit()
    print('ARCHIVADOS:', sorted(archivar.mapped('name')))
    print('OK', DB, 'quitadas', len(quitar), 'cambiadas', len(cambiar))
else:
    usados_despues = usados - {d for _, d, _ in quitar + cambiar}
    print('se archivarían (sin uso):', sorted(PAV.search([('attribute_id', '=', 9), ('active', '=', True)]).filtered(lambda v: v.id not in usados_despues).mapped('name')))
    print('SECO: no se escribió nada')
