# -*- coding: utf-8 -*-
{
    "name": "Special Dates – Birthdays, Anniversaries & Date Reminders",
    "summary": "Never miss a customer's birthday, anniversary or special day. "
               "Multi-channel reminders (Email/SMS/WhatsApp), auto-activities, "
               "Point of Sale popup integration.",
    "description": """
Special Dates
=============

Track and celebrate every important date of your customers and contacts:
birthdays, anniversaries, contract renewals, festivals and any custom
recurring event. Reminders live inside the **Contacts** app and trigger
celebratory popups directly in the **Point of Sale** so your team never
misses an opportunity to delight a customer.

Key features
------------
* Unlimited reminder types (Birthday, Anniversary, Renewal, ...).
* Recurrence by day of the week, every N days or every year.
* Multi-channel communication schedule per Reminder Type:
  send an Email N days before, an SMS the day before, etc.
* WhatsApp channel available via the optional add-on
  ``special_dates_whatsapp`` (auto-installed when both ``special_dates``
  and Odoo ``whatsapp`` modules are present).
* Auto-activities: schedule a Call, an Email, a To-Do or any other
  ``mail.activity`` type on the responsible user when the date arrives,
  with native Odoo notifications.
* Daily cron processes every reminder, schedule line and activity.
* **Live "Today" dashboard** under Contacts ▸ Special Dates that shows
  every reminder due today with comms/activities status.
* Reminder lines embedded as a tab in the contact form.
* **Point of Sale popups**:

  * Welcome popup when the cashier opens the POS session listing every
    customer with a special date today.
  * Periodic re-show every N hours (configurable) while the session is
    open.
  * Individual popup when a customer with a date today is picked on
    the current order.
* Compatible with Mexican localization and multi-company setups.
* Includes English, Spanish and Spanish (Mexico) translations.
""",
    "author": "Cristofferson Reyes",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Sales/Sales",
    "version": "19.0.1.5.5",
    "license": "OPL-1",
    "depends": [
        "base",
        "mail",
        "contacts",
        "point_of_sale",
        "sms",
    ],
    "data": [
        "security/special_dates_security.xml",
        "security/ir.model.access.csv",
        "data/special_dates_email_template.xml",
        "data/ir_cron_data.xml",
        "views/xb_wish_schedule_views.xml",
        "views/xb_wish_activity_views.xml",
        "views/xb_wish_type_views.xml",
        "views/xb_wish_reminders_views.xml",
        "views/xb_wish_reminders_today_views.xml",
        "views/res_partner_views.xml",
        "views/special_dates_menus.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "special_dates/static/src/js/pos/pos_store.js",
            "special_dates/static/src/js/pos/partner_reminder_popup.js",
            "special_dates/static/src/js/pos/today_reminders_popup.js",
            "special_dates/static/src/xml/partner_reminder_popup.xml",
            "special_dates/static/src/xml/today_reminders_popup.xml",
            "special_dates/static/src/scss/pos_reminder.scss",
        ],
    },
    "images": [
        "static/description/banner.png",
        "static/description/icon.png",
    ],
    "application": True,
    "installable": True,
    "auto_install": False,
    "post_init_hook": "_post_init_load_translations",
    "price": 18.00,
    "currency": "USD",
}
