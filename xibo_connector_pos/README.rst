==============================
Xibo Connector — Point of Sale
==============================

.. |badge1| image:: https://img.shields.io/badge/license-OPL--1-blue.png
   :target: https://www.odoo.com/documentation/19.0/legal/licenses.html
.. |badge2| image:: https://img.shields.io/badge/Odoo-19.0-714B67.png
.. |badge3| image:: https://img.shields.io/badge/Xibo-3.x%20%E2%80%94%204.x-success.png

|badge1| |badge2| |badge3|

Turn your Xibo digital signage screens into a live extension of your
Point of Sale. Four production-ready scenarios — each independently
enabled per POS configuration:

1. **AI Thank-You on paid order** — a personalized, AI-generated thank-you
   message appears on the configured screens the moment payment closes.
   Choose from three built-in visual presets (Minimal, Warm, Bold) or
   paste your own HTML.
2. **Dynamic Customer Display Mirror** — when a product is added to the
   cart, a target screen switches from its normal schedule to mirror the
   Odoo POS Customer Display in real time. When the cart is cleared, the
   screen reverts to its normal content.
3. **Contextual product recommendations** — when a tagged product is added
   to the cart, matching Xibo media (videos, images) plays automatically.
   Tags are configured per product category, optionally overridden per
   product. A configurable cool-down prevents on-screen spam.
4. **Cart-add notifications** — optional overlay/ticker when any product
   is added to the cart.

Why this connector exists
=========================

Xibo is excellent at scheduled content. POS sales are the opposite —
**unscheduled, event-driven, contextual to each customer**. This module
bridges that gap by translating POS events into XMR (Xibo Message
Relay) commands and serving fresh HTML at the moment each event
happens. No cron polling, no display-side cache lag.

Requirements
============

* ``xibo_connector`` (base, sold separately on apps.odoo.com)
* ``point_of_sale``
* ``product``
* ``ai`` (Odoo native AI infrastructure)

The connector uses Odoo's native AI infrastructure (``ir.actions.server``
with ``evaluation_type='ai_computed'``) for message generation. It works
out of the box with whichever LLM provider you have configured in Odoo —
OpenAI today, future providers automatically as Odoo adds support.

Architecture in one paragraph
=============================

On every paid order, an Odoo background thread (launched via
``cr.postcommit`` so it never blocks the cashier UI) renders the AI
message, writes a transient ``xibo.thanks.render`` record, then sends an
XMR ``changeLayout`` to each configured screen. The screen's Thank-You
Layout contains a single Webpage widget pointing at
``/xibo/thanks/<pos_config_id>`` on this Odoo server. The endpoint
returns a freshly-styled HTML page with ``Cache-Control: no-cache``, so
the player always shows the latest message — no cache lag, no stale
data, no DataSet refresh cycles to wait for.

Setup
=====

1. **Install** the base ``xibo_connector`` module and configure your Xibo
   Server (Xibo Signage → Configuration). Make sure the connector
   reports the server as ``Connected``.

2. **Install** this module (``xibo_connector_pos``).

3. **Per POS configuration** (POS → Configuration → Point of Sale →
   *select your config* → Settings → scroll to the Xibo Signage block):

   a. Pick the **Xibo Server**.
   b. Set the **Active Time Window** (the connector only fires events
      between these hours — perfect for "9–18 store hours only").
   c. Pick the **Default Displays / Display Groups** used by Camino A
      (legacy Broadcast fallback) and by Recommendations.
   d. Enable any scenario you want and configure it.

AI Thank-You scenario
=====================

This is the flagship scenario. Setup steps:

1. **Create a Thank-You Layout in Xibo CMS** (1920×1080, blank
   background). Add ONE Webpage widget filling the full canvas and set
   its URL to::

        https://YOUR-ODOO-DOMAIN/xibo/thanks/<POS_CONFIG_ID>

   Replace ``<POS_CONFIG_ID>`` with the integer ID of your ``pos.config``
   (visible in the URL when you edit it in Settings, or via the
   developer tools).

   **Important**: in the Webpage widget settings, set Cache to "Always
   re-fetch from server" (or the equivalent zero-cache setting). The
   widget MUST fetch the URL on every layout activation. The Odoo
   endpoint already sends ``Cache-Control: no-cache``, but some Xibo
   versions still cache aggressively unless explicitly told not to.

2. **Publish** the Layout.

3. **Sync displays** in Odoo (Xibo Signage → Servers → *your server* →
   Sync All) so the new Layout appears in your dropdowns.

4. **In POS Settings → Xibo Signage → ① AI Thank-You**:

   * Enable the toggle.
   * Pick the **Thank-You Layout in Xibo** (the one you just created).
   * Pick the **Target Screens**.
   * Set **Display For (s)** — how long the message stays on screen
     before Xibo auto-reverts to the normal schedule. 15–25 seconds is
     ideal; 30+ feels long.
   * Set **Minimum Order Total** (0 = always fire).
   * Configure the **AI Prompt Template** in the language you want the
     messages produced in. The default is in Spanish; rewrite it to suit
     your store's voice. Variables: ``{customer_name}``, ``{top_product}``,
     ``{top_category}``, ``{total}``, ``{currency}``, ``{product_list}``.
   * Set a **Fallback Message** for when the AI is unreachable.
   * Pick a **Visual Preset** (or ``Custom HTML`` and paste your own).
   * Optionally enable **Show Top Product Image**.

5. **Preview** your design at::

        https://YOUR-ODOO-DOMAIN/xibo/thanks/<POS_CONFIG_ID>/preview

   This authenticated endpoint renders the chosen preset with sample
   data so you can fine-tune before going live.

6. **Test**: make a small sale on the POS and watch the screen. The
   message should appear within ~3-5 seconds of payment and auto-revert
   after the configured duration.

Visual presets
==============

* **Minimal** — clean, light background, thin typography, animated check
  mark. Best for boutiques, pharmacies, modern retail.
* **Warm** — gold accents, serif typography, soft bloom animation. Best
  for jewelers, perfumeries, gift shops.
* **Bold** — black background, big uppercase, slide-in animation. Best
  for fast-paced retail, sportswear, electronics.
* **Custom HTML** — bring your own design. Use ``{{message}}``,
  ``{{customer_name}}``, ``{{top_product}}``, ``{{product_image_url}}``,
  ``{{total}}``, ``{{currency}}``, ``{{company_name}}``,
  ``{{company_logo_url}}`` placeholders.

All built-in presets are pure HTML+CSS, 1920×1080 native with fluid units
so they scale to any aspect ratio. No external fonts, no JS, no CDN — they
render even if the Xibo player's internet is restricted to your Odoo
server.

Customer Display Mirror scenario
================================

When enabled, the connector watches POS events. On the first product
added to the cart, the target Xibo screen switches to mirror the Odoo
POS Customer Display URL. When the cart is cleared (payment validated or
canceled), the screen reverts to its normal schedule.

Setup:

1. Enable the toggle in POS Settings.
2. Pick the **Customer Display Screen**.
3. Click **Apply in Xibo Now**. The connector creates the Xibo Layout
   automatically and schedules it on the screen.

The mirror works best on **Xibo Player for Windows or Linux**. Android,
webOS and Tizen players have stricter cookie policies that may break
Odoo's session-scoped Customer Display URL.

Contextual recommendations scenario
===================================

1. In Xibo: **tag your media files** (e.g. ``tv``, ``electronics``,
   ``accessories``, ``rings``, ``baby``).
2. In Odoo: open **product categories** and set the same tags in *Xibo
   Recommendation Tags* (comma-separated). For example, the category
   "Engagement Rings" might be tagged ``rings, romance, wedding``.
3. Optionally override on **specific products** in their *Xibo Signage*
   tab — useful for hero items.
4. Tune the **cool-down** (default 60 s) to avoid one customer
   triggering the same media multiple times.

Customer privacy
================

Each contact has a **Show on Public Screens** toggle (default off, set in
base module). When disabled, the on-screen message uses a generic
greeting ("valued customer") instead of the real name. This is GDPR-
friendly: you're free to display personalized messages only for opted-in
customers.

Troubleshooting
===============

**The screen doesn't change after payment.**

* Check ``/var/log/odoo/odoo-server.log`` and grep for ``[XIBO POS THANKS]``.
  Each step of the pipeline logs its outcome. If you see
  ``proceed`` and ``dispatched: N successes`` but the screen doesn't
  change, the XMR reached the CMS but the player isn't applying it —
  look at the player's local log.
* Verify the Layout has been **Published** in Xibo (status column in
  the Layouts list must say ``Published``, not ``Draft``).
* Verify the ``xibo_layout_id`` on the Odoo side matches the published
  layout ID. After re-publishing a Layout in Xibo, run ``Sync All`` from
  the connector.

**The on-screen message shows a stale Thank-You from minutes ago.**

* The Webpage widget in your Thank-You Layout must have caching
  disabled. Open the widget in Xibo, find the "Cache" or "Update
  Interval" setting, and set it to its minimum (0 if available).
* The Odoo endpoint already sends ``Cache-Control: no-cache``, so once
  the widget setting is right, the message is always fresh.

**The AI message is in English when I want Spanish (or vice versa).**

* The AI follows the language of YOUR prompt template. Rewrite the
  prompt in your target language with explicit instruction "respond in
  Spanish".
* Optionally configure ``xibo_thanks_ai_agent_id`` to use an Odoo AI
  Agent with a language-specific system prompt.

**The race condition crash in the log (``could not serialize access
due to concurrent update``).**

* Cosmetic only. The Thank-You broadcast already completed successfully;
  the message is just the second runner thread losing the lock. This
  does not affect on-screen rendering or duplicate the broadcast.

Support
=======

* Email: soporte@xubax.com
* Website: https://www.xubax.com
* Repository: contact us for source-code access (OPL-1)

Credits
=======

* Author: Cristofferson Reyes Rodriguez (XUBAX)
* License: OPL-1
