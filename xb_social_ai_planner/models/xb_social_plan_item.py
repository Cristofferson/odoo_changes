# -*- coding: utf-8 -*-
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# media_type -> our per-network copy field. Native social.post field names are
# resolved at runtime via social.post._message_fields() / _images_fields().
MEDIA_TO_FIELD = {
    "facebook": "facebook_message",
    "instagram": "instagram_message",
    "linkedin": "linkedin_message",
    "twitter": "twitter_message",
}


class XbSocialPlanItem(models.Model):
    _name = "xb.social.plan.item"
    _description = "Social Plan Item (AI draft post)"
    _inherit = ["mail.thread"]
    _order = "planned_date, sequence, id"

    plan_id = fields.Many2one(
        "xb.social.content.plan", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        related="plan_id.company_id", store=True, index=True,
    )
    sequence = fields.Integer(default=10)
    planned_date = fields.Datetime(string="Planned Date")
    week_number = fields.Integer(compute="_compute_week_number", store=True)
    theme = fields.Char(string="Angle / Theme")
    state = fields.Selection(
        [("draft", "Draft"),
         ("generated", "Generated"),
         ("needs_review", "Needs Review"),
         ("approved", "Approved"),
         ("rejected", "Rejected"),
         ("pushed", "Pushed"),
         ("posted", "Posted"),
         ("failed", "Failed")],
        default="draft", required=True, tracking=True,
    )
    error_message = fields.Text()

    # Base copy (ready-to-post; cta/hashtags are also kept for editing/insight)
    message = fields.Text(string="Post Text")
    cta = fields.Char(string="Call to Action")
    hashtags = fields.Char(string="Hashtags")
    inferred_trends = fields.Char(string="Inferred Trends")

    # Per-network copy
    is_split_per_media = fields.Boolean(string="Split Per Network")
    facebook_message = fields.Text(string="Facebook Text")
    instagram_message = fields.Text(string="Instagram Text")
    linkedin_message = fields.Text(string="LinkedIn Text")
    twitter_message = fields.Text(string="X Text")
    length_warning = fields.Char(compute="_compute_length_warning")

    # Creative briefs
    image_brief = fields.Text(string="Image Brief")
    video_brief = fields.Text(string="Video Brief")

    # Generated / selected media
    generated_image_ids = fields.Many2many(
        "ir.attachment", "xb_plan_item_gen_img_rel",
        "item_id", "attachment_id", string="Generated Images",
    )
    selected_image_ids = fields.Many2many(
        "ir.attachment", "xb_plan_item_sel_img_rel",
        "item_id", "attachment_id", string="Selected Images",
    )

    account_ids = fields.Many2many("social.account", string="Accounts")
    utm_campaign_id = fields.Many2one(
        "utm.campaign", domain="[('is_auto_campaign', '=', False)]",
    )

    social_post_id = fields.Many2one(
        "social.post", string="Published Post", readonly=True, copy=False,
    )
    social_post_state = fields.Selection(
        related="social_post_id.state", string="Post Status", readonly=True,
    )

    # ----- compute ----------------------------------------------------------
    @api.depends("planned_date")
    def _compute_week_number(self):
        for item in self:
            if item.planned_date:
                item.week_number = (item.planned_date.day - 1) // 7 + 1
            else:
                item.week_number = 0

    def _network_message(self, media_type):
        """Per-network copy, falling back to the base message."""
        self.ensure_one()
        field = MEDIA_TO_FIELD.get(media_type)
        return (self[field] if field else None) or self.message or ""

    def _max_lengths(self):
        """Return {media_type: max_post_length} for this item's networks."""
        result = {}
        for account in self.account_ids:
            mt = account.media_id.media_type
            if mt in MEDIA_TO_FIELD and mt not in result:
                result[mt] = account.media_id.max_post_length or 0
        return result

    @api.depends("message", "facebook_message", "instagram_message",
                 "linkedin_message", "twitter_message", "account_ids")
    def _compute_length_warning(self):
        labels = {"facebook": "Facebook", "instagram": "Instagram",
                  "linkedin": "LinkedIn", "twitter": "X"}
        for item in self:
            over = []
            for mt, maxlen in item._max_lengths().items():
                if maxlen and len(item._network_message(mt)) > maxlen:
                    over.append("%s (>%d)" % (labels.get(mt, mt), maxlen))
            item.length_warning = (
                _("Over limit: %s") % ", ".join(over) if over else False)

    # ----- generation -------------------------------------------------------
    def _copy_schema(self, networks):
        props = {
            "message": {"type": "string",
                        "description": "Ready-to-post base text including the "
                                       "call to action and hashtags."},
            "cta": {"type": "string"},
            "hashtags": {"type": "string"},
            "inferred_trends": {"type": "string"},
        }
        required = ["message", "cta", "hashtags", "inferred_trends"]
        for mt in networks:
            field = MEDIA_TO_FIELD[mt]
            props[field] = {
                "type": "string",
                "description": "Full ready-to-post text for %s." % mt,
            }
            required.append(field)
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": props,
            "required": required,
        }

    def _generate_copy(self, job):
        """Called by the generation job. Returns usage dict."""
        self.ensure_one()
        provider = job.provider_id or self.plan_id._get_provider()
        networks = self._max_lengths()
        system = self.plan_id.brand_profile_id._ai_system_context()

        net_lines = "\n".join(
            "- %s (max %s characters)" % (mt, maxlen or "no limit")
            for mt, maxlen in networks.items()
        ) or "- generic"
        user = (
            "Monthly theme: %s\n"
            "This post's angle: %s\n"
            "Write the copy for this single social post.\n"
            "Provide a base 'message' plus a tailored version per network, "
            "each within the network's character limit:\n%s\n"
            "Each version must be ready to post and end with hashtags."
        ) % (
            self.plan_id.monthly_theme or "",
            self.theme or "",
            net_lines,
        )

        schema = self._copy_schema(networks)
        transport = self.env["xb.social.ai.transport"]._get_transport(provider)
        job.request_payload = json.dumps({"system": system, "user": user})
        parsed, usage = transport.generate_text(provider, system, user, schema)
        job.response_raw = json.dumps(parsed)[:30000]

        vals = {
            "message": parsed.get("message"),
            "cta": parsed.get("cta"),
            "hashtags": parsed.get("hashtags"),
            "inferred_trends": parsed.get("inferred_trends"),
        }
        split = False
        for mt in networks:
            field = MEDIA_TO_FIELD[mt]
            net_text = parsed.get(field)
            if net_text:
                vals[field] = net_text
                if net_text != vals["message"]:
                    split = True
        vals["is_split_per_media"] = split
        self.write(vals)

        # flag for review if any network is over its limit
        self.state = "needs_review" if self.length_warning else "generated"
        return usage

    # ----- approval ---------------------------------------------------------
    def action_approve(self):
        for item in self:
            if item.state in ("generated", "needs_review"):
                item.state = "approved"
        return True

    def action_reject(self):
        self.write({"state": "rejected"})
        return True

    def action_reset_draft(self):
        self.write({"state": "draft"})
        return True

    # ----- push to native social.post --------------------------------------
    def _validate_for_push(self):
        self.ensure_one()
        if not self.message and not self.is_split_per_media:
            raise UserError(_("Post '%s' has no text.") % (self.theme or self.id))
        if not self.account_ids:
            raise UserError(_("Post '%s' has no accounts.") % (self.theme or self.id))
        for mt, maxlen in self._max_lengths().items():
            if maxlen and len(self._network_message(mt)) > maxlen:
                raise UserError(_(
                    "Post '%s' exceeds the %s character limit (%d).")
                    % (self.theme or self.id, mt, maxlen))
        # Instagram requires an image
        media_types = set(self.account_ids.mapped("media_id.media_type"))
        if "instagram" in media_types and not self.selected_image_ids:
            raise UserError(_(
                "Post '%s' targets Instagram, which requires an image.")
                % (self.theme or self.id))

    def action_push_to_social(self):
        SocialPost = self.env["social.post"]
        msg_fields = SocialPost._message_fields()   # {media_type: field}
        img_fields = SocialPost._images_fields()
        for item in self:
            if item.social_post_id:
                continue  # idempotent
            item._validate_for_push()
            media_types = set(item.account_ids.mapped("media_id.media_type"))

            vals = {
                "message": item.message or "",
                "account_ids": [(6, 0, item.account_ids.ids)],
                "company_id": item.company_id.id,
                "post_method": "scheduled",
                "scheduled_date": item.planned_date,
            }
            if item.utm_campaign_id:
                vals["utm_campaign_id"] = item.utm_campaign_id.id

            split = item.is_split_per_media
            for mt in media_types:
                native_field = msg_fields.get(mt)
                net_msg = item._network_message(mt)
                if native_field and net_msg and net_msg != vals["message"]:
                    vals[native_field] = net_msg
                    split = True
            vals["is_split_per_media"] = split

            if item.selected_image_ids:
                vals["image_ids"] = [(6, 0, item.selected_image_ids.ids)]
                for mt in media_types:
                    native_img = img_fields.get(mt)
                    if native_img and split:
                        vals[native_img] = [(6, 0, item.selected_image_ids.ids)]

            post = SocialPost.create(vals)
            post._set_attachemnt_res_id()
            post.action_schedule()
            item.write({"social_post_id": post.id, "state": "pushed"})
        return True

    def action_open_social_post(self):
        self.ensure_one()
        if not self.social_post_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "social.post",
            "res_id": self.social_post_id.id,
            "view_mode": "form",
        }
