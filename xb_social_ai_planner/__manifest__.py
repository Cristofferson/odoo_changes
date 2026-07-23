# -*- coding: utf-8 -*-
{
    "name": "XUBAX AI Social Content Planner",
    "summary": "Add AI content planning, strategy and competitor analysis to "
               "Odoo's Social Marketing. Generates monthly themes, copy, CTA and "
               "hashtags with Claude (or your provider) and publishes natively.",
    "description": """
XUBAX AI Social Content Planner
===============================

An AI-powered content **planner and strategist** that sits on top of Odoo's
native **Social Marketing** app. Define a monthly content plan per social
account/campaign and let AI build the whole thing: monthly theme, per-post
copy, calls to action, and hashtags (trends inferred from your industry and
the season). Approved posts are pushed into the native ``social.post``
pipeline, so publishing and the native calendar keep working unchanged.

Key features
------------
* **Brand voice profiles** — tone, audience, value proposition, keywords,
  banned words, emoji/hashtag policy. The AI uses this as context.
* **Monthly content plans** — one plan per month per set of accounts/campaign,
  with an AI-generated strategy summary and a planner kanban + calendar.
* **AI generation, two backends** — defaults to Claude (``claude-opus-4-8``)
  and works either way:

  * *Anthropic API (bring-your-own-key)* — pay-per-use, paste the key in
    Settings.
  * *Claude Code CLI* — reuses a Claude Code / Max subscription already on the
    server: **no API key, no per-call billing**. Ideal for in-house use.

  The provider and model are configurable. No vendor lock-in.
* **Per-network copy** — text generated per network (Facebook, Instagram,
  LinkedIn, X) respecting each network's maximum post length.
* **Push to native publishing** — one click creates scheduled ``social.post``
  records; the native cron publishes and the native calendar shows them.
* **Asynchronous generation** — long AI calls run from a cron queue, never
  blocking the request.
* Multi-company, Odoo 19 privilege-based security, English / Spanish /
  Spanish (Mexico) translations bundled and auto-loaded.

* **AI image generation, two ways** — optionally generate an on-brand image per
  post, from that post's brief and your brand kit (palette, typography, logo):

  * *Vector design by the text model* — the AI draws the graphic and the server
    rasterises it to PNG. **No image API key and nothing billed per image.**
    Ideal for typographic promos and brand cards. (Requires the optional
    ``cairosvg`` Python library; disabled gracefully when absent.)
  * *Photoreal image models (bring-your-own-key)* — OpenAI Images, Google
    Gemini, or any OpenAI-compatible endpoint, with configurable model,
    format (square / portrait / landscape), style, quality and number of
    variants per post. The brief is automatically expanded into a proper
    image prompt, the result is fitted to the exact social format, and your
    logo is composited on top.

AI video (v2) plugs in through the same pluggable media layer.
""",
    "author": "Cristofferson Reyes",
    "maintainer": "XUBAX",
    "company": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Marketing/Social Marketing",
    "version": "19.0.1.3.0",
    "license": "OPL-1",
    "depends": [
        "social",
        "social_facebook",
        "social_instagram",
        "social_linkedin",
        "social_twitter",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/xb_social_ai_planner_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "data/xb_social_ai_provider_data.xml",
        "wizard/xb_social_generate_month_wizard_views.xml",
        "views/xb_social_brand_profile_views.xml",
        "views/xb_social_competitor_views.xml",
        "views/xb_social_ai_provider_views.xml",
        "views/xb_social_plan_item_views.xml",
        "views/xb_social_content_plan_views.xml",
        "views/xb_social_generation_job_views.xml",
        "views/res_config_settings_views.xml",
        "views/xb_social_ai_planner_menus.xml",
    ],
    "images": [
        "static/description/banner.png",
        "static/description/icon.png",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
    "post_init_hook": "_post_init_load_translations",
    "price": 149.00,
    "currency": "USD",
}
