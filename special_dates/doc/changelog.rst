Changelog
=========

19.0.1.6.0 (2026-06)
--------------------

* **Chatter log on the customer.** Whenever a special date is added to
  a contact, a note is now posted automatically in that contact's
  chatter (type icon, type name, date and recurrence), so the partner's
  history reflects when each reminder was created. The message body is
  produced by ``_special_date_log_body`` and the posting by
  ``_log_special_date_on_partner`` on ``xb.wish.reminders``, both
  overridable so add-on/bridge modules can enrich the note (e.g. with
  the source document the date came from). New strings translated to
  es / es_MX.

19.0.1.5.2 (2026-05)
--------------------

* **Translations complete.** Spanish (es) and Spanish-MX (es_MX)
  translations now cover every visible string: field labels, help
  texts, selection values, menus, actions, view body text, and the
  bundled email template. References (``#:`` lines) match the live
  Odoo XML IDs exactly, so the bundled .po files are applied
  immediately on install/upgrade with no manual reload.
* **Auto-reload on every upgrade.** A ``_register_hook`` on
  ``xb.wish.type`` invokes ``TranslationImporter(...overwrite=True)``
  every time the module is loaded — never any "Reload Translations"
  button to click.
* **"Today" menu placed before "Configuration"** under Contacts
  (sequence 2 vs Odoo's Configuration sequence 3).
* Flattened multi-line ``<p>`` texts in the form views so their
  msgids match the bundled .po entries.

19.0.1.4.x (2026-05)
--------------------

* **Live "Today" dashboard.** Replaced the cron-fed
  ``xb.wish.reminders.today`` table with a server action that
  computes due-today reminders live, in Python, every time the menu
  opens. Reminders created today appear immediately.
* **Status fields on every Reminder.**

  * ``Comms Status`` (``✓ 2/2 sent``, ``⏳ 1/3 sent``, ``—``)
  * ``Activities Status`` same idea, for auto-activities.
  * ``Next Occurrence`` showing the upcoming future date.
* **mail.thread + mail.activity.mixin** on
  ``xb.wish.reminders`` — full chatter and activity sidebar on every
  reminder.
* **"Run Daily Cron Now" button** on Reminder Type so admins can
  trigger the full cron flow on demand for testing.
* **Modern Odoo 19 icon** — diagonal vibrant gradient, iOS-style
  squircle, glassmorphism highlight, sparkles, calendar tile with
  drop shadow and accent heart.
* **Modern Selection widget for emojis** — picking the icon of a
  Reminder Type is now a dropdown of 30 curated emojis with
  descriptive labels (🎂 Birthday, 💍 Wedding/Engagement, ...).
* Removed redundant ``mail_template_id`` on the Reminder Type — the
  Communications tab is now the single source of truth.

19.0.1.3.x (2026-05)
--------------------

* **POS popup behaviour redesigned.**

  * Welcome popup at session open showing the list of every customer
    with a special date today.
  * Periodic re-show every N hours (default 3, configurable via the
    ``special_dates.pos_popup_interval_hours`` system parameter).
  * Individual popup when a customer with a date today is selected on
    the current order.
  * Granular per-Reminder-Type control via ``show_in_pos`` flag.
* **Menus consolidated under Contacts.** Sales and Point of Sale
  parent menus removed; everything now lives at
  *Contacts ▸ Special Dates*.
* **Frontend rewrite.** All POS interactions go through async RPC
  after session load; no more ``_load_pos_data_fields`` or
  ``pos.load.mixin`` (those were breaking POS price/tax
  bootstrapping with a ``currency_id`` undefined error).
* OWL Navbar template inheritance removed — replaced with a single
  ``PosStore`` patch that survives Odoo 19 frontend reorganisations.

19.0.1.2.x (2026-05)
--------------------

* **Odoo 19 compatibility pass.**

  * ``res.groups.category_id`` → ``res.groups.privilege``.
  * ``res.groups.users`` → ``res.groups.user_ids``.
  * Removed ``ir.cron.numbercall`` and ``doall`` (removed in 19).
  * Smart-button compute methods made public (no leading underscore).
  * ``<group expand="0" string="Group By">`` removed from search
    views (Odoo 19 search panels can't parse it).
  * ``view_mode`` set to ``list`` instead of ``tree``.
  * ``target="inline"`` replaced with ``target="current"``.

19.0.1.1.0 (2026-05)
--------------------

* **Multi-channel communication schedule** per Reminder Type.
  Stack as many lines as you need (Email -7d, SMS -1d, Email day-of).
  Each line records its own ``last_sent`` and ``sent_count``.
* **Auto-activities.** Configure any ``mail.activity.type`` (Call,
  Email, To-Do, Meeting, custom) to be created on the customer's
  record when the date arrives.
* **Optional WhatsApp channel** through the companion add-on
  ``special_dates_whatsapp`` (auto-installs when Odoo's ``whatsapp``
  module is present).

19.0.1.0.0 (2026-05)
--------------------

* Initial release for Odoo 19.
* Models, security, multi-company rules, OWL POS popup, daily cron,
  Spanish translations, marketing assets for apps.odoo.com.
