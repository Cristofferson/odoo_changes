# -*- coding: utf-8 -*-
from odoo import api, fields, models


class XbSocialBrandProfile(models.Model):
    _name = "xb.social.brand.profile"
    _description = "Social Brand Profile"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company,
    )

    industry = fields.Char(
        string="Industry",
        help="Drives the AI-inferred seasonal/industry trends and hashtags.",
    )
    brand_voice = fields.Text(string="Brand Voice / Tone")
    target_audience = fields.Text(string="Target Audience")
    value_proposition = fields.Text(string="Value Proposition")
    keywords = fields.Text(
        string="Always-on Keywords",
        help="Themes/keywords to weave into the content.",
    )
    banned_words = fields.Text(string="Words to Avoid")
    cta_style = fields.Text(string="Preferred CTA Style")

    default_language = fields.Many2one(
        "res.lang", string="Output Language",
        help="Language the AI writes the copy in. Defaults to the user's "
             "language when empty.",
    )
    emoji_policy = fields.Selection(
        [("none", "No emojis"), ("light", "Light"), ("heavy", "Lots of emojis")],
        string="Emoji Policy", default="light",
    )
    hashtag_policy = fields.Selection(
        [("none", "No hashtags"),
         ("few", "Few (3-5)"),
         ("many", "Many (8-12)")],
        string="Hashtag Policy", default="few",
    )

    # ----- visual brand kit (drives AI image generation) -------------------
    logo = fields.Image(
        string="Logo", max_width=512, max_height=512,
        help="Optional. Embedded into AI-generated post images.",
    )
    palette_primary = fields.Char(
        string="Primary Color", default="#1A1A2E",
        help="Hex color (e.g. #1A1A2E) used as the dominant background.",
    )
    palette_secondary = fields.Char(
        string="Secondary Color", default="#E94560",
        help="Hex color used for accents and shapes.",
    )
    palette_accent = fields.Char(
        string="Text / Accent Color", default="#FFFFFF",
        help="Hex color used for headline text on the image.",
    )
    font_hint = fields.Char(
        string="Typography Hint",
        help="Free text describing the desired type style "
             "(e.g. 'elegant serif', 'bold modern sans').",
    )
    visual_style = fields.Text(
        string="Visual Style",
        help="Art-direction notes for AI images: mood, composition, motifs, "
             "what to avoid.",
    )

    default_utm_campaign_id = fields.Many2one(
        "utm.campaign", string="Default Campaign",
        domain="[('is_auto_campaign', '=', False)]",
    )
    default_account_ids = fields.Many2many(
        "social.account", string="Default Accounts",
    )
    plan_ids = fields.One2many(
        "xb.social.content.plan", "brand_profile_id", string="Plans",
    )
    plan_count = fields.Integer(compute="_compute_plan_count")
    competitor_ids = fields.One2many(
        "xb.social.competitor", "brand_profile_id", string="Competitors",
    )
    competitor_count = fields.Integer(compute="_compute_competitor_count")

    @api.depends("competitor_ids")
    def _compute_competitor_count(self):
        for profile in self:
            profile.competitor_count = len(profile.competitor_ids)

    def action_view_competitors(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Competitors"),
            "res_model": "xb.social.competitor",
            "view_mode": "list,form",
            "domain": [("brand_profile_id", "=", self.id)],
            "context": {"default_brand_profile_id": self.id},
        }

    @api.depends("plan_ids")
    def _compute_plan_count(self):
        for profile in self:
            profile.plan_count = len(profile.plan_ids)

    def action_view_plans(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Content Plans"),
            "res_model": "xb.social.content.plan",
            "view_mode": "kanban,list,form",
            "domain": [("brand_profile_id", "=", self.id)],
            "context": {"default_brand_profile_id": self.id},
        }

    def _image_visual_context(self):
        """Art-direction block injected into the image (SVG) prompt. Keeps the
        generated graphics on-brand: palette, typography and style notes."""
        self.ensure_one()
        lines = [
            "Brand: %s." % (self.name or ""),
        ]
        if self.industry:
            lines.append("Industry: %s." % self.industry)
        lines.append(
            "Color palette — primary/background: %s, secondary/accent: %s, "
            "text: %s. Stay within this palette."
            % (self.palette_primary or "#1A1A2E",
               self.palette_secondary or "#E94560",
               self.palette_accent or "#FFFFFF")
        )
        if self.font_hint:
            lines.append("Typography style: %s." % self.font_hint)
        if self.visual_style:
            lines.append("Art direction: %s" % self.visual_style)
        return "\n".join(lines)

    def _ai_system_context(self):
        """Frozen, brand-grounded system prompt shared by every generation."""
        self.ensure_one()
        lang = self.default_language.name or self.env._("the user's language")
        emoji = dict(self._fields["emoji_policy"].selection).get(self.emoji_policy)
        hashtags = dict(self._fields["hashtag_policy"].selection).get(self.hashtag_policy)
        lines = [
            "You are a senior social media strategist and copywriter.",
            "Write in %s." % lang,
            "Brand: %s." % (self.name or ""),
        ]
        if self.industry:
            lines.append("Industry: %s." % self.industry)
        if self.brand_voice:
            lines.append("Brand voice / tone: %s" % self.brand_voice)
        if self.target_audience:
            lines.append("Target audience: %s" % self.target_audience)
        if self.value_proposition:
            lines.append("Value proposition: %s" % self.value_proposition)
        if self.keywords:
            lines.append("Always-on themes/keywords: %s" % self.keywords)
        if self.banned_words:
            lines.append("Never use these words/phrases: %s" % self.banned_words)
        if self.cta_style:
            lines.append("Preferred call-to-action style: %s" % self.cta_style)
        lines.append("Emoji policy: %s." % (emoji or "light"))
        lines.append("Hashtag policy: %s." % (hashtags or "few"))
        lines.append(
            "Infer current seasonal and industry trends and relevant hashtags "
            "from your own knowledge of this industry and the time of year. "
            "Do not invent real-time data, statistics, or breaking news."
        )
        lines.append("Always respond with JSON matching the provided schema.")
        return "\n".join(lines)
