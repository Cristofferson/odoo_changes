# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    self_service_enabled = fields.Boolean(
        related='website_id.self_service_enabled', readonly=False)
    self_service_appointment_url = fields.Char(
        related='website_id.self_service_appointment_url', readonly=False)
    self_service_team_id = fields.Many2one(
        related='website_id.self_service_team_id', readonly=False)
