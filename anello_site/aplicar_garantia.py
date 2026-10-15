# odoo shell -d <BD> < aplicar_garantia.py  — página /garantia + correcciones (website 1, Anello). Idempotente.
import re
DB = env.cr.dbname
assert DB in ("testanello", "novadiam-anello-diamane-xubax"), DB
D = "/home/ubuntu/xbsa_work/web/"
View = env["ir.ui.view"].sudo()
def rd(f): return open(D + f, encoding="utf-8").read()
def vista(key):
    v = View.with_context(active_test=False).search([("key", "=", key), ("website_id", "=", 1)], limit=1)
    return v
def editar(v, f):
    if not v: return "no existe (se omite)"
    """Aplica f(arch)->arch al arch es_MX (el que pinta) y al en_US; devuelve si cambió algo."""
    cambio = False
    for lang in ("es_MX", "en_US"):
        a = v.with_context(lang=lang).arch_db
        n = f(a)
        if n != a:
            v.with_context(lang=lang).write({"arch_db": n}); cambio = True
    return cambio

# 1) página nueva /garantia
arch = rd("garantia.xml")
g = View.with_context(active_test=False).search([("key", "=", "anbn.page_garantia"), ("website_id", "=", 1)], limit=1)
if g:
    g.with_context(lang="en_US").write({"arch": arch}); g.with_context(lang="es_MX").write({"arch": arch})
else:
    g = View.create({"name": "Garantía y compra segura", "key": "anbn.page_garantia", "type": "qweb", "arch": arch, "website_id": 1})
    g.with_context(lang="es_MX").write({"arch": arch})
Page = env["website.page"].sudo()
if not Page.search([("url", "=", "/garantia"), ("website_id", "=", 1)], limit=1):
    Page.create({"url": "/garantia", "view_id": g.id, "website_id": 1, "is_published": True, "name": "Garantía y compra segura", "website_indexed": True})
print("OK página /garantia", g.id)

# 2) pie: enlace junto a «Envíos y devoluciones»
def pie(a):
    if 'href="/garantia"' in a: return a
    a = a.replace('<li><a href="/envios-y-devoluciones">Envíos y devoluciones</a></li>',
                  '<li><a href="/envios-y-devoluciones">Envíos y devoluciones</a></li>\n          <li><a href="/garantia">Garantía y compra segura</a></li>', 1)
    return a.replace('<a href="/envios-y-devoluciones">Envíos y devoluciones</a>\n      </nav>',
                     '<a href="/envios-y-devoluciones">Envíos y devoluciones</a>\n        <a href="/garantia">Garantía</a>\n      </nav>', 1)
print("OK pie", editar(vista("theme_anello.footer_custom"), pie))

# 3) Envíos y devoluciones, punto 8
def envios(a):
    nuevo = ('<p>Tu pieza tiene <strong>garantía de por vida</strong> contra defectos del metal y de la piedra que compraste. '
             'No cubre el desgaste normal ni los daños por golpes, y no depende del plazo de devolución. '
             'Conoce todo en <a href="/garantia">Garantía y compra segura</a>.</p>')
    return re.sub(r'<p>Los defectos de fabricación están cubiertos.*?</p>', nuevo, a, count=1, flags=re.S)
print("OK envíos", editar(vista("website.envios-y-devoluciones"), envios))

# 4) Contacto: primer ajuste gratis durante un año
def contacto(a):
    return re.sub(r'El primer ajuste de talla es gratuito dentro de los 30 días posteriores a la entrega\.',
                  'El primer ajuste de talla es gratuito durante el primer año después de la entrega.', a)
print("OK contacto", editar(vista("theme_anello.page_contacto"), contacto))

# 5) Nosotros: franja «Por qué Anello» antes de ab-dif
franja = rd("nosotros_franja.xml")
def nosotros(a):
    if 'id="por-que-anello"' in a: return a
    assert '<section class="ab-dif">' in a
    return a.replace('<section class="ab-dif">', franja + '<section class="ab-dif">', 1)
print("OK nosotros", editar(vista("theme_anello.page_nosotros"), nosotros))
env.cr.commit()
