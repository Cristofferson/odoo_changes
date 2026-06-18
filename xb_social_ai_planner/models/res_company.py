# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    xb_social_ai_api_key = fields.Char(
        string="AI Text API Key",
        groups="base.group_system",
        help="Bring-your-own-key for the text/strategy provider (e.g. Claude). "
             "Stored per company; never displayed to non-admins.",
    )
    xb_social_ai_image_api_key = fields.Char(
        string="AI Image API Key",
        groups="base.group_system",
        help="API key for the image-generation provider (optional).",
    )
    xb_social_ai_default_provider_id = fields.Many2one(
        "xb.social.ai.provider", string="Default AI Provider",
    )
