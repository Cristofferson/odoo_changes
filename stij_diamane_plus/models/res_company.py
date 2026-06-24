# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    dmn_theft_mode = fields.Selection(
        [
            ("deterrent", "Disuasivo (avisa al visitante)"),
            ("decoy", "Señuelo (muestra el visor normal y captura en silencio)"),
        ],
        string="Modo trampa de robo",
        default="deterrent",
    )
    dmn_theft_alert_email = fields.Boolean(
        string="Alertar por correo al avistar pieza robada", default=True,
    )
    dmn_theft_alert_extra_emails = fields.Char(
        string="Correos extra para alertas de robo",
        help="Separados por coma. Se suman al dueño y al correo de la compañía.",
    )
    dmn_theft_alert_throttle_minutes = fields.Integer(
        string="Minutos entre alertas de robo por pieza", default=15,
    )
    dmn_view_dedup_minutes = fields.Integer(
        string="Minutos para no recontar una vista (misma sesión)", default=30,
    )
    dmn_warranty_months = fields.Integer(
        string="Meses de garantía", default=12,
        help="Vigencia de garantía a partir de la fecha de compra de la pieza.",
    )
