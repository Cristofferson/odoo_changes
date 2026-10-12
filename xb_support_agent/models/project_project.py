# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"

    xb_support_active = fields.Boolean(
        "Soporte por WhatsApp activo",
        help="El agente reconoce a los usuarios de este sistema por el teléfono de su ficha de usuario.")
    xb_support_contact_ids = fields.One2many(
        "xb.support.contact", "project_id", string="Números autorizados")
