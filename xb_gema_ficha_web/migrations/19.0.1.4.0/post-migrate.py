# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api
from odoo.addons.xb_gema_ficha_web import crear_menu_diamantes


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["product.template"].with_context(active_test=False).search(
        [("categ_id", "=", 71)])._xb_sync_categoria_diamantes()
    crear_menu_diamantes(env)
