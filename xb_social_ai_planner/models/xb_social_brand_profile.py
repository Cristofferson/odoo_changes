# -*- coding: utf-8 -*-
import logging
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.base.models.res_partner import _tz_get
from odoo.addons.xb_social_ai_planner.models.xb_social_competitor import (
    fetch_public_text,
)

_logger = logging.getLogger(__name__)

# "10:00", "18.30", "9h" ... anything that reads as a time of day.
_TIME_RE = re.compile(r"^\s*(\d{1,2})\s*[:.hH]?\s*(\d{2})?\s*$")


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

    website = fields.Char(
        string="Website",
        help="Your own public site. 'Draft From Website' reads it and fills "
             "in the profile below so you correct a draft instead of facing "
             "an empty form.",
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

    # ----- posting windows --------------------------------------------------
    post_mon = fields.Boolean(string="Monday", default=True)
    post_tue = fields.Boolean(string="Tuesday", default=True)
    post_wed = fields.Boolean(string="Wednesday", default=True)
    post_thu = fields.Boolean(string="Thursday", default=True)
    post_fri = fields.Boolean(string="Friday", default=True)
    post_sat = fields.Boolean(string="Saturday")
    post_sun = fields.Boolean(string="Sunday")
    posting_times = fields.Char(
        string="Posting Times", default="10:00",
        help="Times of day the posts are scheduled at, separated by commas "
             "(e.g. 10:00, 18:30). When several are given they are used in "
             "turn.",
    )
    tz = fields.Selection(
        _tz_get, string="Timezone",
        default=lambda self: self.env.user.tz or "UTC",
        help="Timezone the posting times are expressed in. Set it explicitly: "
             "the autopilot runs unattended and must not depend on whoever "
             "happens to trigger it.",
    )

    # ----- autopilot ---------------------------------------------------------
    autopilot = fields.Boolean(
        string="Autopilot",
        help="Generate next month's plan automatically and notify the person "
             "in charge so they only have to review and approve it.",
    )
    autopilot_day = fields.Integer(
        string="Generate On Day", default=25,
        help="Day of the month the next month's plan is generated on.",
    )
    autopilot_user_id = fields.Many2one(
        "res.users", string="Notify",
        help="Who gets the review activity once the plan is generated.",
    )
    autopilot_posts_per_week = fields.Integer(
        string="Autopilot Posts / Week", default=3,
    )
    autopilot_images = fields.Boolean(
        string="Autopilot Images",
        help="Also generate the images for the automatically created plan.",
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

    completeness = fields.Integer(
        string="Profile Completeness", compute="_compute_completeness",
        help="How much of what the AI actually reads is filled in. "
             "A thin profile produces generic copy.",
    )
    completeness_missing = fields.Char(
        string="Still Missing", compute="_compute_completeness",
    )
    completeness_label = fields.Char(
        string="Completeness Detail", compute="_compute_completeness",
        help="The whole sentence, computed here rather than assembled in the "
             "view: interleaving fields with text splits it into fragments no "
             "translator can work with.",
    )

    # What the AI genuinely leans on, in the order it matters. Anything not
    # listed here (autopilot, brand kit, competitors) is optional polish.
    _COMPLETENESS_FIELDS = (
        ("industry", "Industry"),
        ("brand_voice", "Brand voice"),
        ("target_audience", "Target audience"),
        ("value_proposition", "Value proposition"),
        ("keywords", "Keywords"),
        ("cta_style", "CTA style"),
        ("default_account_ids", "Default accounts"),
        ("posting_times", "Posting times"),
    )

    @api.depends(lambda self: [fname for fname, _lbl in self._COMPLETENESS_FIELDS])
    def _compute_completeness(self):
        total = len(self._COMPLETENESS_FIELDS)
        for profile in self:
            missing = [label for fname, label in self._COMPLETENESS_FIELDS
                       if not profile[fname]]
            profile.completeness = round(100.0 * (total - len(missing)) / total)
            profile.completeness_missing = ", ".join(missing)
            profile.completeness_label = self.env._(
                "Profile %(percent)s%% complete. Still missing: %(missing)s. "
                "The thinner this is, the more generic the copy.",
                percent=profile.completeness,
                missing=profile.completeness_missing,
            ) if missing else ""

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

    # ----- draft the profile from the brand's own website --------------------
    # What the AI is allowed to fill in, and only when it is still empty.
    _AUTOFILL_FIELDS = ("industry", "brand_voice", "target_audience",
                        "value_proposition", "keywords", "cta_style")

    def _resolve_provider(self):
        self.ensure_one()
        provider = (
            self.company_id.xb_social_ai_default_provider_id
            or self.env["xb.social.ai.provider"].search(
                [("company_id", "in", (self.company_id.id, False))], limit=1)
        )
        if not provider:
            raise UserError(self.env._(
                "No AI engine configured. Set one in Settings ▸ AI Social "
                "Planner."))
        return provider

    def _autofill_schema(self):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "industry": {
                    "type": "string",
                    "description": "The sector, in a few words.",
                },
                "brand_voice": {
                    "type": "string",
                    "description": "Tone of voice, 1-2 sentences.",
                },
                "target_audience": {
                    "type": "string",
                    "description": "Who this brand sells to, 1-2 sentences.",
                },
                "value_proposition": {
                    "type": "string",
                    "description": "What makes it worth choosing, 1-2 "
                                   "sentences.",
                },
                "keywords": {
                    "type": "string",
                    "description": "6-12 recurring themes, comma separated.",
                },
                "cta_style": {
                    "type": "string",
                    "description": "How the site asks people to act.",
                },
            },
            "required": list(self._AUTOFILL_FIELDS),
        }

    def action_autofill_from_website(self):
        """Draft the profile from the brand's own public site.

        Facing an empty thirty-field form is the main reason profiles end up
        thin, and a thin profile is exactly what makes the copy generic. The
        site already says who the brand is, so let the model read it — but
        only into fields that are still empty, so nothing a human wrote is
        ever overwritten."""
        self.ensure_one()
        if not self.website:
            raise UserError(self.env._(
                "Set the brand's website first, then run this again."))
        url, text = fetch_public_text(self.website)
        if len(text) < 200:
            raise UserError(self.env._(
                "There was almost no readable text at %s. Try the page that "
                "actually describes the brand.") % url)

        provider = self._resolve_provider()
        system = (
            "You profile a brand for a social-media content planner, reading "
            "only the text of its own public website.\n"
            "Base every answer strictly on that text. Never invent awards, "
            "certifications, guarantees, prices, statistics, testimonials or "
            "claims about materials or origin that the page does not state. "
            "If the page does not support a field, describe only what it does "
            "support, briefly.\n"
            "Write in the same language as the website."
        )
        user = "Brand name: %s\nWebsite: %s\n\nPage text:\n%s" % (
            self.name or "", url, text)

        transport = self.env["xb.social.ai.transport"]._get_transport(provider)
        parsed, _usage = transport.generate_text(
            provider, system, user, self._autofill_schema())

        filled, skipped = [], []
        vals = {}
        for fname in self._AUTOFILL_FIELDS:
            label = self._fields[fname].string
            value = (parsed.get(fname) or "").strip()
            if not value:
                continue
            if self[fname]:
                skipped.append(label)
            else:
                vals[fname] = value
                filled.append(label)
        if vals:
            self.write(vals)

        body = (
            self.env._("Drafted from %(url)s: %(fields)s.",
                       url=url, fields=", ".join(filled))
            if filled else
            self.env._("Read %(url)s but found nothing new to fill in.",
                       url=url)
        )
        if skipped:
            body += " " + self.env._(
                "Left untouched because they were already written: %s."
            ) % ", ".join(skipped)
        self.message_post(body=body)
        return True

    # ----- posting windows --------------------------------------------------
    _WEEKDAY_FIELDS = ("post_mon", "post_tue", "post_wed", "post_thu",
                       "post_fri", "post_sat", "post_sun")

    def _posting_weekdays(self):
        """Weekday numbers (Mon=0 … Sun=6) the brand publishes on.
        Falls back to Mon-Fri when the profile has every day switched off."""
        self.ensure_one()
        days = [idx for idx, fname in enumerate(self._WEEKDAY_FIELDS) if self[fname]]
        return days or [0, 1, 2, 3, 4]

    @api.model
    def _parse_posting_times(self, raw):
        """Parse the free-text posting times into sorted (hour, minute) tuples.
        Returns an empty list when nothing parses, so callers can fall back."""
        times = []
        for chunk in (raw or "").replace(";", ",").split(","):
            if not chunk.strip():
                continue
            match = _TIME_RE.match(chunk)
            if not match:
                return []
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            if hour > 23 or minute > 59:
                return []
            times.append((hour, minute))
        return sorted(set(times))

    def _posting_times(self):
        """Times of day to publish at, defaulting to a single 10:00 slot."""
        self.ensure_one()
        return self._parse_posting_times(self.posting_times) or [(10, 0)]

    @api.constrains("posting_times")
    def _check_posting_times(self):
        for profile in self:
            if profile.posting_times and not self._parse_posting_times(
                    profile.posting_times):
                raise ValidationError(self.env._(
                    "'%(value)s' is not a valid list of posting times. Use 24h "
                    "times separated by commas, for example: 10:00, 18:30",
                    value=profile.posting_times,
                ))

    @api.constrains("autopilot_day")
    def _check_autopilot_day(self):
        for profile in self:
            if profile.autopilot and not 1 <= profile.autopilot_day <= 28:
                raise ValidationError(self.env._(
                    "The autopilot day must be between 1 and 28 so it exists "
                    "in every month."))

    def _tz(self):
        """Timezone the brand's posting times are expressed in."""
        self.ensure_one()
        return (self.tz
                or self.company_id.partner_id.tz
                or self.env.user.tz
                or "UTC")

    # ----- performance feedback ---------------------------------------------
    # How many published posts must carry engagement figures before we let the
    # numbers steer the next plan. Below this it is noise, not a signal.
    _PERF_MIN_POSTS = 3
    # How far back to look. A year of posts is plenty and keeps the prompt small.
    _PERF_SAMPLE = 60

    def _scored_history(self):
        """[(engagement, item)] for this brand's already-published posts that
        carry engagement figures, best first. Empty when there is nothing to
        learn from yet (fresh install, or the account statistics never synced)."""
        self.ensure_one()
        items = self.env["xb.social.plan.item"].search(
            [("plan_id.brand_profile_id", "=", self.id),
             ("social_post_id", "!=", False),
             ("planned_date", "<", fields.Datetime.now())],
            order="planned_date desc", limit=self._PERF_SAMPLE,
        )
        scored = []
        for item in items:
            live = item.social_post_id.live_post_ids.filtered(
                lambda lp: lp.state == "posted")
            if live:
                scored.append((sum(live.mapped("engagement")), item))
        # All-zero means the statistics were never fetched from the networks;
        # feeding a flat ranking to the model would teach it nothing.
        if len(scored) < self._PERF_MIN_POSTS or not any(s for s, _i in scored):
            return []
        return sorted(scored, key=lambda pair: pair[0], reverse=True)

    def _describe_post_result(self, engagement, item):
        """One human-readable line about how a published post did."""
        local = fields.Datetime.context_timestamp(item, item.planned_date)
        networks = ", ".join(sorted(set(
            item.social_post_id.live_post_ids.mapped("account_id.media_id.name")
        ))) or "—"
        return "- \"%s\" — %s at %s, %s, %s: %d engagements" % (
            (item.theme or "").strip() or "(untitled)",
            local.strftime("%A"),
            local.strftime("%H:%M"),
            networks,
            "with image" if item.selected_image_ids else "text only",
            engagement,
        )

    def _performance_context(self):
        """Real engagement figures from this brand's previous AI-planned posts,
        rendered for the strategy prompt. Empty string when there is no signal
        yet, so the prompt simply omits the section."""
        self.ensure_one()
        scored = self._scored_history()
        if not scored:
            return ""

        best = scored[:5]
        # Only contrast with the worst performers once the sample is big enough
        # for "worst" to mean something other than "the other two".
        worst = scored[-3:] if len(scored) >= 8 else []

        lines = [
            "Real engagement results from this brand's previous posts "
            "(likes, comments and shares reported by the connected accounts). "
            "Use them: repeat what worked, drop what did not.",
            "Best performing:",
        ]
        lines += [self._describe_post_result(s, i) for s, i in best]
        if worst:
            lines.append("Worst performing:")
            lines += [self._describe_post_result(s, i)
                      for s, i in reversed(worst)]

        # Aggregates say more than any single post: they are what tells the
        # model to shift the whole month, not just imitate one lucky angle.
        with_image = [s for s, i in scored if i.selected_image_ids]
        without = [s for s, i in scored if not i.selected_image_ids]
        if with_image and without:
            lines.append(
                "Average engagement with an image: %d, without: %d."
                % (sum(with_image) / len(with_image),
                   sum(without) / len(without)))

        by_day = {}
        for score, item in scored:
            local = fields.Datetime.context_timestamp(item, item.planned_date)
            by_day.setdefault(local.strftime("%A"), []).append(score)
        if len(by_day) > 1:
            ranked = sorted(
                ((sum(v) / len(v), day) for day, v in by_day.items()),
                reverse=True)
            lines.append(
                "Average engagement by weekday: %s."
                % ", ".join("%s %d" % (day, avg) for avg, day in ranked))
        return "\n".join(lines)

    # ----- autopilot ---------------------------------------------------------
    def _autopilot_target_month(self, today):
        """First day of the month the autopilot should be planning right now."""
        return (today.replace(day=1) + timedelta(days=32)).replace(day=1)

    def _autopilot_create_plan(self, month):
        """Build next month's plan and start generating it. Returns the plan."""
        self.ensure_one()
        plan = self.env["xb.social.content.plan"].create({
            "brand_profile_id": self.id,
            "company_id": self.company_id.id or self.env.company.id,
            "plan_date": month,
            "account_ids": [(6, 0, self.default_account_ids.ids)],
            "utm_campaign_id": self.default_utm_campaign_id.id or False,
            "posts_per_week": self.autopilot_posts_per_week or 3,
            "also_generate_images": self.autopilot_images,
            "created_by_autopilot": True,
            "review_user_id": self.autopilot_user_id.id or False,
        })
        plan.action_generate()
        return plan

    @api.model
    def _cron_autopilot(self):
        """Generate next month's plan for every brand on autopilot.

        Runs daily and fires from the configured day onwards, so a server that
        was down on the day itself still catches up. Idempotent: a brand that
        already has a plan for the target month is skipped."""
        today = fields.Date.context_today(self)
        profiles = self.search([("autopilot", "=", True)])
        Plan = self.env["xb.social.content.plan"]
        for profile in profiles:
            if today.day < (profile.autopilot_day or 25):
                continue
            month = profile._autopilot_target_month(today)
            if Plan.search_count([("brand_profile_id", "=", profile.id),
                                  ("plan_date", "=", month)]):
                continue
            if not profile.default_account_ids:
                profile.message_post(body=self.env._(
                    "Autopilot could not generate the plan for %(month)s: this "
                    "brand profile has no default accounts.",
                    month=month.strftime("%B %Y"),
                ))
                continue
            try:
                profile._autopilot_create_plan(month)
                self.env.cr.commit()
            except Exception as exc:  # noqa: BLE001 — one brand must not stop the rest
                self.env.cr.rollback()
                _logger.warning(
                    "[xb_social_ai_planner] autopilot failed for brand %s: %s",
                    profile.id, exc)
                profile.message_post(body=self.env._(
                    "Autopilot could not generate the plan for %(month)s: "
                    "%(error)s", month=month.strftime("%B %Y"), error=exc))
                self.env.cr.commit()
        return True

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
            "promotions, deadlines, awards, statistics or events, and no "
            "certifications, guarantees, insurance, materials or origin claims "
            "that are not stated above. Write only from the brand information "
            "given above. If a post idea would need such a fact, write it as a "
            "general invitation instead."
        )
        lines.append("Always respond with JSON matching the provided schema.")
        return "\n".join(lines)
