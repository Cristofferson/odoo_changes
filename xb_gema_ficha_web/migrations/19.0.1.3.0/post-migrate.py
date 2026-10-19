# -*- coding: utf-8 -*-
from odoo.addons.xb_gema_ficha_web import copiar_ayudas_a_es_mx


def migrate(cr, version):
    copiar_ayudas_a_es_mx(cr)
