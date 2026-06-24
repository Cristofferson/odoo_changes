===============
Xibo Connector
===============

|badge1| |badge2|

.. |badge1| image:: https://img.shields.io/badge/licence-OPL--1-blue.png
    :alt: License: OPL-1

.. |badge2| image:: https://img.shields.io/badge/Odoo-19.0-714B67.png
    :alt: Odoo 19.0

Manage your Xibo CMS digital signage network directly from Odoo.

The base module of the Xibo Connector Suite. Connects Odoo to your on-premise
(or cloud) Xibo CMS over its REST API and exposes the most common operations:
displays, media library, layouts, datasets, broadcasts and real-time refresh.

Features
========

* OAuth2 client_credentials authentication with automatic token caching
* Multi-server, multi-company
* Sync displays, display groups, layouts and DataSets from Xibo
* **Sync Library metadata** from Xibo (read-only references; no binary download)
* Upload, update and delete Library media (images, videos, audio)
* **Quick Display**: turn any image into a one-click on-screen broadcast
* Schedule layouts via Broadcasts (overlay, fullscreen, ticker)
* Day-of-week and time-of-day filters, plus full recurrence support
* Trigger real-time refresh via the CMS REST API (no port 9505 exposure)
* Open-in-Xibo deep links from every relevant record
* Full audit trail of every Xibo API call (auto-pruned)
* Granular access rights (User / Manager)
* English and Spanish (Mexico) translations

Compatibility
=============

* Odoo 19.0
* Xibo CMS v3.0 or newer

Requirements
============

* Python ``requests``::

    pip install requests

* OAuth2 application in Xibo (Administration → Applications) with:

  - ``Client Credentials`` enabled
  - Scopes set to ``all`` (or granular: library, display, dataset, schedule, layout, displaygroup)
  - ``Owner`` set to your super-admin user

Setup
=====

1. Place the module in your ``addons_path``.
2. Update the apps list and install **Xibo Connector**.
3. Go to **Xibo Signage → Configuration → Servers** and create a server.
4. Enter URL, Client ID, Client Secret and click **Test Connection**.
5. Click **Sync All** to import displays, groups, layouts, datasets and library metadata.

Quick Display
=============

After uploading an image, click the **Quick Display** button to:

1. Auto-create a minimal full-screen Xibo Layout containing the image
2. Schedule it for immediate display on selected screens
3. Optionally set an end time and recurrence

For more complex layouts (multi-region, animations, datasets), open the layout
in Xibo CMS directly with the **Open in Xibo** button.

Add-on modules (sold separately)
================================

* **Xibo Connector — Point of Sale**: thank-you on paid order, cart-add
  notifications, mirror the POS Customer Display.
* **Xibo Connector — Frontdesk**: welcome message on visitor check-in.
* **Xibo Connector — Sale**: thank-you on backend order confirmation.
* **Xibo Connector — eCommerce**: thank-you on website orders.
* **Xibo Connector — HR**: birthday and work-anniversary greetings.
* **Xibo Connector — Anniversary**: client anniversary greetings.
* **Xibo Connector — Daily Feeds**: saint of the day, weather, news, ephemeris.

Support
=======

soporte@xubax.com
