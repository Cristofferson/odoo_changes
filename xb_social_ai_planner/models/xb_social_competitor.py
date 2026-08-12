# -*- coding: utf-8 -*-
"""Competitor analysis.

Note on scraping: the live feeds of Facebook/Instagram/LinkedIn/X cannot be
scraped — those platforms block it and forbid it in their ToS. This module
therefore scrapes the competitor's **public web pages** (site/landing/blog),
lets the user paste sample posts, and uses the AI to analyse positioning and
content gaps. A paid social-data provider can later be plugged into the same
``xb.social.ai.transport`` layer.
"""
import json
import logging
import re

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _html_to_text(html):
    """Very small HTML→text reducer (no extra dependency)."""
    text = _TAG_RE.sub(" ", html or "")
    text = _HTML_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def fetch_public_text(url, limit=20000):
    """Fetch a public page and reduce it to plain text.

    Shared with the brand profile's "draft me from my own website" action:
    same HTTP hygiene, same reducer, one place to fix. Returns
    ``(normalised_url, text)``."""
    url = (url or "").strip()
    if not url:
        raise UserError(_("No URL to read."))
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.get(
            url, timeout=30,
            headers={"User-Agent": "Mozilla/5.0 (compatible; OdooBot)"},
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise UserError(_("Could not fetch the page: %s") % exc)
    return url, _html_to_text(resp.text)[:limit]


class XbSocialCompetitor(models.Model):
    _name = "xb.social.competitor"
    _description = "Social Competitor"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, index=True,
    )
    brand_profile_id = fields.Many2one(
        "xb.social.brand.profile", string="For Brand", ondelete="cascade",
        help="The brand this competitor is benchmarked against.",
    )
    website = fields.Char(
        string="Public Website / URL",
        help="Public page to scrape (homepage, landing or blog).",
    )
    social_handles = fields.Text(
        string="Social Handles",
        help="Handles/URLs for reference (not scraped — platforms forbid it).",
    )
    notes = fields.Text(string="Notes")
    manual_samples = fields.Text(
        string="Sample Posts (pasted)",
        help="Paste example posts/captions to feed the AI analysis.",
    )

    scraped_content = fields.Text(string="Scraped Page Text", readonly=True)
    last_scraped = fields.Datetime(readonly=True)

    analysis_summary = fields.Html(string="AI Analysis", readonly=True)
    key_themes = fields.Char(string="Key Themes", readonly=True)
    tone = fields.Char(string="Tone", readonly=True)
    opportunities = fields.Text(string="Content Gaps / Opportunities", readonly=True)
    analyzed_on = fields.Datetime(readonly=True)

    # ----- scraping ---------------------------------------------------------
    def action_scrape_website(self):
        for comp in self:
            if not comp.website:
                raise UserError(_("Set a public website/URL to scrape."))
            url, text = fetch_public_text(comp.website)
            comp.write({
                "scraped_content": text,
                "last_scraped": fields.Datetime.now(),
            })
            comp.message_post(body=_("Scraped %d characters from %s.")
                              % (len(text), url))
        return True

    # ----- AI analysis ------------------------------------------------------
    def _resolve_provider(self):
        self.ensure_one()
        provider = (
            self.company_id.xb_social_ai_default_provider_id
            or self.env["xb.social.ai.provider"].search(
                [("company_id", "in", (self.company_id.id, False))], limit=1)
        )
        if not provider:
            raise UserError(_("No AI provider configured."))
        return provider

    def action_analyze(self):
        Job = self.env["xb.social.generation.job"]
        for comp in self:
            provider = comp._resolve_provider()
            Job.create({
                "company_id": comp.company_id.id,
                "competitor_id": comp.id,
                "provider_id": provider.id,
                "job_type": "competitor",
                "idempotency_key": "competitor-%s-%s" % (
                    comp.id, fields.Datetime.now().strftime("%Y%m%d%H%M%S")),
            })
            comp.message_post(body=_("Competitor analysis queued."))
        return True

    def _analysis_schema(self):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "analysis_summary": {
                    "type": "string",
                    "description": "2-3 paragraphs (plain text or simple HTML) on "
                                   "the competitor's positioning and content style.",
                },
                "key_themes": {"type": "string"},
                "tone": {"type": "string"},
                "opportunities": {
                    "type": "string",
                    "description": "Concrete content gaps and angles OUR brand "
                                   "could use to differentiate.",
                },
            },
            "required": ["analysis_summary", "key_themes", "tone", "opportunities"],
        }

    def _generate_analysis(self, job):
        """Called by the generation job. Returns usage dict."""
        self.ensure_one()
        provider = job.provider_id or self._resolve_provider()
        brand = self.brand_profile_id
        system = (brand._ai_system_context() if brand else
                  "You are a senior social media competitive analyst. "
                  "Respond with JSON matching the provided schema.")
        parts = ["Analyse this competitor and find how our brand can differentiate.",
                 "Competitor: %s" % (self.name or "")]
        if self.social_handles:
            parts.append("Handles: %s" % self.social_handles)
        if self.website:
            parts.append("Website: %s" % self.website)
        if self.scraped_content:
            parts.append("Public page text (excerpt):\n%s" % self.scraped_content[:8000])
        if self.manual_samples:
            parts.append("Sample posts:\n%s" % self.manual_samples[:4000])
        if self.notes:
            parts.append("Analyst notes: %s" % self.notes)
        user = "\n\n".join(parts)

        schema = self._analysis_schema()
        transport = self.env["xb.social.ai.transport"]._get_transport(provider)
        job.request_payload = json.dumps({"system": system, "user": user})[:60000]
        parsed, usage = transport.generate_text(provider, system, user, schema)
        job.response_raw = json.dumps(parsed)[:30000]

        self.write({
            "analysis_summary": parsed.get("analysis_summary"),
            "key_themes": parsed.get("key_themes"),
            "tone": parsed.get("tone"),
            "opportunities": parsed.get("opportunities"),
            "analyzed_on": fields.Datetime.now(),
        })
        return usage

    def _strategy_context(self):
        """Compact competitor brief injected into the monthly strategy prompt."""
        lines = []
        for comp in self.filtered(lambda c: c.analysis_summary or c.key_themes):
            bits = [comp.name]
            if comp.key_themes:
                bits.append("themes: %s" % comp.key_themes)
            if comp.opportunities:
                bits.append("gaps to exploit: %s" % comp.opportunities)
            lines.append("- " + "; ".join(bits))
        return "\n".join(lines)
