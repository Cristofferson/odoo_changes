# -*- coding: utf-8 -*-
from . import controllers
from . import models

OLD_VIEW_KEY = "xb_gemas.ficha_gema_producto"


def copiar_ayudas_a_es_mx(cr):
    """Los textos de xb.gema.ayuda se cargan en en_US (idioma de la carga de
    datos). Se copian a es_MX donde falte, para que al editarlos desde Odoo
    en español se cambie lo mismo que ve la tienda."""
    for campo in ("name", "explicacion"):
        cr.execute(f"""
            UPDATE xb_gema_ayuda
               SET {campo} = {campo} || jsonb_build_object('es_MX', {campo}->'en_US')
             WHERE {campo} ? 'en_US' AND NOT {campo} ? 'es_MX'
        """)


def crear_menu_diamantes(env):
    """Menú «Diamantes» de anello.mx, justo después de «Anillos de compromiso»
    (secuencia 10). Si ya existe uno que lleve a la categoría, no hace nada."""
    categ = env.ref("xb_gema_ficha_web.categ_diamantes", raise_if_not_found=False)
    if not categ:
        return
    website = categ.website_id or env.ref("website.default_website")
    Menu = env["website.menu"].sudo()
    url = "/shop/category/%s" % env["ir.http"]._slug(categ)
    if Menu.search([("website_id", "=", website.id), ("url", "like", "/shop/category/%%-%d" % categ.id)], limit=1):
        return
    Menu.create({"name": "Diamantes", "url": url, "website_id": website.id,
                 "parent_id": website.menu_id.id, "sequence": 15})


def post_init_hook(env):
    # La vista vieja (creada a mano, sin xmlid) pintaría las tablas DOS veces.
    env["ir.ui.view"].with_context(active_test=False).search(
        [("key", "=", OLD_VIEW_KEY)]).write({"active": False})
    copiar_ayudas_a_es_mx(env.cr)
    env["product.template"].with_context(active_test=False).search(
        [("categ_id", "=", 71)])._xb_sync_categoria_diamantes()
    crear_menu_diamantes(env)
    gemas = env["product.template"].with_context(active_test=False).search(
        [("categ_id", "=", 71)])
    # De 20 en 20 soltando la caché: las fotos de 350 gemas no caben juntas.
    for i in range(0, len(gemas), 20):
        gemas[i:i + 20]._xb_sync_gema_galeria()
        env.flush_all()
        env.invalidate_all()


def uninstall_hook(env):
    env["ir.ui.view"].with_context(active_test=False).search(
        [("key", "=", OLD_VIEW_KEY)]).write({"active": True})
    env["product.image"].search([("xb_gema_field", "!=", False)]).unlink()
