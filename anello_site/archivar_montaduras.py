# odoo shell -d <BD> < archivar_montaduras.py — archiva las «MONTADURA DE…» que el usuario marcó (2-oct). No borra nada.
import json, os
SECO = os.environ.get('XB_SECO', '1') == '1'
ids = json.load(open('/opt/odoo/anbn_tmp/archivar_ids.json'))
T = env['product.template'].sudo().with_context(active_test=False)
ts = T.browse(ids).exists()
malos = ts.filtered(lambda t: not (t.with_context(lang='es_MX').name or t.name or '').upper().startswith('MONTADURA DE'))
assert not malos, ('no son montaduras', malos.ids)
activos = ts.filtered('active')
print('marcadas', len(ids), '| existen', len(ts), '| activas por archivar', len(activos))
bk = '/opt/odoo/anbn_tmp/respaldo_montaduras_%s.json' % env.cr.dbname
if not SECO:
    if not os.path.exists(bk):
        json.dump({'templates': activos.ids, 'variantes': activos.with_context(active_test=True).product_variant_ids.ids}, open(bk, 'w'))
    activos.write({'active': False})
    env.cr.commit()
    print('ARCHIVADAS', len(activos), '| siguen activas:', T.search_count([('id', 'in', ids), ('active', '=', True)]))
else:
    print('SECO: no se escribió nada')
