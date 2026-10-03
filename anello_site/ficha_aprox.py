# odoo shell < ficha_aprox.py — «Ficha de la pieza»: leyenda de peso/precio aproximados junto al peso + ancho de la banda. 3-oct. Idempotente.
V = env['ir.ui.view']
padre = env.ref('stij_website.dmn_ficha_tecnica')
arch = '''<data>
  <xpath expr="//span[@id='dmn_fino']/.." position="after">
    <span class="text-muted fst-italic"> · aproximado</span>
  </xpath>
  <xpath expr="//li[span[@id='dmn_peso']]" position="after">
    <li t-if="product.x_studio_ancho_joya" class="mb-1"><strong>Ancho de la banda:</strong> <span t-out="product.x_studio_ancho_joya"/> mm aprox.</li>
  </xpath>
  <xpath expr="//div[hasclass('form-text')]" position="replace">
    <div class="form-text">Peso y precio aproximados: cambian con el metal y la medida que elijas, y el peso exacto se conoce al terminar la pieza en el taller.</div>
  </xpath>
</data>'''
v = V.search([('key', '=', 'anbn.ficha_aprox')], limit=1)
vals = {'name': 'Anello: ficha con peso aproximado y ancho', 'key': 'anbn.ficha_aprox', 'type': 'qweb', 'mode': 'extension',
        'inherit_id': padre.id, 'priority': 30, 'active': True}
if not v:
    v = V.create(dict(vals, arch=arch))
for lg in ('en_US', 'es_MX'):
    v.with_context(lang=lg).write(dict(vals, arch=arch))
env.cr.commit()
for tb in ('orm_signaling_templates', 'orm_signaling_default'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('OK vista', v.id)
