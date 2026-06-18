Changelog
=========

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
* 19.0.1.2.0 — AI image generation (configurable image provider).
* 19.0.2.0.0 — AI video generation (YouTube path).
