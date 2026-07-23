# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class XbSocialAiProvider(models.Model):
    _name = "xb.social.ai.provider"
    _description = "AI Provider Configuration"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company,
    )

    provider_type = fields.Selection(
        [("anthropic", "Anthropic API (Claude — bring your own key)"),
         ("claude_code", "Claude Code CLI (existing subscription, no API key)"),
         ("openai", "OpenAI API (GPT — bring your own key)"),
         ("custom", "Custom (OpenAI-compatible endpoint)")],
        string="Provider", required=True, default="anthropic",
        help="Selects the transport implementation used to call the model.\n"
             "• Anthropic API / OpenAI API: pay-per-use, needs an API key.\n"
             "• Claude Code CLI: reuses a Claude Code / Max subscription already "
             "installed on the server (no API key, no per-call billing).\n"
             "• Custom: any endpoint that speaks the OpenAI chat API.",
    )
    text_model = fields.Char(
        string="Text Model", default="claude-opus-4-8",
        help="Model id used for strategy and copy generation.",
    )
    effort = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        string="Effort", default="high",
        help="Reasoning/output effort. Higher = better quality, more tokens.",
    )
    max_tokens = fields.Integer(string="Max Tokens", default=8000)
    timeout = fields.Integer(string="Timeout (s)", default=120)
    api_base_url = fields.Char(
        string="API Base URL",
        help="Override the provider endpoint (self-hosted / proxy). "
             "Leave empty for the provider default.",
    )

    # --- Claude Code CLI backend (provider_type == 'claude_code') -----------
    cli_binary = fields.Char(
        string="CLI Binary",
        default="claude",
        help="Path to the Claude Code executable runnable by the Odoo service "
             "user (e.g. /usr/local/bin/claude). 'claude' resolves it on PATH.",
    )
    cli_config_dir = fields.Char(
        string="CLI Config Dir",
        help="Optional value for CLAUDE_CONFIG_DIR — the directory holding the "
             "CLI's auth/credentials, readable by the Odoo service user. "
             "Leave empty to use the service user's default (~/.claude).",
    )

    # ----- media generation (image now / video later) -----------------------
    image_provider_type = fields.Selection(
        [("svg", "Vector design by the text model (no image key, no extra cost)"),
         ("openai_images", "OpenAI Images (photoreal — bring your own key)"),
         ("gemini_images", "Google Gemini (photoreal — bring your own key)"),
         ("custom", "Custom (OpenAI-compatible endpoint)"),
         ("none", "Disabled (manual upload)")],
        string="Image Provider", required=True, default="svg",
        help="How post images are produced.\n"
             "• Vector design: the text model draws an on-brand graphic that "
             "is rasterised locally. No image API key and no per-image "
             "billing, but it is graphic design, not photography.\n"
             "• OpenAI / Gemini: real photoreal image models. Needs an image "
             "API key and is billed per image by the provider.",
    )
    image_model = fields.Char(
        string="Image Model",
        help="Image model id, e.g. 'gpt-image-1' or 'gemini-3-pro-image'. "
             "Leave empty for the provider default.",
    )
    image_api_base_url = fields.Char(
        string="Image API Base URL",
        help="Override the image endpoint (gateway / self-hosted). Required "
             "for the custom provider; leave empty otherwise.",
    )
    image_format = fields.Selection(
        [("square", "Square 1080×1080"),
         ("portrait", "Portrait 1080×1350"),
         ("landscape", "Landscape 1200×675")],
        string="Image Format", default="square",
        help="Aspect ratio of generated images. Square is the safest across "
             "Facebook, Instagram, LinkedIn and X.",
    )
    image_style = fields.Selection(
        [("photo", "Photograph"),
         ("product", "Studio product shot"),
         ("lifestyle", "Lifestyle / people"),
         ("illustration", "Illustration"),
         ("flat", "Flat graphic")],
        string="Image Style", default="photo",
        help="Art direction sent to photoreal image models. Ignored by the "
             "vector backend, which follows the brand kit instead.",
    )
    image_quality = fields.Selection(
        [("auto", "Automatic"), ("low", "Low"), ("medium", "Medium"),
         ("high", "High")],
        string="Image Quality", default="auto",
        help="Higher quality costs more per image at the provider.",
    )
    image_count = fields.Integer(
        string="Variants per Post", default=1,
        help="How many images to generate per post so an editor can pick. "
             "Each variant is billed separately by the image provider.",
    )
    image_prompt_boost = fields.Boolean(
        string="Enrich Image Prompt", default=True,
        help="Let the text model rewrite the brief into a richer prompt "
             "before calling the image model. Costs one extra (cheap) text "
             "call and noticeably improves photoreal results.",
    )
    image_timeout = fields.Integer(
        string="Image Timeout (s)", default=180,
        help="Photoreal generation is slower than text; keep this generous.",
    )

    @api.onchange("provider_type")
    def _onchange_provider_type(self):
        """Suggest that provider's flagship text model when switching backend."""
        defaults = {
            "anthropic": "claude-opus-4-8",
            "claude_code": "claude-opus-4-8",
            "openai": "gpt-4.1",
        }
        for provider in self:
            suggested = defaults.get(provider.provider_type)
            if suggested and provider.text_model in (False, "", *defaults.values()):
                provider.text_model = suggested

    @api.onchange("image_provider_type")
    def _onchange_image_provider_type(self):
        """Suggest a sensible model id when switching image backend."""
        defaults = {
            "openai_images": "gpt-image-1",
            "gemini_images": "gemini-3-pro-image",
        }
        for provider in self:
            suggested = defaults.get(provider.image_provider_type)
            if suggested and provider.image_model in (
                    False, "", *defaults.values()):
                provider.image_model = suggested
            elif provider.image_provider_type in ("svg", "none"):
                provider.image_model = False

    @api.constrains("image_count")
    def _check_image_count(self):
        for provider in self:
            if provider.image_count < 1 or provider.image_count > 4:
                raise ValidationError(
                    _("Variants per Post must be between 1 and 4."))
