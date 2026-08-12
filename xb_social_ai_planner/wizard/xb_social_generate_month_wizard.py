# -*- coding: utf-8 -*-
import logging

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class XbSocialGenerateMonthWizard(models.TransientModel):
    _name = "xb.social.generate.month.wizard"
    _description = "Generate Monthly Content Plan"

    brand_profile_id = fields.Many2one(
        "xb.social.brand.profile", string="Brand Profile", required=True,
    )
    plan_date = fields.Date(
        string="Month", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    account_ids = fields.Many2many("social.account", string="Accounts", required=True)
    utm_campaign_id = fields.Many2one(
        "utm.campaign", domain="[('is_auto_campaign', '=', False)]",
    )
    ai_provider_id = fields.Many2one("xb.social.ai.provider", string="AI Provider")
    posts_per_week = fields.Integer(string="Posts / Week", default=3)
    also_generate_images = fields.Boolean(string="Also Generate Images")

    post_count = fields.Integer(
        string="Posts", compute="_compute_preview",
        help="How many posts this will produce.")
    schedule_preview = fields.Char(
        string="Schedule", compute="_compute_preview",
        help="The exact slots the posts will land on, from the brand's "
             "posting days and times.")
    schedule_problem = fields.Char(
        string="Problem", compute="_compute_preview")

    @api.depends("brand_profile_id", "plan_date", "posts_per_week",
                 "also_generate_images")
    def _compute_preview(self):
        """Say what is about to be produced, before a token is spent.

        The dialog used to ask for 'posts per week' and reveal the answer —
        how many posts, on which days — only after the AI had already run and
        been paid for."""
        Plan = self.env["xb.social.content.plan"]
        for wiz in self:
            wiz.post_count = max(1, wiz.posts_per_week or 3) * 4
            wiz.schedule_preview = False
            wiz.schedule_problem = False
            if not (wiz.brand_profile_id and wiz.plan_date):
                continue
            try:
                dates = Plan._plan_dates_for(
                    wiz.brand_profile_id, wiz.plan_date, wiz.post_count)
            except UserError as exc:
                wiz.schedule_problem = exc.args[0] if exc.args else str(exc)
                continue
            except Exception as exc:  # noqa: BLE001 — a preview must not block
                _logger.info(
                    "[xb_social_ai_planner] could not preview the schedule: %s",
                    exc)
                continue

            tz = pytz.timezone(wiz.brand_profile_id._tz())
            def local(value):
                return pytz.utc.localize(value).astimezone(tz)

            first, last = local(dates[0]), local(dates[-1])
            template = (
                _("%(count)s posts, each with its own AI image, from "
                  "%(first)s to %(last)s (%(tz)s)")
                if wiz.also_generate_images else
                _("%(count)s posts, from %(first)s to %(last)s (%(tz)s)")
            )
            wiz.schedule_preview = template % {
                "count": len(dates),
                "first": first.strftime("%a %d %b, %H:%M"),
                "last": last.strftime("%a %d %b, %H:%M"),
                "tz": tz.zone,
            }

    @api.onchange("brand_profile_id")
    def _onchange_brand_profile(self):
        if self.brand_profile_id:
            self.account_ids = self.brand_profile_id.default_account_ids
            self.utm_campaign_id = self.brand_profile_id.default_utm_campaign_id

    def action_generate(self):
        self.ensure_one()
        if not self.account_ids:
            raise UserError(_("Select at least one account."))
        plan = self.env["xb.social.content.plan"].create({
            "brand_profile_id": self.brand_profile_id.id,
            "plan_date": self.plan_date.replace(day=1),
            "account_ids": [(6, 0, self.account_ids.ids)],
            "utm_campaign_id": self.utm_campaign_id.id or False,
            "ai_provider_id": self.ai_provider_id.id or False,
            "posts_per_week": self.posts_per_week,
            "also_generate_images": self.also_generate_images,
        })
        plan.action_generate()
        return {
            "type": "ir.actions.act_window",
            "name": _("Content Plan"),
            "res_model": "xb.social.content.plan",
            "res_id": plan.id,
            "view_mode": "form",
        }
