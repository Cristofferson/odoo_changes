===============================
XUBAX AI Social Content Planner
===============================

AI-powered monthly content planner and strategist that complements Odoo 19
Enterprise **Social Marketing**. Generates the full strategy (themes, copy,
CTA, hashtags) with Claude (or your own provider) and pushes approved posts
into the native ``social.post`` pipeline for publishing.

Requirements
============
* Odoo 19 Enterprise with Social Marketing (``social`` and the network modules
  ``social_facebook``, ``social_instagram``, ``social_linkedin``,
  ``social_twitter``).
* An AI provider API key (Claude by default). Set it in
  *Settings ▸ AI Social Planner*. Alternatively, point the provider at a
  Claude Code CLI already installed on the server and use no key at all.
* Python ``requests`` (ships with Odoo).
* Optional, for images only:

  * key-free vector images need the ``cairosvg`` Python library;
  * photoreal images need an image API key (OpenAI or Gemini) in
    *Settings ▸ AI Social Planner ▸ AI Image API Key*.

Quick start
===========
1. Install the module. Open **AI Social Planner**.
2. *Configuration ▸ Settings* — paste your AI API key.
3. Create a **Brand Profile** (voice, audience, keywords).
4. **Generate Month** — pick the brand, month and accounts. The AI builds the
   strategy and queues per-post copy (processed by a cron every couple of
   minutes).
5. Review/approve the posts, then **Push Approved** — they become scheduled
   ``social.post`` records and publish through Odoo's native pipeline.

Images
======
Fill the **Brand Kit** tab of the brand profile (logo, palette, typography,
visual style), then choose an **Image Provider** on the AI provider:

* *Vector design by the text model* — no image key, nothing billed per image.
  On-brand typographic graphics and promo cards.
* *OpenAI Images* / *Google Gemini* — photoreal imagery, billed per image by
  the provider. Set the format, style, quality and how many variants to
  generate per post so an editor can pick.

Either way the image is fitted to the social format and your logo is
composited on top, then attached to the post.

License: OPL-1. Author/Maintainer: XUBAX — https://www.xubax.com
