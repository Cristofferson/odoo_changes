# 5-oct: Padua no lleva piedras de acento (los «baguettes» eran escalones de metal) y Sorrento lleva brillantes
# redondos sobre placas en abanico (no baguettes). Nombre, render, vista de lado y estuche nuevos.
import base64, re
D = '/opt/odoo/anbn_tmp/fix-oct5/'
b64 = lambda f: base64.b64encode(open(D + f, 'rb').read())
T = env['product.template']; PI = env['product.image']
FICHAS = {
    4510: ('Padua · Solitario con hombros escalonados', '373210-blanco_1.png', None, '373210-estuche-blanco.png'),
    4260: ('Padua · Solitario con hombros escalonados', '373210-amarillo_1.png', None, '373210-estuche-amarillo.png'),
    4338: ('Sorrento · Solitario con piedras graduadas en abanico', '373250-blanco_2.png', '373250-lado-blanco_1.png', '373250-estuche-blanco.png'),
    4526: ('Sorrento · Solitario con piedras graduadas en abanico', '373250-amarillo-v2_1.png', '373250-lado-amarillo_1.png', '373250-estuche-amarillo.png'),
}
for tid, (nombre, render, lado, estuche) in FICHAS.items():
    t = T.browse(tid)
    for lang in ('es_MX', 'en_US'):
        t.with_context(lang=lang).name = nombre
    t.image_1920 = b64(render)
    quitar = t.product_template_image_ids.filtered(lambda i: i.name in ('En el estuche', 'En la mano') or (lado and i.name == 'De lado'))
    quitar.unlink()
    if lado:
        PI.create({'name': 'De lado', 'sequence': 5, 'product_tmpl_id': t.id, 'image_1920': b64(lado)})
    PI.create({'name': 'En el estuche', 'sequence': 10, 'product_tmpl_id': t.id, 'image_1920': b64(estuche)})
    # el video se hizo con el render viejo (con baguettes): fuera
    if 'anello-video' in (t.description_ecommerce or ''):
        t.description_ecommerce = re.sub(r'<!--anello-video-->\s*<div class="o_anello_video">.*?</div>', '', str(t.description_ecommerce), flags=re.S)
    t.message_post(body='5-oct-2026: nombre corregido y fotos rehechas (gpt-image-2): %s.' % (
        'sin piedras de acento; los escalones de los hombros son metal' if tid in (4510, 4260) else 'brillantes redondos sobre placas en abanico, sin baguettes'))
    print(tid, t.with_context(lang='es_MX').name, t.product_template_image_ids.mapped('name'), 'video' if 'anello-video' in (t.description_ecommerce or '') else 'sin video')
env.cr.commit()
for tb in ('orm_signaling_default', 'orm_signaling_templates'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('GUARDADO')
