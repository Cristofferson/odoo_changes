# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """«factor_acento» (3.26, solo acentos) pasa a «factor_lab» (3.88, todos los
    diamantes de laboratorio, también dentro de las joyas) y se recalculan."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["ir.config_parameter"].search([("key", "=", "xb_gema_precio_rapaport.factor_acento")]).unlink()
    env["ir.model.data"].search([("module", "=", "xb_gema_precio_rapaport"), ("name", "=", "param_factor_acento")]).unlink()
    lab = env["product.template"].with_context(active_test=False).search([("xb_costo_lab_quilate", "=", True)])
    lab._xb_aplicar_costo_lab()
