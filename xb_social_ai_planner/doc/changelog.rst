Changelog
=========

19.0.1.3.0 (2026-07)
--------------------
* **Photoreal image generation (bring-your-own-key).** Image generation is now
  a pluggable layer of its own (``xb.social.ai.image``) with four backends:

  * ``svg`` — the previous key-free route: the text model designs vector art
    that the server rasterises. Still the default.
  * ``openai_images`` — OpenAI Images (``gpt-image-1`` & co).
  * ``gemini_images`` — Google Gemini image models.
  * ``custom`` — any OpenAI-compatible images endpoint.

* New provider settings: image model, image API base URL, format
  (square / portrait / landscape), style, quality, variants per post, timeout.
* Briefs are tailored per backend: the vector backend is briefed like a
  designer, photoreal backends like a photographer. Brand palette hex codes are
  translated into plain-English colour words, which is what image models
  actually act on. Generated images are fitted to the exact social format.
* Optional **prompt enrichment**: the text model rewrites the brief into a
  proper image prompt before the image call (falls back to the raw brief).
* **New text transports**: ``openai`` and ``custom`` (OpenAI-compatible chat
  endpoints). Both were already offered in the provider dropdown but had no
  implementation and raised an error when selected.
* Token usage is normalised across providers, so OpenAI jobs no longer record
  0 input/output tokens; image jobs record the backend and model that billed.
* Spanish / Spanish (Mexico) translations completed: 373 of 373 terms.

19.0.1.2.0 (2026-06)
--------------------
* AI image generation without an image API: the text model produces SVG which
  is rasterised to PNG with ``cairosvg`` and attached to the post.
* Brand kit on the brand profile (logo, palette, typography hint, visual
  style) feeding the image prompt; the logo is composited onto the render.

19.0.1.1.0 (2026-06)
--------------------
* New AI backend **Claude Code CLI** (``provider_type = claude_code``): drives
  Claude through the locally-installed ``claude`` executable instead of the HTTP
  API, reusing a Claude Code / Max subscription — no API key, no per-call
  billing. Configurable CLI binary path and ``CLAUDE_CONFIG_DIR``.
* The provider form now shows API-key vs CLI options depending on the backend.
* Bug fixes from QA: the default AI provider is now company-global
  (``company_id = False``) so plans of any company resolve it; planner never
  schedules posts in the past (mid-month plans push cleanly).

19.0.1.0.0 (2026-06)
--------------------
* Initial release.
* Brand voice profiles used as AI context.
* Monthly content plans with AI-generated strategy summary and per-post copy,
  CTA, hashtags and inferred trends.
* Bring-your-own-key AI provider layer; defaults to Claude (``claude-opus-4-8``)
  via raw HTTP, provider/model configurable.
* Per-network copy (Facebook, Instagram, LinkedIn, X) within each network's
  ``max_post_length``.
* Push approved posts into the native ``social.post`` pipeline (scheduled);
  native cron publishes and the native calendar shows them.
* Asynchronous generation via an ``ir.cron`` queue (avoids request timeouts).
* Odoo 19 privilege-based security, multi-company record rules,
  English / Spanish / Spanish (Mexico) translations auto-loaded on install.

Roadmap
-------
* 19.0.2.0.0 — AI video generation (YouTube path), through the same pluggable
  media layer.
