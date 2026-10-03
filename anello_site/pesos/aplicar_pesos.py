# odoo shell < aplicar_pesos.py — aplica los pesos base autorizados en la página de pesos (lee /opt/odoo/anbn_tmp/pesos_decision.json:
#   {ref: peso_g}). Escribe x_studio_peso_joya en TODAS las fichas activas del modelo (blanco/amarillo). XB_SECO=1 ensaya.
import json, os
SECO = os.environ.get('XB_SECO', '1') == '1'
dec = json.load(open('/opt/odoo/anbn_tmp/pesos_decision.json'))
T = env['product.template']
bk = '/opt/odoo/anbn_tmp/respaldo_pesos_%s.json' % env.cr.dbname
resp = {}
for ref, peso in dec.items():
    ts = T.search([('xb_ref_modelo', '=', ref), ('active', '=', True), ('xb_precio_por_metal', '=', True)])
    for t in ts:
        resp[t.id] = t.x_studio_peso_joya
        if (t.x_studio_peso_joya or '') != str(peso):
            print(ref, t.id, t.with_context(lang='es_MX').name, t.x_studio_peso_joya, '→', peso)
            t.x_studio_peso_joya = str(peso)
            if not SECO:
                t.message_post(body='3-oct-2026: peso base (14K, medida 4) %s g → %s g, autorizado en la revisión visual de pesos.' % (resp[t.id], peso))
if SECO:
    env.cr.rollback(); print('ENSAYO')
else:
    if not os.path.exists(bk):
        json.dump(resp, open(bk, 'w'))
    env.cr.commit()
    for tb in ('orm_signaling_default', 'orm_signaling_templates'):
        env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
    env.cr.commit(); print('GUARDADO', len(resp))
