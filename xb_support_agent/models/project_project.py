# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    xb_support_active = fields.Boolean(
        "Soporte por WhatsApp activo",
        help="El agente reconoce a los usuarios de este sistema por el teléfono de su ficha de usuario.")
    xb_sa_store = fields.Boolean(
        "Sistema de la tienda (agente de tienda)",
        help="Es el propio Odoo de la tienda: solo lo atiende el agente de TIENDA (a su equipo, sin costo) y el agente de soporte "
             "de XUBAX lo ignora. Los servicios en este sistema no se cobran.")
    xb_support_contact_ids = fields.One2many(
        "xb.support.contact", "project_id", string="Números autorizados")
