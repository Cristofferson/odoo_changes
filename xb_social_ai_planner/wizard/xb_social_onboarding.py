# -*- coding: utf-8 -*-
"""The 'Start Here' screen.

The planner has four moving parts that have to exist before the first plan can
be generated — a connected social account, an AI engine, a key for it, and a
brand profile — and until now the only way to discover a missing one was to hit
the error it raises. This screen states the four out loud, says which are done,
and gives each one the button that fixes it.
"""
from odoo import api, fields, models

# Engines that talk to a paid HTTP API and therefore need a key. The Claude
# Code CLI reuses a subscription already on the server, so it needs none.
_KEYED_PROVIDERS = ("anthropic", "openai", "custom")

DEFAULT_HELP_URL = "https://www.xubax.com/apps/xb-social-ai-planner"


class XbSocialOnboarding(models.TransientModel):
    _name = "xb.social.onboarding"
    _description = "AI Social Planner — Start Here"

    # Whole sentences are computed here rather than assembled in the view.
    # Interleaving <field> with text splits each line into several translatable
    # fragments, which are then impossible to translate well.

    # ----- step 1: a connected social account -------------------------------
    account_count = fields.Integer(compute="_compute_status")
    has_accounts = fields.Boolean(compute="_compute_status")
    accounts_status = fields.Char(compute="_compute_status")

    # ----- step 2: an AI engine, with a key if it needs one ------------------
    provider_id = fields.Many2one(
        "xb.social.ai.provider", compute="_compute_status")
    has_engine = fields.Boolean(compute="_compute_status")
    engine_label = fields.Char(compute="_compute_status")
    needs_key = fields.Boolean(
        compute="_compute_status",
        help="True when the chosen engine bills through an API key and none "
             "is configured yet.")
    image_engine_label = fields.Char(compute="_compute_status")
    engine_status = fields.Char(compute="_compute_status")
    key_status = fields.Char(compute="_compute_status")

    # ----- step 3: a brand profile the AI can actually read ------------------
    brand_id = fields.Many2one(
        "xb.social.brand.profile", compute="_compute_status")
    brand_count = fields.Integer(compute="_compute_status")
    has_brand = fields.Boolean(compute="_compute_status")
    brand_completeness = fields.Integer(compute="_compute_status")
    brand_missing = fields.Char(compute="_compute_status")
    brand_status = fields.Char(compute="_compute_status")

    # ----- step 4: the plans themselves --------------------------------------
    plan_count = fields.Integer(compute="_compute_status")
    plan_status = fields.Char(compute="_compute_status")
    ready = fields.Boolean(
        compute="_compute_status",
        help="Everything the first generation needs is in place.")
    help_url = fields.Char(compute="_compute_status")

    @api.depends_context("company")
    def _compute_status(self):
        company = self.env.company
        Provider = self.env["xb.social.ai.provider"]
        Brand = self.env["xb.social.brand.profile"]

        accounts = self.env["social.account"].search_count([])
        provider = (
            company.xb_social_ai_default_provider_id
            or Provider.search(
                [("company_id", "in", (company.id, False))], limit=1)
        )
        # The key is a system-only field: read it privileged, expose only
        # whether it is there. Its value never reaches this screen.
        key_set = bool(company.sudo().xb_social_ai_api_key)
        # Completeness is computed, not stored, so the "best" brand has to be
        # picked in Python rather than ordered by the database.
        brand_rs = Brand.search([])
        brand = max(brand_rs, key=lambda b: b.completeness, default=Brand)
        brands = len(brand_rs)
        plans = self.env["xb.social.content.plan"].search_count([])
        help_url = self.env["ir.config_parameter"].sudo().get_param(
            "xb_social_ai_planner.help_url", DEFAULT_HELP_URL)

        provider_types = dict(Provider._fields["provider_type"].selection)
        image_types = dict(Provider._fields["image_provider_type"].selection)

        for wiz in self:
            wiz.account_count = accounts
            wiz.has_accounts = bool(accounts)
            wiz.accounts_status = self.env._(
                "%s account(s) ready to publish to.") % accounts

            wiz.provider_id = provider
            wiz.has_engine = bool(provider)
            wiz.engine_label = provider and "%s — %s" % (
                provider_types.get(provider.provider_type,
                                   provider.provider_type),
                provider.text_model or "default model",
            ) or ""
            wiz.image_engine_label = provider and image_types.get(
                provider.image_provider_type, provider.image_provider_type) or ""
            wiz.engine_status = self.env._(
                "Copy: %(text)s · Images: %(image)s",
                text=wiz.engine_label, image=wiz.image_engine_label,
            ) if provider else ""
            wiz.needs_key = bool(
                provider and provider.provider_type in _KEYED_PROVIDERS
                and not key_set)
            wiz.key_status = self.env._(
                "%s bills through an API key, and none is set yet. You bring "
                "your own: it is stored per company and never leaves this "
                "database.", wiz.engine_label,
            ) if wiz.needs_key else ""

            wiz.brand_id = brand
            wiz.brand_count = brands
            wiz.has_brand = bool(brands)
            wiz.brand_completeness = brand.completeness if brand else 0
            wiz.brand_missing = brand.completeness_missing if brand else ""
            if brand and brand.completeness < 100:
                wiz.brand_status = self.env._(
                    "%(name)s — filled in %(percent)s%%. Still missing: "
                    "%(missing)s. The thinner it is, the more generic the copy.",
                    name=brand.display_name,
                    percent=brand.completeness,
                    missing=brand.completeness_missing,
                )
            else:
                wiz.brand_status = brand.display_name if brand else ""

            wiz.plan_count = plans
            wiz.plan_status = self.env._(
                "You already have %s plan(s).") % plans if plans else ""
            wiz.ready = bool(
                accounts and provider and not wiz.needs_key and brands)
            wiz.help_url = help_url

    # ----- the button of each step ------------------------------------------
    def _act(self, xml_id, **overrides):
        action = self.env["ir.actions.act_window"]._for_xml_id(xml_id)
        action.update(overrides)
        return action

    def action_open_accounts(self):
        return self._act("social.action_social_account")

    def action_open_settings(self):
        return self._act("xb_social_ai_planner.action_xb_social_settings")

    def action_open_engine(self):
        return self._act("xb_social_ai_planner.action_xb_social_ai_provider")

    def action_open_brands(self):
        return self._act("xb_social_ai_planner.action_xb_social_brand_profile")

    def action_new_brand(self):
        action = self._act(
            "xb_social_ai_planner.action_xb_social_brand_profile")
        action["views"] = [(False, "form")]
        action["res_id"] = False
        return action

    def action_open_brand(self):
        self.ensure_one()
        action = self._act(
            "xb_social_ai_planner.action_xb_social_brand_profile")
        action["views"] = [(False, "form")]
        action["res_id"] = self.brand_id.id
        return action

    def action_generate_month(self):
        action = self._act(
            "xb_social_ai_planner.action_xb_social_generate_month_wizard")
        if self.brand_id:
            action["context"] = dict(
                self.env.context, default_brand_profile_id=self.brand_id.id)
        return action

    def action_open_plans(self):
        return self._act("xb_social_ai_planner.action_xb_social_content_plan")

    def action_open_grid(self):
        return self._act("xb_social_ai_planner.action_xb_social_plan_item")

    def action_open_help(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": self.help_url,
                "target": "new"}
