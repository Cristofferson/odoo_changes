# odoo shell -d <BD> < aplicar.py   — anello.mx estilo Blue Nile (website 1)
# Idempotente. La 1a vez guarda respaldo de vistas y menús en /opt/odoo/anbn_tmp/respaldo_<bd>.json
import base64, json, os, re
from odoo import fields
D = '/opt/odoo/anbn_tmp/'
DB = env.cr.dbname
assert DB in ('testanello', 'novadiam-anello-diamane-xubax'), DB
W = env['website'].browse(1)
assert 'anello' in (W.name or '').lower(), W.name
View = env['ir.ui.view'].sudo().with_context(lang='en_US')
Att = env['ir.attachment'].sudo()
Menu = env['website.menu'].sudo().with_context(lang='en_US')
V_HEADER, V_FOOTER, V_HOME = 4417, 6542, 6545
for vid, key in ((V_HEADER, 'website.template_header_default'), (V_FOOTER, 'theme_anello.footer_custom'), (V_HOME, 'theme_anello.page_inicio')):
    v = View.browse(vid)
    assert v.key == key and v.website_id.id == 1, (vid, v.key, v.website_id.id)

# 1) respaldo (solo la primera vez)
bk = D + 'respaldo_%s.json' % DB
if not os.path.exists(bk):
    data = {'views': {vid: View.browse(vid).arch_db for vid in (V_HEADER, V_FOOTER, V_HOME)},
            'menus': [{'id': m.id, 'name': m.name, 'url': m.url, 'sequence': m.sequence} for m in W.menu_id.child_id]}
    json.dump(data, open(bk, 'w'), ensure_ascii=False, indent=1)
    print('respaldo', bk)

# 2) archivos
def up(fname, mime):
    datas = base64.b64encode(open(D + fname, 'rb').read())
    name = 'anbn_' + fname
    a = Att.search([('name', '=', name), ('res_model', '=', 'ir.ui.view'), ('res_id', '=', V_HOME)], limit=1)
    vals = {'name': name, 'datas': datas, 'mimetype': mime, 'public': True, 'res_model': 'ir.ui.view', 'res_id': V_HOME, 'type': 'binary'}
    if a:
        if a.checksum != Att._compute_checksum(base64.b64decode(datas)):
            a.write(vals)
    else:
        a = Att.create(vals)
    return a
def img_url(fname):
    a = up('img/' + fname, 'image/png' if fname.endswith('.png') else 'image/jpeg')
    return '/web/image/%d/%s?unique=%s' % (a.id, fname, a.checksum[:8])
def fill(xml):
    return re.sub(r'\{\{([^}]+)\}\}', lambda m: img_url(m.group(1)), xml)
css = up('anello-bn.css', 'text/css')

# 3) hoja de estilos en todo el sitio 1
link = View.with_context(active_test=False).search([('key', '=', 'anbn.css_link'), ('website_id', '=', 1)], limit=1)
arch = '<data><xpath expr="//head" position="inside"><link rel="stylesheet" href="/web/content/%d/anello-bn.css?unique=%s"/></xpath></data>' % (css.id, css.checksum[:8])
lvals = {'name': 'Anello estilo Blue Nile (CSS)', 'key': 'anbn.css_link', 'type': 'qweb', 'mode': 'extension',
         'inherit_id': env.ref('website.layout').id, 'website_id': 1, 'priority': 99, 'arch': arch, 'active': True}
if link: link.write(lvals)
else: View.create(lvals)

# 5d) Citas nativas de Odoo (website 1): PRESENCIAL en el Estudio y VIRTUAL (videollamada de Odoo).
#     Atienden Jacqueline (13) y Cristofferson (2), 45 min, 11:00-19:00 diario. Los botones van a /appointment (elige tipo).
AT = env['appointment.type'].sudo().with_context(lang='es_MX', active_test=False)
users = env['res.users'].sudo().browse([13, 2]).exists()
Q = env['appointment.question'].sudo().with_context(lang='es_MX')
COMUN = {'website_id': 1, 'is_published': True, 'active': True, 'schedule_based_on': 'users',
         'staff_user_ids': [(6, 0, users.ids)], 'is_auto_assign': True, 'appointment_duration': 0.75,
         'slot_creation_interval': 0.75, 'appointment_tz': 'America/Mexico_City', 'min_schedule_hours': 2.0,
         'max_schedule_days': 60, 'min_cancellation_hours': 2.0}
TIPOS = [
    ('Cita en el Estudio Anello', 10, {
        'image_1920': base64.b64encode(open(D + 'img/cita-estudio.jpg', 'rb').read()), 'location_id': 13, 'event_videocall_source': False,
        'message_intro': '<p>Visítanos en nuestro Estudio de Morelia, en Plaza Fiesta Camelinas, piso G (Av. Ventura Puente 1843 E16, Col. Electricistas). '
                         'Tu asesor te espera con los anillos listos para probar metal, piedra y medida con calma. Todos los días de 11:00 a 19:00.</p>',
        'message_confirmation': '<p>¡Gracias! Te esperamos en el Estudio Anello. Si necesitas cambiar tu cita, escríbenos por WhatsApp al 443 324 4511.</p>'}),
    ('Cita virtual por videollamada', 20, {
        'image_1920': base64.b64encode(open(D + 'img/bn4-icert.jpg', 'rb').read()), 'location_id': False, 'event_videocall_source': 'discuss',
        'message_intro': '<p>¿No estás en Morelia? Conéctate desde tu casa: tu asesor te muestra los anillos en vivo por videollamada, '
                         'te ayuda a elegir metal, piedra y medida, y resuelve tus dudas. Todos los días de 11:00 a 18:00.</p>',
        'message_confirmation': '<p>¡Gracias! Te enviamos por correo la liga de la videollamada. Si necesitas cambiar tu cita, escríbenos por WhatsApp al 443 324 4511.</p>'}),
]
apts = AT.browse()
FIN = {'Cita virtual por videollamada': 18.0}   # la virtual termina a las 18:00
for nombre, seq, extra in TIPOS:
    apt = AT.search([('website_id', '=', 1), ('name', '=', nombre)], limit=1)
    vals = dict(COMUN, name=nombre, sequence=seq, **extra)
    if apt: apt.write(vals)
    else: apt = AT.create(vals)
    apt.slot_ids.unlink()
    env['appointment.slot'].sudo().create([{'appointment_type_id': apt.id, 'slot_type': 'recurring', 'weekday': str(d),
                                            'start_hour': 11.0, 'end_hour': FIN.get(nombre, 19.0)} for d in range(1, 8)])
    if not apt.question_ids.filtered(lambda q: q.name == '¿Qué te gustaría ver?'):
        Q.create({'appointment_type_ids': [(4, apt.id)], 'name': '¿Qué te gustaría ver?', 'question_type': 'char',
                  'placeholder': 'Ej. anillos de compromiso en oro blanco, argollas…', 'question_required': False})
    apts |= apt
APT_URL = '/appointment'
print('citas', [(x.id, x.name, x.event_videocall_source or 'presencial') for x in apts])

def rd(fname):
    # todos los «Agenda tu cita» del sitio van al calendario nativo de Citas
    return open(D + fname).read().replace('/contacto#cita', APT_URL)

# 4) encabezado, pie y portada
# 🪤 el arch que PINTA es es_MX: se escribe en_US y luego es_MX con el mismo texto (si no, Odoo mezcla frases viejas)
def put(vid, arch):
    View.browse(vid).write({'arch': arch})
    View.with_context(lang='es_MX').browse(vid).write({'arch': arch})
put(V_HEADER, rd('header.xml'))
put(V_FOOTER, rd('footer.xml'))
put(V_HOME, fill(rd('home.xml')))

# 4b) logo del sitio recortado y transparente (original respaldado en ~/backups/anello-website-logo-original-30sep.png)
logo = base64.b64encode(open(D + 'logo-anello-trim.png', 'rb').read())
if W.logo != logo:
    W.write({'logo': logo})

# 5) menú principal
want = [('Anillos de compromiso', '/shop/category/anillos-de-compromiso-18'),
        ('Argollas de boda', '/shop/category/joyeria-de-boda-14'),
        ('Aretes', '/shop/category/aretes-12'),
        ('Joyería', '/shop'),
        ('Diseño a la medida', APT_URL),
        ('Nosotros', '/nosotros'),
        ('Contacto', '/contacto')]
cur = W.menu_id.child_id.sorted('sequence')
for i, (name, url) in enumerate(want):
    vals = {'name': name, 'url': url, 'sequence': (i + 1) * 10, 'parent_id': W.menu_id.id, 'website_id': 1}
    if i < len(cur): cur[i].write(vals)
    else: Menu.create(vals)
for extra in cur[len(want):]:
    extra.unlink()

# 5a) Nosotros (vista 6546): respaldo la 1a vez y arch nuevo estilo Blue Nile
V_NOS = 6546
vn = View.browse(V_NOS)
assert vn.key == 'theme_anello.page_nosotros' and vn.website_id.id == 1, vn.key
bkn = D + 'respaldo_nosotros_%s.xml' % DB
if not os.path.exists(bkn):
    open(bkn, 'w').write(vn.arch_db)
put(V_NOS, fill(rd('page_nosotros.xml')))

# 5c) Contacto (vista 6543, del tema): «showroom» → «Estudio», horario real, mapa real en lugar del letrero de relleno
V_CON = 6543
vc = View.browse(V_CON)
assert vc.key == 'theme_anello.page_contacto' and vc.website_id.id == 1, vc.key
bkc = D + 'respaldo_contacto_%s.xml' % DB
if not os.path.exists(bkc):
    open(bkc, 'w').write(vc.with_context(lang='es_MX').arch_db)
# Coordenadas reales (ficha de Google «Anello Joyería», Plaza Fiesta Camelinas piso G). Antes 19.6546,-101.2624 = Kimberly-Clark.
for pid in (1, 13, 67320):
    pp = env['res.partner'].sudo().browse(pid)
    if pp.exists() and pp.street == 'Av. Ventura Puente 1843 E16':
        pp.write({'partner_latitude': 19.6822551, 'partner_longitude': -101.1804949, 'date_localization': fields.Date.today()})
DIR = 'Anello%20Joyer%C3%ADa%2C%20Plaza%20Fiesta%20Camelinas%2C%20Calz.%20Ventura%20Puente%201843%2C%20Morelia'
MAPA = ('<div style="position:relative;width:100%;height:100%;min-height:340px">'
        '<iframe title="Ubicación del Estudio Anello" src="https://maps.google.com/maps?q=' + DIR + '&amp;z=16&amp;output=embed" '
        'style="border:0;width:100%;height:100%;min-height:340px;display:block" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>'
        '<a href="https://www.google.com/maps/dir/?api=1&amp;destination=' + DIR + '" target="_blank" rel="noopener" '
        'style="position:absolute;left:14px;bottom:14px;background:#14110E;color:#fff;padding:12px 18px;font:500 12px/1 Jost,sans-serif;letter-spacing:.1em;text-transform:uppercase;text-decoration:none">Cómo llegar</a></div>')
import re as _re0
arch_c = _re0.sub(r'/appointment/\d+', APT_URL, vc.with_context(lang='es_MX').arch_db.replace('/contacto#cita', APT_URL))
for old, new in (('reserva una cita privada en el showroom.', 'reserva una cita privada en nuestro Estudio.'),
                 ('margin-bottom:.3rem">Showroom</span>', 'margin-bottom:.3rem">Estudio</span>'),
                 ('Lun a Sáb · 11:00 – 19:00<br/>Dom · 12:00 – 18:00', 'Todos los días · 11:00 – 19:00<br/>WhatsApp · 8:00 – 21:00'),
                 ('<span class="ph__tag">Mapa · ubicación del showroom (Google Maps / Odoo)</span>', MAPA)):
    arch_c = arch_c.replace(old, new)
import re as _re
arch_c = _re.sub(r'<div style="position:relative;width:100%;height:100%;min-height:340px"><iframe title="Ubicación del Estudio Anello".*?Cómo llegar</a></div>', lambda m: MAPA, arch_c, flags=_re.S)
arch_c = _re.sub(r'<iframe title="Ubicación del Estudio Anello" src="https://maps\.google\.com[^>]*?(/>|></iframe>)', lambda m: MAPA, arch_c)
if 'Plaza Fiesta Camelinas' not in arch_c:
    arch_c = arch_c.replace('<p style="margin:0">Av. Ventura Puente 1843 E16, Col. Electricistas<br/>',
                            '<p style="margin:0">Plaza Fiesta Camelinas, piso G<br/>Av. Ventura Puente 1843 E16, Col. Electricistas<br/>', 1)
put(V_CON, arch_c)

# 5b) páginas nuevas: /icert y /grabado-laser
Page = env['website.page'].sudo()
for url, key, fname, title in (('/icert', 'anbn.page_icert', 'page_icert.xml', 'Certificado ICERT'),
                               ('/grabado-laser', 'anbn.page_grabado', 'page_grabado.xml', 'Grabado láser')):
    arch = fill(rd(fname))
    v = View.with_context(active_test=False).search([('key', '=', key), ('website_id', '=', 1)], limit=1)
    if v:
        v.write({'arch': arch}); v.with_context(lang='es_MX').write({'arch': arch})
    else:
        v = View.create({'name': title, 'key': key, 'type': 'qweb', 'arch': arch, 'website_id': 1})
    pg = Page.search([('url', '=', url), ('website_id', '=', 1)], limit=1)
    if not pg:
        Page.create({'url': url, 'view_id': v.id, 'website_id': 1, 'is_published': True, 'name': title, 'website_indexed': True})

# 6) tienda y ficha (solo website 1: las vistas de opción se copian al sitio con website_id en el contexto)
VW = env['ir.ui.view'].sudo().with_context(website_id=1, lang='en_US')
def opt(key, active):
    vs = VW.with_context(active_test=False).search([('key', '=', key), ('website_id', 'in', (1, False))])
    v = vs.filtered(lambda x: x.website_id.id == 1)[:1] or vs[:1]
    if v.active != active:
        v.write({'active': active})
for key, act in (('website_sale.products_attributes', False), ('website_sale.products_attributes_top', True),
                 ('website_sale.search', False),
                 ('website_sale_comparison.product_attributes_body', False)):   # «Especificaciones»: repetía las variantes
    opt(key, act)
item = View.with_context(active_test=False).search([('key', '=', 'anbn.products_item'), ('website_id', '=', 1)], limit=1)
ivals = {'name': 'Anello: metales en la tarjeta', 'key': 'anbn.products_item', 'type': 'qweb', 'mode': 'extension',
         'inherit_id': env.ref('website_sale.products_item').id, 'website_id': 1, 'priority': 99,
         'arch': rd('shop_item.xml'), 'active': True}
if item: item.write(ivals)
else: View.create(ivals)
W.write({'shop_ppr': 4, 'shop_ppg': 24, 'shop_gap': '14px',
         'shop_opt_products_design_classes': 'o_wsale_products_opt_layout_catalog o_wsale_products_opt_design_thumbs o_wsale_products_opt_name_color_regular o_wsale_products_opt_rounded_0 o_wsale_products_opt_thumb_cover o_wsale_products_opt_img_secondary_show o_wsale_products_opt_has_wishlist o_wsale_products_opt_wishlist_fixed o_wsale_products_opt_actions_subtle o_wsale_products_opt_cc1',
         'product_page_image_layout': 'grid', 'product_page_grid_columns': 2, 'product_page_image_spacing': 'small'})
cta = View.with_context(active_test=False).search([('key', '=', 'anbn.product_cta'), ('website_id', '=', 1)], limit=1)
cvals = {'name': 'Anello: botón de asesor en la ficha', 'key': 'anbn.product_cta', 'type': 'qweb', 'mode': 'extension',
         'inherit_id': env.ref('website_sale.cta_wrapper').id, 'website_id': 1, 'priority': 99,
         'arch': rd('product_cta.xml'), 'active': True}
if cta: cta.write(cvals)
else: View.create(cvals)
ic = View.with_context(active_test=False).search([('key', '=', 'anbn.product_icert'), ('website_id', '=', 1)], limit=1)
icv = {'name': 'Anello: ICERT y grabado láser en la ficha', 'key': 'anbn.product_icert', 'type': 'qweb', 'mode': 'extension',
       'inherit_id': env.ref('website_sale.product').id, 'website_id': 1, 'priority': 99,
       'arch': fill(rd('product_icert.xml')), 'active': True}
if ic: ic.write(icv)
else: View.create(icv)
# texto de la ficha: el de fábrica prometía «30 días de devolución» y «envío 2-3 días» (falso); copia solo para el sitio 1
terms = VW.with_context(active_test=False).search([('key', '=', 'website_sale.product_terms_and_conditions'), ('website_id', 'in', (1, False))])
terms = terms.filtered(lambda x: x.website_id.id == 1)[:1] or terms[:1]
terms.write({'arch': rd('product_terms.xml')})
terms.with_context(lang='es_MX').write({'arch': rd('product_terms.xml')})
Cat = env['product.public.category'].sudo()
for cid, desc in ((18, 'Solitarios, trilogías y pavé hechos a mano. Elige el metal, la piedra y la medida.'),
                  (14, 'Argollas lisas, mate, bitono y con piedras, para los dos.'),
                  (12, 'Broqueles y arracadas de oro para todos los días.')):
    c = Cat.browse(cid)
    vals = {'show_category_title': True, 'show_category_description': True}
    if not (c.website_description or '').strip():
        vals['website_description'] = '<p>%s</p>' % desc
    c.with_context(lang='es_MX').write(vals)

env.cr.commit()
print('OK', DB, 'css', css.id, [m.name for m in W.menu_id.child_id.sorted('sequence')])
