Special Dates
=============

Never miss a customer's birthday, anniversary or special day.
Automatic Email / SMS / WhatsApp reminders, auto-activities, and
Point of Sale popups for Odoo 19.

* Author: **Cristofferson Reyes** (XUBAX)
* License: OPL-1 (proprietary)
* Compatible with: **Odoo 19 Enterprise** and **Community**

Installation
------------

1. Copy the ``special_dates`` folder into your Odoo addons path
   (e.g. ``/odoo/custom-addons``).
2. Restart the Odoo server::

       sudo service odoo-server restart

3. Activate developer mode and update the app list.
4. Search for *Special Dates* in **Apps** and click **Install**.

After installation, every option lives under **Contacts ▸ Special Dates**:

* **Reminders** — every special date currently configured.
* **Today** — live list of reminders due today.
* **Reminder Types** — Birthday, Anniversary, Renewal, etc., with their
  per-channel schedule (Email / SMS / WhatsApp) and auto-activities.

Reminders are also accessible as a **Special Dates** tab inside every
Contact form.

Point of Sale
-------------

* When the cashier opens a POS session, a welcome popup lists every
  customer with a special date today.
* The popup re-appears every N hours (configurable via the
  ``special_dates.pos_popup_interval_hours`` system parameter, default
  ``3``) while the session stays open.
* When the cashier picks a customer with a date today, an individual
  celebratory popup appears on the order.

Translations
------------

Spanish (``es``) and Spanish (Mexico) (``es_MX``) translations are
included and applied automatically on install and on every upgrade —
no manual reload required.

Support
-------

Bug reports & feature requests: soporte@xubax.com
