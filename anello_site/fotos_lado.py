# odoo shell < fotos_lado.py — agrega la foto «De lado» (vista de frente con el hueco del aro) a cada ficha, en el color de la ficha. 3-oct.
#   Lee /opt/odoo/anbn_tmp/lado_jobs.json y las imágenes en /opt/odoo/anbn_tmp/lado/. Idempotente: reemplaza la «De lado» previa.
import json, os, base64
jobs = json.load(open('/opt/odoo/anbn_tmp/lado_jobs.json'))
PI = env['product.image']; T = env['product.template']
hechas = faltan = 0
for j in jobs:
    f = '/opt/odoo/anbn_tmp/' + j['out']
    t = T.browse(j['ficha'])
    if not t.exists() or not t.active:
        continue
    if not os.path.exists(f):
        faltan += 1; print('falta', j['ref'], j['want']); continue
    t.product_template_image_ids.filtered(lambda i: i.name == 'De lado').unlink()
    PI.create({'name': 'De lado', 'sequence': 5, 'product_tmpl_id': t.id, 'image_1920': base64.b64encode(open(f, 'rb').read())})
    hechas += 1
env.cr.commit()
for tb in ('orm_signaling_default', 'orm_signaling_templates'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('fotos de lado', hechas, '| faltan', faltan)
