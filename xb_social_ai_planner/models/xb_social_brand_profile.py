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

    # Hue buckets (degrees) -> plain-English colour family. Image models act on
    # words, not hex codes, so we translate the brand kit before prompting.
    _HUE_NAMES = [
        (15, "red"), (45, "orange"), (65, "yellow"), (160, "green"),
        (200, "teal"), (255, "blue"), (290, "purple"), (330, "magenta"),
        (360, "red"),
    ]

    @api.model
    def _color_word(self, hex_value):
        """Describe a hex colour in words (e.g. '#1A1A2E' -> 'deep navy blue')."""
        raw = (hex_value or "").strip().lstrip("#")
        if len(raw) == 3:
            raw = "".join(c * 2 for c in raw)
        if len(raw) != 6:
            return ""
        try:
            r, g, b = (int(raw[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        except ValueError:
            return ""
        import colorsys
        hue, light, sat = colorsys.rgb_to_hls(r, g, b)
        hue *= 360

        if sat < 0.12:
            if light < 0.15:
                return "near-black"
            if light < 0.4:
                return "charcoal grey"
            if light < 0.75:
                return "mid grey"
            return "off-white" if light < 0.97 else "white"

        family = next(
            (name for limit, name in self._HUE_NAMES if hue <= limit), "red")
        if family == "blue" and light < 0.3:
            return "deep navy blue"
        # Golds sit on the orange/yellow border with medium lightness.
        if 30 <= hue <= 60 and 0.3 <= light <= 0.65 and sat > 0.35:
            return "warm gold"
        if light < 0.25:
            return "deep %s" % family
        if light > 0.8:
            return "pale %s" % family
        if sat > 0.7:
            return "vivid %s" % family
        return family

    def _image_photo_context(self):
        """Art direction for photoreal image models. Colours are described in
        words (hex is meaningless to them) and the logo is left out — it is
        composited onto the render afterwards."""
        self.ensure_one()
        lines = []
        if self.industry:
            lines.append("Industry / subject matter: %s." % self.industry)
        if self.target_audience:
            lines.append("It must appeal to: %s" % self.target_audience)
        palette = [w for w in (
            self._color_word(self.palette_primary),
            self._color_word(self.palette_secondary),
            self._color_word(self.palette_accent),
        ) if w]
        if palette:
            lines.append(
                "Colour mood: the scene should read predominantly in %s."
                % ", ".join(dict.fromkeys(palette)))
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
        # Models date from their training cut-off and happily emit hashtags
        # like #Weddings2024 years later, so state the date explicitly.
        lines.append(
            "Today's date is %s. Every year, season or dated hashtag you write "
            "must match it; never use a year from the past."
            % fields.Date.context_today(self).strftime("%d %B %Y")
        )
        lines.append(
            "Infer current seasonal and industry trends and relevant hashtags "
            "from your own knowledge of this industry and the time of year. "
            "Do not invent real-time data, statistics, or breaking news."
        )
        # Anything a brand publishes is a factual claim about itself. The model
        # has no way to check these, so it must never make them up.
        lines.append(
            "Never fabricate facts about the business: no invented customer "
            "testimonials or named customers, no made-up prices, discounts, "
            "promotions, deadlines, awards, statistics or events. Write only "
            "from the brand information given above. If a post idea would need "
            "such a fact, write it as a general invitation instead."
        )
        lines.append("Always respond with JSON matching the provided schema.")
        return "\n".join(lines)
