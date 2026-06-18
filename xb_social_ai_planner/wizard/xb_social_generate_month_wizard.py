# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
