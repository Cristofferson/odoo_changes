# -*- coding: utf-8 -*-
import calendar
import json
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class XbSocialContentPlan(models.Model):
    _name = "xb.social.content.plan"
    _description = "Social Content Plan (monthly)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "plan_date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company,
        required=True, index=True,
    )
    brand_profile_id = fields.Many2one(
        "xb.social.brand.profile", string="Brand Profile",
        required=True, tracking=True,
    )
    plan_date = fields.Date(
        string="Month", required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        help="Any date in the target month; the day is normalised to the 1st.",
    )
    account_ids = fields.Many2many(
        "social.account", string="Accounts",
        help="Which connected accounts this plan targets.",
    )
    utm_campaign_id = fields.Many2one(
        "utm.campaign", string="Campaign",
        domain="[('is_auto_campaign', '=', False)]",
    )
    ai_provider_id = fields.Many2one("xb.social.ai.provider", string="AI Provider")

    posts_per_week = fields.Integer(string="Posts / Week", default=3)
    use_performance_feedback = fields.Boolean(
        string="Learn From Past Results", default=True,
        help="Feed the engagement figures of this brand's previous posts into "
             "the strategy, so the plan leans on what actually worked.",
    )
    performance_preview = fields.Text(
        string="What the AI Learned", compute="_compute_performance_preview",
        help="Exactly what the past-results section of the prompt will say. "
             "Empty until enough posts have been published and their "
             "statistics fetched from the networks.",
    )
    created_by_autopilot = fields.Boolean(readonly=True, copy=False)
    review_user_id = fields.Many2one(
        "res.users", string="Reviewer", copy=False,
        help="Gets an activity to review the plan once the AI is done.",
    )
    target_post_count = fields.Integer(
        string="Target Posts", compute="_compute_target_post_count",
        store=True, readonly=False,
    )
    also_generate_images = fields.Boolean(string="Also Generate Images")

    state = fields.Selection(
        [("draft", "Draft"),
         ("generating", "Generating"),
         ("generated", "Generated"),
         ("approved", "Approved"),
         ("pushed", "Pushed"),
         ("done", "Done")],
        default="draft", required=True, tracking=True,
    )
    monthly_theme = fields.Text(string="Monthly Theme")
    strategy_summary = fields.Html(string="Strategy Summary")

    item_ids = fields.One2many(
        "xb.social.plan.item", "plan_id", string="Posts",
    )
    generation_job_ids = fields.One2many(
        "xb.social.generation.job", "plan_id", string="Generation Jobs",
    )

    item_count = fields.Integer(compute="_compute_counts")
    approved_count = fields.Integer(compute="_compute_counts")
    pushed_count = fields.Integer(compute="_compute_counts")

    # ----- compute ----------------------------------------------------------
    @api.depends("brand_profile_id", "plan_date")
    def _compute_name(self):
        for plan in self:
            brand = plan.brand_profile_id.name or _("Plan")
            month = plan.plan_date and plan.plan_date.strftime("%Y-%m") or ""
            plan.name = "%s — %s" % (brand, month) if month else brand

    @api.depends("posts_per_week")
    def _compute_target_post_count(self):
        for plan in self:
            plan.target_post_count = max(1, (plan.posts_per_week or 3)) * 4

    @api.depends("brand_profile_id", "use_performance_feedback")
    def _compute_performance_preview(self):
        for plan in self:
            plan.performance_preview = (
                plan.brand_profile_id._performance_context()
                if plan.use_performance_feedback and plan.brand_profile_id
                else False
            )

    @api.depends("item_ids.state")
    def _compute_counts(self):
        for plan in self:
            plan.item_count = len(plan.item_ids)
            plan.approved_count = len(
                plan.item_ids.filtered(lambda i: i.state == "approved"))
            plan.pushed_count = len(
                plan.item_ids.filtered(lambda i: i.state in ("pushed", "posted")))

    # ----- onchange defaults ------------------------------------------------
    @api.onchange("brand_profile_id")
    def _onchange_brand_profile(self):
        if self.brand_profile_id:
            if not self.account_ids:
                self.account_ids = self.brand_profile_id.default_account_ids
            if not self.utm_campaign_id:
                self.utm_campaign_id = self.brand_profile_id.default_utm_campaign_id

    # ----- helpers ----------------------------------------------------------
    def _get_provider(self):
        self.ensure_one()
        provider = (
            self.ai_provider_id
            or self.company_id.xb_social_ai_default_provider_id
            or self.env["xb.social.ai.provider"].search(
                [("company_id", "in", (self.company_id.id, False))], limit=1)
        )
        if not provider:
            raise UserError(_(
                "No AI provider configured. Create one under "
                "AI Social Planner ▸ Configuration ▸ Providers."))
        return provider

    def _present_networks(self):
        """Return {media_type: max_post_length} for the networks targeted by
        this plan, restricted to those Odoo can actually write copy for."""
        self.ensure_one()
        msg_fields = self.env["social.post"]._message_fields()
        result = {}
        for account in self.account_ids:
            mt = account.media_id.media_type
            if mt in msg_fields and mt not in result:
                result[mt] = account.media_id.max_post_length or 0
        return result

    def _planned_dates(self, count):
        """Spread `count` posting datetimes across the plan's month, honouring
        the brand's posting days and times. Never schedules in the past: slots
        already elapsed are skipped, so a plan created mid-month still pushes
        cleanly. Returned datetimes are UTC, ready to store."""
        self.ensure_one()
        brand = self.brand_profile_id
        weekdays = brand._posting_weekdays()
        times = brand._posting_times()
        tz = pytz.timezone(brand._tz())
        now_local = pytz.utc.localize(fields.Datetime.now()).astimezone(tz)

        def slots_from(first_day, days):
            """Future (day, time) slots in chronological order."""
            found = []
            for offset in range(days):
                day = first_day + timedelta(days=offset)
                if day.weekday() not in weekdays:
                    continue
                for hour, minute in times:
                    naive = datetime(day.year, day.month, day.day, hour, minute)
                    # A DST jump can leave a wall-clock time non-existent or
                    # ambiguous; is_dst=None would raise, so let pytz pick.
                    local = tz.localize(naive)
                    if local > now_local:
                        found.append(local)
            return found

        first = self.plan_date.replace(day=1)
        candidates = slots_from(
            first, calendar.monthrange(first.year, first.month)[1])
        # Fallback: the plan's month is already over (or fully elapsed) — roll
        # forward from tomorrow until we have enough slots.
        if not candidates:
            start = now_local.date() + timedelta(days=1)
            span = 7
            while len(candidates) < max(1, count) and span <= 120:
                candidates = slots_from(start, span)
                span += 7
        if not candidates:
            raise UserError(_(
                "No posting slot fits this month. Check the posting days and "
                "times on brand profile '%s'.") % brand.display_name)

        # even sampling across the available slots
        dates = []
        n = max(1, count)
        step = len(candidates) / float(n)
        for i in range(n):
            local = candidates[min(len(candidates) - 1, int(round(i * step)))]
            dates.append(local.astimezone(pytz.utc).replace(tzinfo=None))
        return dates

    # ----- generation entrypoints ------------------------------------------
    def action_generate(self):
        """Queue a strategy generation job and flip to 'generating'."""
        for plan in self:
            if not plan.account_ids:
                raise UserError(_("Add at least one account to the plan first."))
            if not plan._present_networks():
                raise UserError(_(
                    "None of the selected accounts belong to a supported "
                    "network (Facebook, Instagram, LinkedIn, X)."))
            provider = plan._get_provider()
            plan.ai_provider_id = provider
            # remove un-approved/un-pushed items so regeneration is clean
            plan.item_ids.filtered(
                lambda i: i.state in ("draft", "generated", "needs_review",
                                      "rejected", "failed")
            ).unlink()
            plan.state = "generating"
            self.env["xb.social.generation.job"].create({
                "plan_id": plan.id,
                "company_id": plan.company_id.id,
                "provider_id": provider.id,
                "job_type": "strategy",
                "idempotency_key": "strategy-%s-%s" % (
                    plan.id, fields.Datetime.now().strftime("%Y%m%d%H%M%S")),
            })
        return True

    def _strategy_schema(self, count):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "monthly_theme": {"type": "string"},
                "strategy_summary": {
                    "type": "string",
                    "description": "2-4 short paragraphs (plain text or simple "
                                   "HTML) describing the month's strategy, "
                                   "content pillars and posting rationale.",
                },
                "posts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "theme": {"type": "string"},
                            "image_brief": {"type": "string"},
                            "video_brief": {"type": "string"},
                        },
                        "required": ["theme", "image_brief", "video_brief"],
                    },
                },
            },
            "required": ["monthly_theme", "strategy_summary", "posts"],
        }

    def _generate_strategy(self, job):
        """Called by the generation job. Builds the monthly strategy + post
        skeletons, then enqueues one copy job per post. Returns usage dict."""
        self.ensure_one()
        provider = job.provider_id or self._get_provider()
        networks = self._present_networks()
        count = max(1, self.target_post_count)

        system = self.brand_profile_id._ai_system_context()
        user = (
            "Create a social media content plan for the month of %s.\n"
            "Produce exactly %d posts.\n"
            "Target networks: %s.\n"
            "Give each post a distinct angle/theme that ladders up to one "
            "overarching monthly theme, plus a concise image brief and a short "
            "video brief (concept only — no production details)."
        ) % (
            self.plan_date.strftime("%B %Y"),
            count,
            ", ".join(networks.keys()) or "generic",
        )
        competitor_brief = self.brand_profile_id.competitor_ids._strategy_context()
        if competitor_brief:
            user += (
                "\n\nDifferentiate from these competitors and exploit the "
                "content gaps noted:\n%s" % competitor_brief
            )
        performance = (
            self.brand_profile_id._performance_context()
            if self.use_performance_feedback else ""
        )
        if performance:
            user += "\n\n%s" % performance

        schema = self._strategy_schema(count)
        transport = self.env["xb.social.ai.transport"]._get_transport(provider)
        job.request_payload = json.dumps({"system": system, "user": user})
        parsed, usage = transport.generate_text(provider, system, user, schema)
        job.response_raw = json.dumps(parsed)[:60000]

        self.monthly_theme = parsed.get("monthly_theme")
        self.strategy_summary = parsed.get("strategy_summary")

        posts = parsed.get("posts") or []
        dates = self._planned_dates(len(posts) or count)
        Item = self.env["xb.social.plan.item"]
        Job = self.env["xb.social.generation.job"]
        for idx, post in enumerate(posts):
            planned = dates[min(idx, len(dates) - 1)]
            item = Item.create({
                "plan_id": self.id,
                "sequence": (idx + 1) * 10,
                "planned_date": planned,
                "theme": post.get("theme"),
                "image_brief": post.get("image_brief"),
                "video_brief": post.get("video_brief"),
                "account_ids": [(6, 0, self.account_ids.ids)],
                "utm_campaign_id": self.utm_campaign_id.id or False,
                "state": "draft",
            })
            Job.create({
                "plan_id": self.id,
                "item_id": item.id,
                "company_id": self.company_id.id,
                "provider_id": provider.id,
                "job_type": "item_copy",
                "idempotency_key": "copy-%s" % item.id,
            })
            if self.also_generate_images:
                Job.create({
                    "plan_id": self.id,
                    "item_id": item.id,
                    "company_id": self.company_id.id,
                    "provider_id": provider.id,
                    "job_type": "image",
                    "idempotency_key": "image-%s" % item.id,
                })
        return usage

    def _refresh_state_after_generation(self):
        """Move plans to 'generated' once no copy job is left pending, and hand
        the finished plan to its reviewer."""
        for plan in self:
            if plan.state != "generating":
                continue
            pending = plan.generation_job_ids.filtered(
                lambda j: j.state in ("queued", "running"))
            if not pending and plan.item_ids:
                plan.state = "generated"
                plan._notify_reviewer()

    def _notify_reviewer(self):
        """Schedule the 'review this plan' activity. Only ever fires once, so a
        regenerated plan does not pile activities on the reviewer."""
        self.ensure_one()
        if not self.review_user_id or self.activity_ids.filtered(
                lambda a: a.user_id == self.review_user_id):
            return
        failed = len(self.generation_job_ids.filtered(
            lambda j: j.state == "failed"))
        note = _(
            "The AI plan for %(month)s is ready: %(count)s posts to review "
            "and approve.", month=self.plan_date.strftime("%B %Y"),
            count=len(self.item_ids))
        if failed:
            note += " " + _("%s generation job(s) failed.") % failed
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=self.plan_date,
            summary=_("Review the AI content plan"),
            note=note,
            user_id=self.review_user_id.id,
        )

    # ----- approval / push --------------------------------------------------
    def action_approve_all(self):
        for plan in self:
            plan.item_ids.filtered(
                lambda i: i.state in ("generated", "needs_review")
            ).action_approve()
            if plan.state == "generated" and all(
                    i.state in ("approved", "pushed", "posted", "rejected")
                    for i in plan.item_ids):
                plan.state = "approved"
        return True

    def action_push_approved(self):
        for plan in self:
            to_push = plan.item_ids.filtered(lambda i: i.state == "approved")
            if not to_push:
                raise UserError(_("No approved posts to push."))
            to_push.action_push_to_social()
            plan.state = "pushed"
        return True

    def action_open_native_calendar(self):
        """Open the native social.post calendar filtered to this plan's posts."""
        self.ensure_one()
        posts = self.item_ids.mapped("social_post_id")
        return {
            "type": "ir.actions.act_window",
            "name": _("Scheduled Posts"),
            "res_model": "social.post",
            "view_mode": "calendar,list,form",
            "domain": [("id", "in", posts.ids)],
        }
