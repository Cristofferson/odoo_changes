# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    xb_social_ai_api_key = fields.Char(
        related="company_id.xb_social_ai_api_key",
        string="AI Text API Key", readonly=False,
    )
    xb_social_ai_image_api_key = fields.Char(
        related="company_id.xb_social_ai_image_api_key",
        string="AI Image API Key", readonly=False,
    )
    xb_social_ai_default_provider_id = fields.Many2one(
        related="company_id.xb_social_ai_default_provider_id",
        string="Default AI Provider", readonly=False,
    )
