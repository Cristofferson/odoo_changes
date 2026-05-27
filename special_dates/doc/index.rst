Special Dates
=============

A complete reminder system for the special dates of your customers and
contacts — birthdays, anniversaries, contract renewals, festivals or any
custom recurring event. Built for Odoo 19, fully integrated with the
Contacts app and the Point of Sale.

Features
--------

* Unlimited reminder types (Birthday, Anniversary, Renewal, ...).
* Three recurrence modes: day of the week, every N days, or every year.
* **Multi-channel communication schedule per type:** stack Email, SMS
  and WhatsApp messages with their own offsets ("7 days before",
  "1 day before", "on the day"). Each line tracks its own counter.
* **WhatsApp** support via the optional companion add-on
  (``special_dates_whatsapp``), auto-installed when the Odoo ``whatsapp``
  module is present.
* **Auto-activities:** schedule a Call, Email, To-Do or any custom
  activity on the responsible user (salesperson, creator, fixed user,
  current user) when the date arrives or N days before/after, with
  native Odoo notifications.
* Daily cron processes every reminder, schedule line and activity.
* **Live "Today" dashboard** under Contacts ▸ Special Dates that
  computes due-today reminders in real time (no waiting for the cron).
* Per-reminder **status fields** (Comms Status, Activities Status,
  Next Occurrence) for fast auditing.
* Full **chatter** on every reminder.
* Reminder lines embedded directly inside the contact form.
* **Point of Sale popups:** welcome at session open + periodic re-show
  every N hours + individual popup when a customer with a date today
  is selected on the order.
* Multi-company aware (per-company record rules).
* Compatible with the Mexican localization (l10n_mx) and any other.
* English, Spanish, Spanish (Mexico) translations bundled.

Configuration
-------------

1. Install the module ``Special Dates``. The Spanish translations apply
   automatically.
2. Go to **Contacts ▸ Special Dates ▸ Reminder Types**.
3. Create the reminder types you need (Birthday, Anniversary, etc.):

   * Open a type, pick an emoji icon, set the default recurrence
     (Every Year / Every N Days / Day of the Week).
   * Check **Show Popup in Point of Sale** if you want this type to
     trigger the POS popup.
   * Switch to the **Communications** tab. Add one line per message —
     pick the channel (Email / SMS / WhatsApp if installed), the
     interval (Immediately / N hours / N days / N weeks / N months),
     the trigger (Before / On / After the date), and the template.
   * Switch to the **Auto-Activities** tab to schedule activities on
     the responsible user.

4. The pre-installed *Default Greeting* email template is ready to use,
   or create your own under **Settings ▸ Technical ▸ Email Templates**.

Usage
-----

* From the customer / contact form, open the **Special Dates** tab and
  add a line per reminder.
* Browse all reminders at **Contacts ▸ Special Dates ▸ Reminders**.
* See today's load at **Contacts ▸ Special Dates ▸ Today** — the list
  is computed live every time you open it.
* The scheduled action ``Special Dates: Send Daily Reminders`` runs
  every day; you can also run it manually from any Reminder Type with
  the **Run Daily Cron Now** button, or from
  **Settings ▸ Technical ▸ Scheduled Actions**.

Point of Sale
-------------

* **Welcome popup**: when a cashier opens a POS session, a popup
  appears listing every customer with a special date today.
* **Periodic re-show**: the popup re-appears every N hours
  (default 3, configurable via the system parameter
  ``special_dates.pos_popup_interval_hours``) while the session is open.
* **Individual popup**: when a cashier sets a customer on the current
  order, the module checks for active reminders due today; if any are
  found, an elegant popup shows the reminder name and emoji.
* Granular control per Reminder Type via the **Show Popup in Point of
  Sale** boolean — useful to silence specific types from the POS while
  keeping their emails and activities.

Bug Tracker
-----------

Issues are tracked at https://www.xubax.com/support — please include
the full traceback when reporting a problem.

Credits
-------

Author: Cristofferson Reyes — XUBAX
