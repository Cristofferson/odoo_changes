# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class XbSocialGenerationJob(models.Model):
    _name = "xb.social.generation.job"
    _description = "AI Generation Job"
    _inherit = ["mail.thread"]
    _order = "create_date desc, id desc"

    # Deliberately not stored: it is built from the post's own name and from a
    # translated label, and a stored copy went stale the moment either changed
    # — jobs were still showing "Image — xb.social.plan.item,21".
    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, index=True,
    )
    plan_id = fields.Many2one("xb.social.content.plan", ondelete="cascade", index=True)
    item_id = fields.Many2one("xb.social.plan.item", ondelete="cascade", index=True)
    competitor_id = fields.Many2one(
        "xb.social.competitor", ondelete="cascade", index=True)
    provider_id = fields.Many2one("xb.social.ai.provider")

    job_type = fields.Selection(
        [("strategy", "Strategy"),
         ("item_copy", "Post Copy"),
         ("item_refine", "Copy Refinement"),
         ("competitor", "Competitor Analysis"),
         ("image", "Image"),
         ("video", "Video")],
        required=True,
    )
    instruction = fields.Text(
        string="Instruction",
        help="What the user asked for, on a refinement job.",
    )
    state = fields.Selection(
        [("queued", "Queued"),
         ("running", "Running"),
         ("done", "Done"),
         ("failed", "Failed")],
        default="queued", required=True, tracking=True,
    )
    idempotency_key = fields.Char(index=True)
    request_payload = fields.Text(string="Request (audit)")
    response_raw = fields.Text(string="Response (audit)")
    error_message = fields.Text()
    started_at = fields.Datetime()
    finished_at = fields.Datetime()
    token_usage_input = fields.Integer(string="Input Tokens")
    token_usage_output = fields.Integer(string="Output Tokens")

    _sql_constraints = [
        ("idempotency_key_uniq",
         "unique(idempotency_key)",
         "A generation job with this idempotency key already exists."),
    ]

    @api.depends("job_type", "plan_id.name", "item_id.theme",
                 "item_id.planned_date")
    def _compute_name(self):
        labels = dict(self._fields["job_type"].selection)
        for job in self:
            target = job.item_id.display_name or job.plan_id.display_name or ""
            job.name = "%s — %s" % (labels.get(job.job_type, job.job_type), target)

    # ----- execution --------------------------------------------------------
    def _run(self, raise_on_error=False):
        """Execute a single job. Dispatches to the plan/item generator.

        The cron swallows failures so one bad job cannot stop the queue; jobs
        launched straight from a dialog pass raise_on_error so the user sees
        what went wrong instead of a silent no-op."""
        self.ensure_one()
        self.write({"state": "running", "started_at": fields.Datetime.now()})
        try:
            if self.job_type == "strategy":
                usage = self.plan_id._generate_strategy(self)
            elif self.job_type == "item_copy":
                usage = self.item_id._generate_copy(self)
            elif self.job_type == "item_refine":
                usage = self.item_id._refine_copy(self)
            elif self.job_type == "competitor":
                usage = self.competitor_id._generate_analysis(self)
            elif self.job_type == "image":
                usage = self.item_id._generate_image(self)
            else:
                raise NotImplementedError(self.job_type)
            self.write({
                "state": "done",
                "finished_at": fields.Datetime.now(),
                "token_usage_input": (usage or {}).get("input_tokens", 0),
                "token_usage_output": (usage or {}).get("output_tokens", 0),
            })
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[xb_social_ai_planner] job %s failed: %s", self.id, exc)
            self.write({
                "state": "failed",
                "finished_at": fields.Datetime.now(),
                "error_message": str(exc),
            })
            body = _("AI generation failed: %s") % exc
            if self.item_id:
                self.item_id.message_post(body=body)
                self.item_id.write({"state": "failed", "error_message": str(exc)})
            elif self.competitor_id:
                self.competitor_id.message_post(body=body)
            elif self.plan_id:
                self.plan_id.message_post(body=body)
            if raise_on_error:
                raise UserError(body) from exc
            # otherwise do not re-raise: keep the cron processing other jobs

    @api.model
    def _cron_run_generation_jobs(self, limit=20):
        """Process queued jobs, committing after each so a failure or timeout
        doesn't roll back completed work."""
        jobs = self.search([("state", "=", "queued")], limit=limit, order="id")
        for job in jobs:
            job._run()
            # commit so each AI call's result is durable independently
            if not self.env.registry.in_test_mode():
                self.env.cr.commit()
        # roll plans whose items have all been generated up to 'generated'
        plans = jobs.mapped("plan_id") | jobs.mapped("item_id.plan_id")
        plans._refresh_state_after_generation()
        return True

    def action_requeue(self):
        for job in self:
            job.write({"state": "queued", "error_message": False})
        return True
