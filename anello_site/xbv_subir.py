# odoo shell < xbv_subir.py — sube xbv.js / xbv.css (selector de variantes) y actualiza la vista xbv.propuesta_b. 🚨 con mimetype.
import base64
Att = env['ir.attachment'].sudo(); V = env['ir.ui.view']
D = '/opt/odoo/anbn_tmp/'
js = Att.browse(31277); css = Att.browse(31276)
js.write({'datas': base64.b64encode(open(D + 'xbv.js', 'rb').read()), 'mimetype': 'text/javascript'})
css.write({'datas': base64.b64encode(open(D + 'xbv.css', 'rb').read()), 'mimetype': 'text/css'})
v = V.search([('key', '=', 'xbv.propuesta_b')], limit=1)
arch = ('<data><xpath expr="//div[@id=\'o_wsale_product_details_content\']" position="inside">\n'
        '<link rel="stylesheet" href="/web/content/%d?unique=%s"/><script src="/web/content/%d?unique=%s" data-mode="B"/></xpath></data>'
        % (css.id, css.checksum[:8], js.id, js.checksum[:8]))
for lg in ('en_US', 'es_MX'):
    v.with_context(lang=lg).write({'arch': arch})
env.cr.commit()
for tb in ('orm_signaling_templates', 'orm_signaling_default'):
    env.cr.execute("INSERT INTO %s DEFAULT VALUES" % tb)
env.cr.commit(); print('OK', js.mimetype, js.checksum[:8], css.mimetype, css.checksum[:8])
