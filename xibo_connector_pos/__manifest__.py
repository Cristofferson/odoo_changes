# -*- coding: utf-8 -*-
{
    'name': 'Xibo Connector — Point of Sale',
    'version': '19.0.1.5.33',
    'category': 'Marketing/Digital Signage',
    'summary': 'AI thank-you with audio, dynamic customer display mirror, and contextual product recommendations on Xibo from your POS.',
    'description': """
Xibo Connector — Point of Sale
==============================

AI Thank-You (with optional audio) + Dynamic Customer Display Mirror +
Contextual Recommendations for POS via Xibo CMS.

Changelog
---------
19.0.1.5.33 (2026-06)
~~~~~~~~~~~~~~~~~~~~~
* **Privacy — optional access key on the Thank-You page**. The public
  ``/xibo/thanks/<id>`` endpoint was keyed only by a guessable integer, so
  anyone could read the last customer name + product. A per-POS secret key
  is now supported via ``?key=<token>``. Enforcement is **OFF by default**
  (``xibo_thanks_require_token``) so upgrading breaks nothing: update each
  screen's Webpage widget URL to the one shown in Settings (it includes the
  key), then turn the switch ON. Bad/missing key serves the neutral fallback
  page — never data, never an error.
* **Security — healthcheck closed by default**. ``/xibo/healthcheck`` no
  longer leaks module version, Xibo connectivity, AI availability or render
  counts to the public internet. It returns 404 unless the secret
  ir.config_parameter ``xibo_connector_pos.healthcheck_token`` is set and
  passed as ``?token=<secret>``.

19.0.1.5.31 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* **New feature — optional audio notification on Thank-You**. Configurable
  per POS. Four built-in synthetic audio presets (chime / cash / success /
  bell, ~10-22KB each, royalty-free) plus a custom URL option for clients
  who want their own sound. Volume slider (0-100). The audio plays inside
  the Webpage widget's HTML5 ``<audio autoplay>`` element, perfectly synced
  with the visual animation.
* **Defensive schema validation via pre_init_hook**. When the module is
  upgraded in-place (just dropping new files and restarting Odoo, without
  going through Apps -> Upgrade), the new Python code expects columns that
  Odoo hasn't created yet, causing ``UndefinedColumn`` errors on the next
  sale. The pre_init_hook now runs ``ALTER TABLE ADD COLUMN IF NOT EXISTS``
  for every field the latest version declares on ``pos_order`` and
  ``pos_config``. Fully idempotent; safe to run repeatedly.
* **Migration script for v1.5.31**. ``migrations/19.0.1.5.31/post-migration.py``
  normalises the new audio fields on existing pos.config rows (default
  audio_enabled=False so no surprise sounds for upgraders, audio_preset='chime',
  audio_volume=80).
* **New endpoint — /xibo/healthcheck**. Returns a JSON diagnostic showing
  schema integrity, Xibo server connectivity, AI agent availability, and
  active render count. Useful for monitoring tools and customer support.
* **Renamed admin preview endpoint**. The old ``/xibo/thanks/<id>/preview``
  is now ``/xibo/thanks/<id>/admin-preview`` to prevent the
  most-common-customer-misconfiguration: pasting the admin preview URL
  into the Xibo Webpage widget (which then redirected the player to a
  login page). The old ``/preview`` URL still works as a deprecated alias
  but logs a warning so admins notice.
* **Friendly error pages**. Controller catches exceptions and serves a
  branded HTML fallback instead of a raw Werkzeug traceback. The fallback
  message stays generic in production to avoid leaking implementation
  details.

19.0.1.5.30 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* **Critical bugfix — v1.5.29's up-front flag set blocked itself**. The
  v1.5.29 fix set ``xibo_thanks_sent=TRUE`` via raw SQL BEFORE calling
  ``_xibo_send_thanks``. But that method's first check is "if
  xibo_thanks_sent: skip" — which now ALWAYS triggered because we just
  set it ourselves. Net effect: NOTHING ever happened on Thank-You.
  Orders ended with the flag True but no AI message, no render, no XMR.
  Fix: the runner now passes ``xibo_skip_sent_check=True`` in the
  context when calling ``_xibo_send_thanks``, and that check is
  conditional on the absence of that context flag.

19.0.1.5.29 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* **Critical bugfix — race condition allowed the second thread to do
  the work twice**. The previous v1.5.28 lock acquired correctly, but
  the dedup flag (``xibo_thanks_sent``) was only set AFTER the
  Thank-You broadcast completed inside ``_xibo_send_thanks`` — too
  late: the second thread woke up from the lock, re-read the flag,
  saw False (because the flag was set via ORM ``write()`` deferred to
  commit time), and proceeded to do all the work again, fighting with
  the first thread's AI server action over the same row. Result: PG
  ``could not serialize access`` and a second render published over
  the first one. Fix: the runner now writes the flag via raw SQL
  ``UPDATE pos_order SET xibo_thanks_sent=TRUE WHERE id=%s`` BEFORE
  doing any work. The other thread wakes up and sees the new flag
  immediately. No more double-firing.

19.0.1.5.28 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* **Critical bugfix — preset HTML rendering crashed with KeyError 'margin'**.
  The preset templates contain inline CSS rules like ``body{margin:0}``
  whose curly braces collided with Python's ``str.format()`` placeholder
  syntax, raising ``KeyError`` on the very first CSS rule. The endpoint
  silently fell back to the "Gracias por su visita" neutral page on
  every request. Replaced ``.format()`` with direct ``.replace()`` of
  named tokens — CSS curly braces are now left intact.
* **Critical bugfix — race condition crash on every Thank-You sale**.
  The dedup ``SELECT ... FOR UPDATE`` was triggering PostgreSQL
  ``could not serialize access due to concurrent update`` under
  REPEATABLE READ isolation (Odoo's default). The race protection still
  worked (the Thank-You only fired once) but the log showed a scary
  ERROR after every sale. Replaced with ``pg_advisory_xact_lock`` — a
  lightweight, isolation-friendly lock keyed on the order id, namespaced
  to avoid collisions with core Odoo or other modules.

19.0.1.5.27 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* **Major rework — URL-render flow replaces DataSet for AI Thank-You**.

  Previous versions pushed the AI-generated message into a Xibo DataSet
  and let the player's ticker widget read from it. In practice this never
  worked reliably: the player caches DataSets and refreshes them only
  every N minutes (the smallest interval is too long for a real-time
  Thank-You). The on-screen message lagged minutes behind the actual sale.

  The new architecture removes the DataSet from the path entirely:

  1. When an order is paid, the connector creates a record in a new
     ``xibo.thanks.render`` table holding the message body, customer name,
     top product, total, and chosen visual preset.
  2. An XMR ``changeLayout`` switches the target screens to the Thank-You
     Layout, which contains a single ``Webpage`` widget pointing at
     ``/xibo/thanks/<config_id>`` on this server.
  3. The Webpage widget reloads on every layout activation. The endpoint
     responds with ``Cache-Control: no-cache`` and serves a fresh HTML
     page rendered from the most recent ``xibo.thanks.render`` record.

  Result: the on-screen message ALWAYS matches the sale that just
  happened. No more cache lag, no more stale messages.

* **Three built-in visual presets** for instant deployment:

  * ``Minimal`` — clean, lots of whitespace, animated check mark,
    soft fade-in. Default.
  * ``Warm`` — jewelry-friendly, gold accents, serif typography,
    ornament glyph, soft bloom animation.
  * ``Bold`` — high contrast, big text, energetic slide-in,
    cinema-like background pulse.

  All presets are 1920×1080 native with fluid units for any aspect ratio.
  All are pure CSS — no external fonts, no JS, no CDN — so they render
  even when the Xibo player has limited connectivity beyond the Odoo
  server it's already reaching.

* **Custom HTML preset** for full creative control. The cashier pastes
  their own HTML/CSS and references dynamic values via simple
  placeholders: ``{{message}}``, ``{{customer_name}}``, ``{{top_product}}``,
  ``{{product_image_url}}``, ``{{total}}``, ``{{currency}}``,
  ``{{company_name}}``, ``{{company_logo_url}}``.

* **Optional product image**: a single boolean
  (``xibo_thanks_show_product_image``) toggles a photo of the most
  expensive product in the order. The image is served as
  ``/web/image/product.product/<id>/image_1024`` so it goes straight from
  Odoo's Media library to the screen.

* **Admin preview endpoint** at ``/xibo/thanks/<config_id>/preview`` (auth
  required). Renders the chosen preset with sample data so admins can
  fine-tune their Custom HTML without making a sale.

* **GC cron**: ``xibo.thanks.render`` records older than 1 hour past
  expiry are purged every 30 minutes. Lightweight, single indexed query.

* **Legacy compatibility**: the old ``xibo_thanks_dataset_id`` field is
  preserved but marked deprecated; it is still used by the Camino A
  (Broadcast) fallback path for setups without target screens.

19.0.1.5.26 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* Provider-agnostic AI via the native Odoo ``ai_computed`` server action
  mechanism. Works with whichever LLM provider the customer has
  configured (OpenAI today, future providers automatically).

19.0.1.5.25 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* Anti-double-dispatch race condition guard via ``SELECT FOR UPDATE`` on
  the order row.

19.0.1.5.24 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* Thread launched on post-commit, not inside the current transaction.

19.0.1.5.23 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* Diagnostic instrumentation across the Thank-You pipeline.

19.0.1.5.22 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* Critical bugfix: removed obsolete ``Environment.manage()`` call.

19.0.1.5.21 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* AI Thank-You direct XMR (deprecated approach, kept for transition).

19.0.1.5.20 (2026-05)
~~~~~~~~~~~~~~~~~~~~~
* Customer Display Mirror end-to-end with real-time cart sync via shared
  ``device_uuid`` in the websocket bus.
* In-memory ``_xibo_mirror_active`` deduplicates XMR calls on every product add.
    """,
    'author': 'Cristofferson Reyes Rodriguez',
    'maintainer': 'Cristofferson Reyes Rodriguez',
    'website': 'https://www.xubax.com',
    'support': 'soporte@xubax.com',
    'license': 'OPL-1',
    'price': 8.00,
    'currency': 'USD',
    'pre_init_hook': 'pre_init_check_schema',
    'depends': ['xibo_connector', 'point_of_sale', 'product', 'ai'],
    'data': [
        'security/ir.model.access.csv',
        'data/ai_server_actions.xml',
        'data/ir_cron.xml',
        'views/pos_config_views.xml',
        'views/product_category_views.xml',
        'views/product_template_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'xibo_connector_pos/static/src/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
