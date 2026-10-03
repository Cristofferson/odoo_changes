# odoo shell < descripciones_3oct.py — descripción corta de venta por modelo en x_studio_descripcion (la usa el muro). 3-oct.
import json
D = json.load(open('/opt/odoo/anbn_tmp/descripciones.json'))
T = env['product.template']
n = 0
for t in T.search([('xb_precio_por_metal', '=', True), ('active', '=', True)]):
    d = D.get(t.xb_ref_modelo or '')
    if d and t.x_studio_descripcion != d:
        t.x_studio_descripcion = d; n += 1
env.cr.commit(); print('descripciones', n)
