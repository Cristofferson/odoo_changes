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
  *Settings ▸ AI Social Planner*.
* Python ``requests`` (ships with Odoo).

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

License: OPL-1. Author/Maintainer: XUBAX — https://www.xubax.com
