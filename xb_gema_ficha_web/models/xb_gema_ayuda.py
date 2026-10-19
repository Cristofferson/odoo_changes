# -*- coding: utf-8 -*-
from odoo import fields, models


class XbGemaAyuda(models.Model):
    """Qué significa cada casilla de la ficha de gema en la tienda (el botón
    «ⓘ»). La clave la usa la plantilla; nombre y explicación los edita el
    usuario desde Sitio web › Configuración."""
    _name = "xb.gema.ayuda"
    _description = "Gem product page: field explanation"
    _order = "sequence, id"
    _rec_name = "name"

    clave = fields.Char(required=True, readonly=True, index=True)
    name = fields.Char("Casilla", required=True, translate=True)
    explicacion = fields.Text("Qué significa", translate=True,
                              help="Lo que lee el cliente al tocar «ⓘ». Vacío = sin botón.")
    sequence = fields.Integer(default=10)

    _clave_unica = models.Constraint("unique(clave)", "Cada casilla solo puede tener una explicación.")
