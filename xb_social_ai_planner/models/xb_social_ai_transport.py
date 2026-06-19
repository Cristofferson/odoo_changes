# -*- coding: utf-8 -*-
"""Pluggable AI transport layer (bring-your-own-key).

`xb.social.ai.transport` defines the contract; one concrete `_inherit` model
per provider implements it. Dispatch is by `provider.provider_type`, so adding
a new provider (e.g. OpenAI) is a new `_inherit` model with no change to the
callers.

The text provider defaults to Claude (`claude-opus-4-8`). Odoo does not ship
the `anthropic` SDK, so the Anthropic implementation uses raw HTTP via
`requests` against `POST /v1/messages`.
"""
import json
import logging
import os
import shutil
import subprocess

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_BASE = "https://api.anthropic.com"

# Tools the CLI must never invoke for plain text generation (defence in depth:
# print mode rarely uses tools, but the planner only ever wants text back).
CLI_DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "NotebookEdit",
    "Glob", "Grep", "Task", "WebFetch", "WebSearch",
]


class XbSocialAiTransport(models.AbstractModel):
    _name = "xb.social.ai.transport"
    _description = "AI Transport (abstract contract)"

    # ----- dispatch ---------------------------------------------------------
    @api.model
    def _get_transport(self, provider):
        """Return the concrete transport model for a provider record."""
        model_name = "xb.social.ai.transport.%s" % (provider.provider_type or "anthropic")
        if model_name not in self.env:
            raise UserError(
                _("No AI transport is implemented for provider type '%s'.")
                % provider.provider_type
            )
        return self.env[model_name]

    # ----- contract (override in concrete models) ---------------------------
    @api.model
    def generate_text(self, provider, system_prompt, user_prompt, json_schema=None):
        """Return (parsed_dict_or_text, usage_dict). Override per provider."""
        raise NotImplementedError()

    @api.model
    def generate_image(self, provider, brief, n=1, size="1080x1080"):
        """Generate on-brand post image(s) without a dedicated image API.

        Strategy: ask the (text) model for a single, self-contained SVG that
        matches the art brief, then rasterise it to PNG with cairosvg. This
        works for ANY text-capable provider (Anthropic HTTP or Claude Code
        CLI) because it only relies on `generate_text`. Returns a list of
        ``(png_bytes, mimetype)`` tuples.
        """
        try:
            width, height = (int(x) for x in str(size).lower().split("x"))
        except (ValueError, TypeError):
            width = height = 1080
        system = self._image_svg_system(width, height)
        images = []
        for _i in range(max(1, n)):
            text, _usage = self.generate_text(provider, system, brief)
            svg = self._extract_svg(text)
            images.append((self._svg_to_png(svg, width, height), "image/png"))
        return images

    # ----- image helpers ----------------------------------------------------
    @api.model
    def _image_svg_system(self, width, height):
        return (
            "You are a senior graphic designer. You output clean, valid, "
            "self-contained SVG for social-media post images.\n"
            "Hard requirements:\n"
            "- The root element is <svg> with "
            'width="%(w)s" height="%(h)s" viewBox="0 0 %(w)s %(h)s" '
            'and xmlns="http://www.w3.org/2000/svg".\n'
            "- Fully self-contained: NO external URLs, remote fonts, scripts, "
            "or <image> referencing remote resources. Use only inline shapes, "
            "gradients, and <text> with generic font families "
            "(serif, sans-serif).\n"
            "- A polished composition that fills the entire canvas, respects "
            "the brand palette, and keeps any headline text legible with strong "
            "contrast. Leave the bottom-right corner relatively clear for a "
            "logo overlay.\n"
            "- Output ONLY the SVG markup: start with <svg and end with </svg>. "
            "No prose, no explanations, no markdown code fences."
        ) % {"w": width, "h": height}

    @api.model
    def _extract_svg(self, text):
        """Pull the <svg>…</svg> document out of the model's reply, tolerating
        stray code fences or surrounding prose."""
        s = (text or "").strip()
        start = s.find("<svg")
        end = s.rfind("</svg>")
        if start == -1 or end == -1 or end < start:
            raise UserError(_("The AI did not return a valid SVG image."))
        return s[start:end + len("</svg>")]

    @api.model
    def _svg_to_png(self, svg, width, height):
        """Rasterise an SVG string to PNG bytes via the optional cairosvg lib."""
        try:
            import cairosvg
        except ImportError:
            raise UserError(_(
                "AI image generation needs the optional 'cairosvg' Python "
                "library (and the system Cairo library). Install it with "
                "`pip install cairosvg`, or disable 'Also Generate Images'."))
        try:
            return cairosvg.svg2png(
                bytestring=svg.encode("utf-8"),
                output_width=width, output_height=height,
            )
        except Exception as exc:  # noqa: BLE001 — surface a clean error
            raise UserError(
                _("Could not rasterise the generated SVG: %s") % exc)

    # ----- shared helpers ---------------------------------------------------
    @api.model
    def _resolve_api_key(self, provider):
        """Read the BYOK key from the company (system-only field) or, as a
        fallback, from an ir.config_parameter. Never logged."""
        company = provider.company_id or self.env.company
        key = company.sudo().xb_social_ai_api_key
        if not key:
            key = self.env["ir.config_parameter"].sudo().get_param(
                "xb_social_ai_planner.api_key"
            )
        if not key:
            raise UserError(
                _("No AI API key configured. Set it in "
                  "Settings ▸ AI Social Planner.")
            )
        return key


class XbSocialAiTransportAnthropic(models.AbstractModel):
    _name = "xb.social.ai.transport.anthropic"
    _inherit = "xb.social.ai.transport"
    _description = "AI Transport — Anthropic (Claude)"

    @api.model
    def generate_text(self, provider, system_prompt, user_prompt, json_schema=None):
        api_key = self._resolve_api_key(provider)
        base_url = (provider.api_base_url or DEFAULT_ANTHROPIC_BASE).rstrip("/")
        url = "%s/v1/messages" % base_url

        output_config = {"effort": provider.effort or "high"}
        if json_schema:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}

        body = {
            "model": provider.text_model or "claude-opus-4-8",
            "max_tokens": provider.max_tokens or 8000,
            "thinking": {"type": "adaptive"},
            "output_config": output_config,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            resp = requests.post(
                url, headers=headers, json=body,
                timeout=provider.timeout or 120,
            )
        except requests.exceptions.RequestException as exc:
            raise UserError(_("Could not reach the AI provider: %s") % exc)

        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after", "?")
            raise UserError(
                _("AI provider rate limit reached (retry after %s s).") % retry_after
            )
        if resp.status_code >= 400:
            # Surface the provider error without leaking the key.
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except ValueError:
                detail = resp.text[:500]
            raise UserError(
                _("AI provider error (HTTP %s): %s") % (resp.status_code, detail)
            )

        data = resp.json()

        # Check stop_reason BEFORE reading content.
        stop_reason = data.get("stop_reason")
        if stop_reason == "refusal":
            raise UserError(
                _("The AI declined to generate this content (safety refusal). "
                  "Try rephrasing the brand profile or the request.")
            )
        if stop_reason == "max_tokens":
            raise UserError(
                _("The AI response was cut off (max_tokens). Increase the "
                  "provider's Max Tokens and try again.")
            )

        text = next(
            (b.get("text") for b in data.get("content", []) if b.get("type") == "text"),
            None,
        )
        if not text:
            raise UserError(_("The AI returned an empty response."))

        usage = data.get("usage", {}) or {}
        if json_schema:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise UserError(
                    _("The AI returned malformed JSON: %s") % exc
                )
            return parsed, usage
        return text, usage


class XbSocialAiTransportClaudeCode(models.AbstractModel):
    """Talk to Claude through the locally-installed Claude Code CLI instead of
    the HTTP API. This reuses an existing Claude Code / Max subscription, so it
    needs no API key and incurs no per-call API billing.

    Requirement: the `claude` executable AND its auth must be reachable by the
    Odoo *service user* (the one running the cron). Because that user is usually
    `odoo`, install the binary on a system path and point `cli_config_dir` at a
    credentials directory it can read (CLAUDE_CONFIG_DIR).
    """
    _name = "xb.social.ai.transport.claude_code"
    _inherit = "xb.social.ai.transport"
    _description = "AI Transport — Claude Code CLI (subscription, no API key)"

    @api.model
    def generate_text(self, provider, system_prompt, user_prompt, json_schema=None):
        binary = (provider.cli_binary or "claude").strip()
        exe = shutil.which(binary) or binary

        prompt = user_prompt
        if json_schema:
            # The CLI does not enforce structured output, so we ask for it and
            # validate by parsing. Keep the instruction terse and unambiguous.
            prompt = (
                "%s\n\n---\nReturn a SINGLE valid JSON object and nothing else: "
                "no markdown code fences, no commentary before or after. The "
                "object MUST conform to this JSON Schema:\n%s"
                % (user_prompt, json.dumps(json_schema))
            )

        cmd = [
            exe, "-p",
            "--output-format", "json",
            "--model", provider.text_model or "claude-opus-4-8",
            "--disallowed-tools", *CLI_DISALLOWED_TOOLS,
        ]
        if system_prompt:
            cmd += ["--append-system-prompt", system_prompt]

        env = dict(os.environ)
        if provider.cli_config_dir:
            env["CLAUDE_CONFIG_DIR"] = provider.cli_config_dir

        try:
            completed = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=provider.timeout or 180,
                env=env,
                cwd="/tmp",  # neutral cwd; the CLI must not touch the repo
            )
        except FileNotFoundError:
            raise UserError(_(
                "Claude Code CLI not found ('%s'). Install it and set the CLI "
                "Binary path on the AI provider.") % binary)
        except subprocess.TimeoutExpired:
            raise UserError(_(
                "The Claude Code CLI timed out after %ss. Increase the "
                "provider's Timeout or lower Effort.") % (provider.timeout or 180))

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()[:500]
            raise UserError(_(
                "Claude Code CLI failed (exit %s). Check that the service user "
                "is authenticated (run `claude` once as that user, or set CLI "
                "Config Dir). Details: %s") % (completed.returncode, stderr))

        try:
            envelope = json.loads(completed.stdout)
        except (ValueError, json.JSONDecodeError):
            raise UserError(_(
                "Claude Code CLI returned unreadable output: %s")
                % (completed.stdout or "").strip()[:500])

        if envelope.get("is_error") or envelope.get("subtype") != "success":
            detail = envelope.get("result") or envelope.get("subtype") or "unknown"
            raise UserError(_("Claude Code CLI error: %s") % detail)

        text = envelope.get("result")
        if not text:
            raise UserError(_("The Claude Code CLI returned an empty response."))

        # The CLI usage envelope already exposes input_tokens / output_tokens.
        usage = envelope.get("usage", {}) or {}
        if json_schema:
            return self._parse_cli_json(text), usage
        return text, usage

    @api.model
    def _parse_cli_json(self, text):
        """Parse JSON returned by the CLI, tolerating stray code fences or
        surrounding prose (the CLI gives no schema guarantee)."""
        s = (text or "").strip()
        if s.startswith("```"):
            s = s.strip("`").strip()
            if s[:4].lower() == "json":
                s = s[4:].strip()
        try:
            return json.loads(s)
        except (ValueError, json.JSONDecodeError):
            start, end = s.find("{"), s.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(s[start:end + 1])
                except (ValueError, json.JSONDecodeError):
                    pass
        raise UserError(_("The Claude Code CLI returned malformed JSON."))
