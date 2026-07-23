# -*- coding: utf-8 -*-
"""Pluggable image-generation backends (bring-your-own-key).

Two families live behind the same contract, selected by
`provider.image_provider_type`:

* ``svg`` — no image API at all. The *text* model designs a vector graphic
  which we rasterise with cairosvg. On-brand and free when the text backend is
  the Claude Code CLI, but it is graphic design, not photography.
* ``openai_images`` / ``gemini_images`` / ``custom`` — real image models.
  Photoreal output, billed per image by the provider, needs an image API key.

Adding a provider = one more `_inherit` model here; callers never change.
"""
import base64
import io
import json
import logging

import requests

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE = "https://api.openai.com"
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com"

# Final pixel size we want on the post, per format.
SOCIAL_SIZES = {
    "square": (1080, 1080),
    "portrait": (1080, 1350),
    "landscape": (1200, 675),
}

# What each backend renders natively; we fit to SOCIAL_SIZES afterwards.
OPENAI_SIZES = {
    "square": "1024x1024",
    "portrait": "1024x1536",
    "landscape": "1536x1024",
}
GEMINI_RATIOS = {"square": "1:1", "portrait": "4:5", "landscape": "16:9"}

STYLE_GUIDANCE = {
    "photo": (
        "Photorealistic photograph. Natural depth of field, realistic "
        "materials and lighting. Shot on a full-frame camera with a prime lens."
    ),
    "product": (
        "Professional studio product photograph. Seamless backdrop, controlled "
        "softbox lighting, crisp focus on the product, subtle reflections and "
        "shadows. Catalogue quality."
    ),
    "lifestyle": (
        "Candid lifestyle photograph with real people in a believable setting, "
        "natural light, authentic expressions. The product is present but the "
        "scene tells the story."
    ),
    "illustration": (
        "Rich editorial illustration with intentional texture and brushwork. "
        "Not a photograph."
    ),
    "flat": (
        "Clean flat vector-style graphic: simple geometric shapes, generous "
        "negative space, no photographic texture."
    ),
}

# Appended to every photoreal prompt: the failure modes of image models.
PHOTO_GUARDRAILS = (
    "Do not render any watermark, signature, stock-photo overlay, logo or "
    "brand mark. Avoid garbled or misspelled lettering — if no text is "
    "requested, include no text at all. Keep the bottom-right corner visually "
    "calm so a logo can be overlaid there."
)


class XbSocialAiImage(models.AbstractModel):
    _name = "xb.social.ai.image"
    _description = "AI Image Backend (abstract contract)"

    # ----- dispatch ---------------------------------------------------------
    @api.model
    def _get_backend(self, provider):
        """Return the concrete image backend for a provider record."""
        kind = provider.image_provider_type or "svg"
        if kind == "none":
            raise UserError(_(
                "Image generation is disabled on AI provider '%s'. Pick an "
                "Image Provider on it, or upload the image manually."
            ) % provider.display_name)
        model_name = "xb.social.ai.image.%s" % kind
        if model_name not in self.env:
            raise UserError(
                _("No image backend is implemented for '%s'.") % kind)
        return self.env[model_name]

    # ----- contract (override in concrete models) ---------------------------
    @api.model
    def _brief_mode(self):
        """'vector' (the model writes SVG) or 'photo' (a real image model)."""
        return "vector"

    @api.model
    def generate_image(self, provider, brief, n=1, image_format=None):
        """Return a list of ``(png_bytes, mimetype)``."""
        raise NotImplementedError()

    # ----- shared helpers ---------------------------------------------------
    @api.model
    def _resolve_image_api_key(self, provider):
        """Image key from the company (system-only field), falling back to an
        ir.config_parameter. Never logged, never echoed in errors."""
        company = provider.company_id or self.env.company
        key = company.sudo().xb_social_ai_image_api_key
        if not key:
            key = self.env["ir.config_parameter"].sudo().get_param(
                "xb_social_ai_planner.image_api_key")
        if not key:
            raise UserError(_(
                "No image API key configured. Set 'AI Image API Key' in "
                "Settings ▸ AI Social Planner, or switch the provider's Image "
                "Provider to the key-free vector option."))
        return key

    @api.model
    def _image_format(self, provider, image_format=None):
        fmt = image_format or provider.image_format or "square"
        return fmt if fmt in SOCIAL_SIZES else "square"

    @api.model
    def _pixel_size(self, fmt):
        return SOCIAL_SIZES.get(fmt, SOCIAL_SIZES["square"])

    @api.model
    def _style_guidance(self, provider):
        return STYLE_GUIDANCE.get(provider.image_style or "photo", "")

    @api.model
    def _photo_prompt(self, provider, brief):
        """Turn the art brief into a prompt for a real image model."""
        parts = [brief, self._style_guidance(provider), PHOTO_GUARDRAILS]
        return "\n\n".join(p for p in parts if p)

    @api.model
    def _boost_prompt(self, provider, brief):
        """Optionally let the *text* model rewrite the brief into a richer,
        single-paragraph image prompt. Best-effort: any failure falls back to
        the raw brief, because a worse prompt beats a failed post."""
        if not provider.image_prompt_boost:
            return brief
        system = (
            "You turn a marketing brief into a prompt for a text-to-image "
            "model. Reply with ONE vivid paragraph (max 120 words) describing "
            "the subject, setting, composition, lighting, colour and mood of a "
            "single photograph. Describe only what is visible. Never mention "
            "brands, logos or written words. No preamble, no quotes, no lists."
        )
        try:
            transport = self.env["xb.social.ai.transport"]._get_transport(provider)
            text, _usage = transport.generate_text(provider, system, brief)
            text = (text or "").strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001 — enrichment is optional
            _logger.info(
                "[xb_social_ai_planner] prompt boost unavailable (%s); "
                "using the raw brief.", exc)
        return brief

    @api.model
    def _fit(self, data, fmt):
        """Resize/crop the returned image to the exact social format.
        Best-effort: returns the bytes untouched if Pillow chokes."""
        target = self._pixel_size(fmt)
        try:
            from PIL import Image, ImageOps  # Pillow ships with Odoo
            img = Image.open(io.BytesIO(data))
            if img.size == target:
                return data
            img = ImageOps.fit(
                img.convert("RGB"), target, method=Image.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="PNG")
            return out.getvalue()
        except Exception as exc:  # noqa: BLE001 — cosmetic step
            _logger.warning(
                "[xb_social_ai_planner] could not fit image to %s: %s",
                target, exc)
            return data

    @api.model
    def _http_error(self, resp, label):
        """Raise a clean UserError from a provider HTTP error, never leaking
        the key that produced it."""
        detail = ""
        try:
            payload = resp.json()
            error = payload.get("error")
            if isinstance(error, dict):
                detail = error.get("message") or ""
            elif isinstance(error, str):
                detail = error
            if not detail:
                detail = json.dumps(payload)[:500]
        except ValueError:
            detail = (resp.text or "")[:500]

        if resp.status_code in (401, 403):
            raise UserError(_(
                "%(provider)s rejected the image API key (HTTP %(code)s). "
                "Check 'AI Image API Key' in Settings ▸ AI Social Planner. "
                "Details: %(detail)s",
                provider=label, code=resp.status_code, detail=detail))
        if resp.status_code == 429:
            raise UserError(_(
                "%(provider)s rate limit or quota reached. Details: %(detail)s",
                provider=label, detail=detail))
        raise UserError(_(
            "%(provider)s image error (HTTP %(code)s): %(detail)s",
            provider=label, code=resp.status_code, detail=detail))


class XbSocialAiImageSvg(models.AbstractModel):
    """Key-free backend: the text model designs an SVG, we rasterise it.

    Works with any text provider, including the Claude Code CLI, so a customer
    can generate on-brand post graphics without a single image API call.
    """
    _name = "xb.social.ai.image.svg"
    _inherit = "xb.social.ai.image"
    _description = "AI Image — Vector design via the text model"

    @api.model
    def _brief_mode(self):
        return "vector"

    @api.model
    def generate_image(self, provider, brief, n=1, image_format=None):
        fmt = self._image_format(provider, image_format)
        width, height = self._pixel_size(fmt)
        transport = self.env["xb.social.ai.transport"]._get_transport(provider)
        system = transport._image_svg_system(width, height)
        images = []
        for _i in range(max(1, n)):
            text, _usage = transport.generate_text(provider, system, brief)
            svg = transport._extract_svg(text)
            images.append((transport._svg_to_png(svg, width, height), "image/png"))
        return images


class XbSocialAiImageOpenai(models.AbstractModel):
    """OpenAI Images — POST /v1/images/generations.

    GPT image models return base64 in ``data[].b64_json`` by default;
    ``response_format`` is a DALL·E-only parameter, so we only send it there.
    """
    _name = "xb.social.ai.image.openai_images"
    _inherit = "xb.social.ai.image"
    _description = "AI Image — OpenAI Images (bring your own key)"

    @api.model
    def _brief_mode(self):
        return "photo"

    @api.model
    def _base_url(self, provider):
        return (provider.image_api_base_url or DEFAULT_OPENAI_BASE).rstrip("/")

    @api.model
    def generate_image(self, provider, brief, n=1, image_format=None):
        api_key = self._resolve_image_api_key(provider)
        fmt = self._image_format(provider, image_format)
        model = (provider.image_model or "gpt-image-1").strip()
        is_dalle = model.startswith("dall-e")

        prompt = self._photo_prompt(provider, self._boost_prompt(provider, brief))
        count = max(1, n)

        body = {
            "model": model,
            "prompt": prompt,
            "n": 1 if (is_dalle and model.endswith("-3")) else count,
            "size": OPENAI_SIZES.get(fmt, "1024x1024"),
        }
        quality = provider.image_quality or "auto"
        if quality != "auto":
            # low/medium/high are GPT-image values; DALL·E 3 wants standard/hd.
            body["quality"] = (
                {"high": "hd"}.get(quality, "standard") if is_dalle else quality
            )
        if is_dalle:
            body["response_format"] = "b64_json"
        else:
            body["output_format"] = "png"

        url = "%s/v1/images/generations" % self._base_url(provider)
        try:
            resp = requests.post(
                url,
                headers={"Authorization": "Bearer %s" % api_key,
                         "Content-Type": "application/json"},
                json=body,
                timeout=provider.image_timeout or 180,
            )
        except requests.exceptions.RequestException as exc:
            raise UserError(_("Could not reach the image provider: %s") % exc)

        if resp.status_code >= 400:
            self._http_error(resp, "OpenAI")

        payload = resp.json()
        images = []
        for entry in payload.get("data", []):
            b64 = entry.get("b64_json")
            if not b64:
                continue
            try:
                raw = base64.b64decode(b64)
            except (ValueError, TypeError):
                continue
            images.append((self._fit(raw, fmt), "image/png"))

        if not images:
            raise UserError(_(
                "The image provider returned no usable image. This usually "
                "means the prompt was rejected by its content filter — try "
                "rewording the post's image brief."))

        # DALL·E 3 caps n at 1: loop for the remaining variants.
        while len(images) < count:
            images += self.generate_image(provider, brief, n=1, image_format=fmt)
        return images[:count]


class XbSocialAiImageCustom(models.AbstractModel):
    """Any OpenAI-compatible images endpoint (self-hosted, gateway, proxy).
    Same wire format; only the base URL differs, and it is mandatory."""
    _name = "xb.social.ai.image.custom"
    _inherit = "xb.social.ai.image.openai_images"
    _description = "AI Image — Custom (OpenAI-compatible endpoint)"

    @api.model
    def _base_url(self, provider):
        if not provider.image_api_base_url:
            raise UserError(_(
                "The custom image provider needs an 'Image API Base URL' "
                "(an OpenAI-compatible endpoint)."))
        return provider.image_api_base_url.rstrip("/")


class XbSocialAiImageGemini(models.AbstractModel):
    """Google Gemini image models — generateContent with an IMAGE modality.

    The image comes back inline as base64 under
    ``candidates[].content.parts[].inlineData.data``.
    """
    _name = "xb.social.ai.image.gemini_images"
    _inherit = "xb.social.ai.image"
    _description = "AI Image — Google Gemini (bring your own key)"

    @api.model
    def _brief_mode(self):
        return "photo"

    @api.model
    def _body(self, provider, prompt, fmt, with_format=True):
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        if with_format:
            body["generationConfig"]["responseFormat"] = {
                "image": {
                    "aspectRatio": GEMINI_RATIOS.get(fmt, "1:1"),
                    "imageSize": "2K" if provider.image_quality == "high" else "1K",
                }
            }
        return body

    @api.model
    def _call(self, provider, api_key, prompt, fmt):
        base = (provider.image_api_base_url or DEFAULT_GEMINI_BASE).rstrip("/")
        model = (provider.image_model or "gemini-3-pro-image").strip()
        url = "%s/v1/models/%s:generateContent" % (base, model)
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

        for with_format in (True, False):
            try:
                resp = requests.post(
                    url, headers=headers,
                    json=self._body(provider, prompt, fmt, with_format),
                    timeout=provider.image_timeout or 180,
                )
            except requests.exceptions.RequestException as exc:
                raise UserError(_("Could not reach the image provider: %s") % exc)
            # Older/other Gemini image models reject the sizing block; retry
            # once without it rather than failing the whole post.
            if resp.status_code == 400 and with_format:
                _logger.info(
                    "[xb_social_ai_planner] Gemini rejected the image sizing "
                    "block; retrying without it.")
                continue
            if resp.status_code >= 400:
                self._http_error(resp, "Gemini")
            return resp.json()
        return {}

    @api.model
    def generate_image(self, provider, brief, n=1, image_format=None):
        api_key = self._resolve_image_api_key(provider)
        fmt = self._image_format(provider, image_format)
        prompt = self._photo_prompt(provider, self._boost_prompt(provider, brief))

        images = []
        for _i in range(max(1, n)):
            payload = self._call(provider, api_key, prompt, fmt)
            for candidate in payload.get("candidates", []):
                for part in (candidate.get("content") or {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if not inline or not inline.get("data"):
                        continue
                    try:
                        raw = base64.b64decode(inline["data"])
                    except (ValueError, TypeError):
                        continue
                    images.append((self._fit(raw, fmt), "image/png"))
                    break
        if not images:
            raise UserError(_(
                "The image provider returned no usable image. This usually "
                "means the prompt was blocked by its safety filter — try "
                "rewording the post's image brief."))
        return images
