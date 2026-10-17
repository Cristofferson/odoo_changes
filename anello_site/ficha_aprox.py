# odoo shell < ficha_aprox.py — página del producto (3-oct, v2):
#  · «Ficha de la pieza»: «· aproximado» junto al peso, ancho de banda, PIEDRAS y características de los DIAMANTES
#    (cambian con la piedra elegida, vía xb_joyeria_peso_precio 1.4.0); sin la leyenda larga de «peso y precio aproximados».
#  · descripción persuasiva bajo el nombre (x_studio_descripcion).
#  · botones: se quita «Agenda una cita»; la liga va en la frase «Agenda una cita en nuestro Estudio de Morelia».
V = env['ir.ui.view']
def vista(key, name, padre, arch, prio=30, website=False):
    v = V.with_context(active_test=False).search([('key', '=', key)], limit=1)
    vals = {'name': name, 'key': key, 'type': 'qweb', 'mode': 'extension', 'inherit_id': padre.id,
            'priority': prio, 'active': True, 'website_id': website}
    if not v:
        v = V.create(dict(vals, arch=arch))
    for lg in ('en_US', 'es_MX'):
        v.with_context(lang=lg).write(dict(vals, arch=arch))
    return v
ficha = '''<data>
  <xpath expr="//span[@id='dmn_fino']/.." position="after">
    <span class="text-muted fst-italic"> · aproximado</span>
  </xpath>
  <xpath expr="//li[span[@id='dmn_peso']]" position="after">
    <li t-if="product.x_studio_ancho_joya" class="mb-1"><strong>Ancho de la banda:</strong> <span t-out="product.x_studio_ancho_joya"/> mm aprox.</li>
    <li t-attf-class="mb-1 {{'' if combination_info.get('xb_gemas') else 'd-none'}}"><strong>Piedras:</strong> <span id="xb_gemas" t-out="combination_info.get('xb_gemas')"/></li>
    <li t-attf-class="mb-1 {{'' if combination_info.get('xb_diamantes') else 'd-none'}}"><strong>Diamantes:</strong>
      <ul id="xb_diamantes" class="mb-0 ps-3"><li t-foreach="combination_info.get('xb_diamantes') or []" t-as="d" t-out="d"/></ul>
    </li>
    <li t-if="product.sale_delay" class="mb-1"><strong>Fabricación:</strong> aproximadamente <t t-out="int(product.sale_delay)"/> días desde que se confirma el pedido</li>
  </xpath>
  <xpath expr="//div[hasclass('form-text')]" position="replace"/>
  <xpath expr="//li[span[@id='dmn_stones']]" position="replace"/>
</data>'''
v1 = vista('anbn.ficha_aprox', 'Anello: ficha con peso aproximado, ancho, piedras y diamantes', env.ref('stij_website.dmn_ficha_tecnica'), ficha)
pitch = '''<data>
  <xpath expr="//h1" position="after">
    <p t-if="product.x_studio_descripcion" class="anbn-pitch" t-out="product.x_studio_descripcion"/>
  </xpath>
</data>'''
v2 = vista('anbn.product_pitch', 'Anello: descripción persuasiva bajo el nombre', env.ref('website_sale.product_title'), pitch)
# botones: se republica la vista del sitio con la cita dentro de la frase
D = '/opt/odoo/anbn_tmp/'
arch = open(D + 'product_cta.xml').read().replace('/contacto#cita', '/appointment')
cta = V.with_context(active_test=False).search([('key', '=', 'anbn.product_cta'), ('website_id', '=', 1)], limit=1)
for lg in ('en_US', 'es_MX'):
    cta.with_context(lang=lg).write({'arch': arch})
env.cr.commit()
for tb in ('orm_signaling_templates', 'orm_signaling_default'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('OK', v1.id, v2.id, cta.id)
# hoja de estilos (mismo adjunto y vista que aplicar.py)
import base64
Att = env['ir.attachment'].sudo()
V_HOME = 6545
datas = base64.b64encode(open(D + 'anello-bn.css', 'rb').read())
a = Att.search([('name', '=', 'anbn_anello-bn.css'), ('res_model', '=', 'ir.ui.view'), ('res_id', '=', V_HOME)], limit=1)
a.write({'datas': datas, 'mimetype': 'text/css'})
link = V.with_context(active_test=False).search([('key', '=', 'anbn.css_link'), ('website_id', '=', 1)], limit=1)
link.write({'arch': '<data><xpath expr="//head" position="inside"><link rel="stylesheet" href="/web/content/%d/anello-bn.css?unique=%s"/></xpath></data>' % (a.id, a.checksum[:8])})
env.cr.commit(); print('CSS', a.id, a.checksum[:8])
