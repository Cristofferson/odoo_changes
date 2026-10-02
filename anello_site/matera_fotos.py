# odoo shell < matera_fotos.py — render + estuche de Matera (2869 blanco, 4648 amarillo) y publica la amarilla. 2-oct.
import base64
D = '/opt/odoo/anbn_tmp/matera/373721-'
b64 = lambda f: base64.b64encode(open(D + f, 'rb').read())
P = env['product.template']
for tid, sfx, est in ((2869, 'render-BCO_1', 'estuche-BCO-B'), (4648, 'render-AMA_1', 'estuche-AMA-B')):
    t = P.browse(tid)
    t.image_1920 = b64(sfx + '.png')
    t.product_template_image_ids.unlink()
    env['product.image'].create({'name': 'En el estuche', 'sequence': 10, 'product_tmpl_id': t.id, 'image_1920': b64(est + '.png')})
    t.is_published = True
    t.message_post(body='2-oct-2026: render de catálogo y foto en el estuche generados (gpt-image-2) a partir de las fotos del proveedor.')
    print(tid, t.with_context(lang='es_MX').name, '| fotos', t.product_template_image_ids.mapped('name'), '| pub', t.is_published)
env.cr.commit()
for tb in ('orm_signaling_default', 'orm_signaling_templates'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('GUARDADO')
