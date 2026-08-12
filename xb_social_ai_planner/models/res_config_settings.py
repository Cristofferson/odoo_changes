# -*- coding: utf-8 -*-
from odoo import api, fields, models


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
        string="AI Engine", readonly=False,
    )

    # The three choices that actually matter, surfaced here so the engine is
    # configured in one screen instead of "key in Settings, model somewhere
    # else". The full record stays one click away for anything advanced.
    xb_social_ai_text_engine = fields.Selection(
        related="xb_social_ai_default_provider_id.provider_type",
        string="Text Engine", readonly=False,
    )
    xb_social_ai_text_model = fields.Char(
        related="xb_social_ai_default_provider_id.text_model",
        string="Text Model", readonly=False,
    )
    xb_social_ai_image_engine = fields.Selection(
        related="xb_social_ai_default_provider_id.image_provider_type",
        string="Image Engine", readonly=False,
    )
    xb_social_ai_image_model = fields.Char(
        related="xb_social_ai_default_provider_id.image_model",
        string="Image Model", readonly=False,
    )
    xb_social_ai_image_quality = fields.Selection(
        related="xb_social_ai_default_provider_id.image_quality",
        string="Image Quality", readonly=False,
    )

    @api.model
    def default_get(self, fields_list):
        """Adopt an engine when the company has not picked one.

        Every install ships a provider record, but nothing ever pointed the
        company at it — so this screen opened with the engine fields blank and
        nothing to edit. Done on open rather than on save: the related fields
        below have to resolve *before* the form loads, otherwise saving would
        write their empty values back onto the engine."""
        company = self.env.company
        if not company.xb_social_ai_default_provider_id:
            provider = self.env["xb.social.ai.provider"].search(
                [("company_id", "in", (company.id, False))], limit=1)
            if provider:
                company.sudo().xb_social_ai_default_provider_id = provider
        return super().default_get(fields_list)

    def action_open_ai_engine(self):
        """Open the engine record itself, for the settings this screen hides."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "xb_social_ai_planner.action_xb_social_ai_provider")
        if self.xb_social_ai_default_provider_id:
            action["views"] = [(False, "form")]
            action["res_id"] = self.xb_social_ai_default_provider_id.id
        return action
