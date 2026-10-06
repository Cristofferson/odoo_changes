# Fotos de Ravello (4329 blanco, 4718 amarillo). Si existe xb_sin_central (1.12.0) lo marca y publica ambas.
import base64
D = '/opt/odoo/anbn_tmp/ravello/'
b64 = lambda f: base64.b64encode(open(D + f, 'rb').read())
T = env['product.template']; PI = env['product.image']
for tid, c in ((4329, 'blanco'), (4718, 'amarillo')):
    t = T.browse(tid)
    t.image_1920 = b64('render-%s_1.png' % c)
    t.product_template_image_ids.unlink()
    PI.create({'name': 'De lado', 'sequence': 5, 'product_tmpl_id': t.id, 'image_1920': b64('lado-%s.png' % c)})
    PI.create({'name': 'En el estuche', 'sequence': 10, 'product_tmpl_id': t.id, 'image_1920': b64('estuche-%s.png' % c)})
    if 'xb_sin_central' in t._fields:
        t.xb_sin_central = True
        t.is_published = True
    print(tid, t.product_template_image_ids.mapped('name'), 'publicada' if t.is_published else 'SIN publicar (falta 1.12.0)')
env.cr.commit()
for tb in ('orm_signaling_default', 'orm_signaling_templates'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('GUARDADO')
