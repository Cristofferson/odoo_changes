# -*- coding: utf-8 -*-
from . import controllers
from . import models

OLD_VIEW_KEY = "xb_gemas.ficha_gema_producto"


def post_init_hook(env):
    # La vista vieja (creada a mano, sin xmlid) pintaría las tablas DOS veces.
    env["ir.ui.view"].with_context(active_test=False).search(
        [("key", "=", OLD_VIEW_KEY)]).write({"active": False})
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
