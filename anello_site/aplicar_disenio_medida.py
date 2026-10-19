# Página /diseno-a-la-medida en anello.mx (propuesta A) y menú «Diseño a la medida» (id 62) apuntando a ella.
import base64, re
D = '/tmp/xb_dm/'
View = env['ir.ui.view'].sudo(); Att = env['ir.attachment'].sudo(); Page = env['website.page'].sudo()
KEY, URL, TITLE = 'anbn.page_disenio_medida', '/diseno-a-la-medida', 'Diseño a la medida'
v = View.with_context(active_test=False).search([('key', '=', KEY), ('website_id', '=', 1)], limit=1)
if not v:
    v = View.create({'name': TITLE, 'key': KEY, 'type': 'qweb', 'arch': '<t t-name="%s"><t t-call="website.layout"/></t>' % KEY, 'website_id': 1})


def img_url(fname):
    datas = base64.b64encode(open(D + fname, 'rb').read())
    name = 'anbn_dm_' + fname
    a = Att.search([('name', '=', name), ('res_model', '=', 'ir.ui.view'), ('res_id', '=', v.id)], limit=1)
    vals = {'name': name, 'datas': datas, 'mimetype': 'image/jpeg', 'public': True, 'res_model': 'ir.ui.view', 'res_id': v.id, 'type': 'binary'}
    if a:
        a.write(vals)
    else:
        a = Att.create(vals)
    return '/web/image/%d/%s?unique=%s' % (a.id, fname, a.checksum[:8])


arch = re.sub(r'\{\{([^}]+)\}\}', lambda m: img_url(m.group(1)), open(D + 'page_disenio_medida.xml').read())
# 🪤 el arch que PINTA es es_MX: se escribe en ambos idiomas
v.write({'arch': arch})
v.with_context(lang='es_MX').write({'arch': arch})
pg = Page.search([('url', '=', URL), ('website_id', '=', 1)], limit=1)
if not pg:
    pg = Page.create({'url': URL, 'view_id': v.id, 'website_id': 1, 'is_published': True, 'name': TITLE, 'website_indexed': True})
m = env['website.menu'].sudo().browse(62)
print('menú antes:', m.name, m.url)
m.write({'url': URL})
env.cr.commit()
# los workers vivos no se enteran de vistas cambiadas desde un shell: avisarles
env.cr.execute("INSERT INTO orm_signaling_templates DEFAULT VALUES")
env.cr.execute("INSERT INTO orm_signaling_default DEFAULT VALUES")
env.cr.commit()
print('LISTO · vista', v.id, '| página', pg.url, '| menú ahora', m.url)
