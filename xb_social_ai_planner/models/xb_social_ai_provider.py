# -*- coding: utf-8 -*-
from odoo import fields, models


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
         ("openai", "OpenAI"),
         ("custom", "Custom")],
        string="Provider", required=True, default="anthropic",
        help="Selects the transport implementation used to call the model.\n"
             "• Anthropic API: pay-per-use, needs an API key.\n"
             "• Claude Code CLI: reuses a Claude Code / Max subscription already "
             "installed on the server (no API key, no per-call billing).",
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

    # Media generation (image now / video later) — separate provider.
    image_provider_type = fields.Selection(
        [("none", "None (manual upload)"),
         ("openai_images", "OpenAI Images"),
         ("custom", "Custom")],
        string="Image Provider", default="none",
    )
    image_model = fields.Char(string="Image Model")
