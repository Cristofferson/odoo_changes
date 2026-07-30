# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# The handful of tweaks people actually ask for, so the common case is one
# click instead of typing the same sentence every time.
PRESETS = [
    ("shorter", "Make it shorter"),
    ("longer", "Make it longer"),
    ("warmer", "Warmer, more human"),
    ("professional", "More professional"),
    ("no_emoji", "Remove the emojis"),
    ("stronger_cta", "Stronger call to action"),
    ("custom", "Custom instruction"),
]

PRESET_INSTRUCTIONS = {
    "shorter": "Make the copy noticeably shorter and tighter without losing "
               "the message or the call to action.",
    "longer": "Develop the copy further: add a little more substance and "
              "detail while keeping it easy to read.",
    "warmer": "Rewrite in a warmer, closer, more human tone — as if talking "
              "to one person rather than an audience.",
    "professional": "Rewrite in a more professional, sober tone. Keep it "
                    "warm but drop any slang or over-familiarity.",
    "no_emoji": "Rewrite without a single emoji.",
    "stronger_cta": "Keep the body as it is but make the call to action much "
                    "more compelling and explicit.",
}


class XbSocialRefineWizard(models.TransientModel):
    _name = "xb.social.refine.wizard"
    _description = "Refine Post Copy with AI"

    item_ids = fields.Many2many(
        "xb.social.plan.item", string="Posts", required=True,
    )
    item_count = fields.Integer(compute="_compute_item_count")
    preset = fields.Selection(
        PRESETS, string="What to change", default="shorter", required=True,
    )
    instruction = fields.Text(
        string="Instruction",
        help="Describe the change in your own words, e.g. 'mention the "
             "lifetime warranty' or 'do not talk about prices'.",
    )

    @api.depends("item_ids")
    def _compute_item_count(self):
        for wizard in self:
            wizard.item_count = len(wizard.item_ids)

    def _instruction(self):
        self.ensure_one()
        if self.preset == "custom":
            if not (self.instruction or "").strip():
                raise UserError(_("Write the instruction for the AI."))
            return self.instruction.strip()
        base = PRESET_INSTRUCTIONS[self.preset]
        # A preset plus a note is the most useful combination: "shorter, and
        # mention the workshop".
        extra = (self.instruction or "").strip()
        return "%s %s" % (base, extra) if extra else base

    def action_refine(self):
        """Refine every selected post, right now — the user is watching."""
        self.ensure_one()
        blocked = self.item_ids.filtered(
            lambda i: i.state in ("pushed", "posted"))
        if blocked:
            raise UserError(_(
                "These posts have already been pushed to Social Marketing and "
                "can no longer be refined here: %s")
                % ", ".join(blocked.mapped(lambda i: i.theme or str(i.id))))
        if not self.item_ids:
            raise UserError(_("Select at least one post."))

        instruction = self._instruction()
        Job = self.env["xb.social.generation.job"]
        stamp = fields.Datetime.now().strftime("%Y%m%d%H%M%S%f")
        for item in self.item_ids:
            provider = item.plan_id._get_provider()
            job = Job.create({
                "plan_id": item.plan_id.id,
                "item_id": item.id,
                "company_id": item.company_id.id,
                "provider_id": provider.id,
                "job_type": "item_refine",
                "instruction": instruction,
                "idempotency_key": "refine-%s-%s" % (item.id, stamp),
            })
            # Synchronous on purpose: waiting two minutes for the cron to pick
            # up a one-line tweak is not an edit loop anyone would use.
            job._run(raise_on_error=True)
        return {"type": "ir.actions.act_window_close"}
