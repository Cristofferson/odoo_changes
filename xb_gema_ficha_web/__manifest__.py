# -*- coding: utf-8 -*-
{
    "name": "Gems - Product page: certificates and gem gallery",
    "summary": "Gem product page shows the certificate of each lab the gem "
               "has, hides empty rows and puts the gem photos and video in "
               "the product gallery.",
    "description": """
Gems - Product page: certificates and gem gallery
=================================================
Replaces the gem data tables of the product page (the old database view
``xb_gemas.ficha_gema_producto``, archived on install and restored on
uninstall):

* The "Certificate" table is repeated for every lab in "Certificado(s)"
  (DIAMANE, GIA, IGI, AGS, EGL, HRD, GRA, GCAL, GSI) reading that lab's own
  fields. Before, it always read the DIAMANE fields.
* "Hearts and Arrows" reads its own field (it was reading "Fire").
* Rows without data are hidden.
* Shop category and menu "Diamantes" (anello.mx): gems of type Diamante
  tracked by serial number get it automatically (accent stones do not); "/shop" without category or search no longer
  lists them.
* The gem video ("Video", ``x_studio_video``) is always saved without
  sound: on every upload the audio track is removed with ffmpeg (video
  copied as is, no re-encoding). Needs ``ffmpeg``/``ffprobe`` on the
  server; if they fail the video is saved unchanged and a warning logged.
* Layout E: the 4Cs as visual scales (a value outside its scale, e.g. cut
  "N/A", shows as a plain row) and the rest in clean tables, "Brillo y
  simetría" in two columns. The lab images (ASET, IdealScope, hearts and
  arrows, clarity plot, fluorescence...) show inside the "i" balloon of
  their field. Every field has an
  "i" button with what it means; the texts are edited in Website >
  Configuration > "Ficha de gema: explicaciones" (empty text = no button).

The gem photos (Imagen 1-4, measures, clarity plot, hearts, arrows, ASET,
IdealScope, fluorescence...) and the gem video are mirrored as "Extra
Product Media" so the product gallery shows them. They are kept in sync
when the gem fields change. The video is served by
``/xb_gema_ficha_web/video/<template id>`` (published gems or internal
users only).
""",
    "author": "XUBAX",
    "maintainer": "XUBAX",
    "website": "https://www.xubax.com",
    "support": "soporte@xubax.com",
    "category": "Website/eCommerce",
    "version": "19.0.1.4.2",
    "license": "LGPL-3",
    "depends": ["website_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/xb_gema_ayuda_data.xml",
        "views/xb_gema_ayuda_views.xml",
        "data/product_public_category_data.xml",
        "views/ficha_gema_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "xb_gema_ficha_web/static/src/scss/ficha_gema.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "application": False,
    "installable": True,
}
