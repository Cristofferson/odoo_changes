# -*- coding: utf-8 -*-
"""special_dates - module bootstrap.

Auto-loads Spanish translations from i18n/*.po:
 - On install: via the manifest's `post_init_hook`.
 - On upgrade: via the `post_load` hook in __manifest__.py.
"""
import logging
import os

from . import models

_logger = logging.getLogger(__name__)


def _load_translations_overwrite(env):
    """Force-reload special_dates' bundled .po files with overwrite=True."""
    try:
        from odoo.modules import get_module_path
        module_path = get_module_path("special_dates")
        if not module_path:
            return
        lang_obj = env["res.lang"].with_context(active_test=False)
        target_langs = []
        for code in ("es_MX", "es"):
            lang = lang_obj.search([("code", "=", code)], limit=1)
            if not lang:
                continue
            if not lang.active:
                lang.sudo().active = True
            target_langs.append(code)

        # Preferred: Odoo 17+ TranslationImporter
        try:
            from odoo.tools.translate import TranslationImporter
            importer = TranslationImporter(env.cr, verbose=False)
            loaded = 0
            for code in target_langs:
                po_path = os.path.join(module_path, "i18n", "%s.po" % code)
                if os.path.exists(po_path):
                    importer.load_file(po_path, code)
                    loaded += 1
            if loaded:
                importer.save(overwrite=True)
                _logger.info(
                    "[special_dates] Auto-loaded %d .po file(s) "
                    "via TranslationImporter (overwrite=True)", loaded
                )
                return
        except ImportError:
            pass

        # Fallback: legacy _update_translations
        modules = env["ir.module.module"].sudo().search([
            ("name", "=", "special_dates"),
            ("state", "=", "installed"),
        ])
        if modules and target_langs:
            modules.with_context(
                overwrite=True,
                overwrite_existing_translations=True,
            )._update_translations(filter_lang=target_langs)
            _logger.info(
                "[special_dates] Auto-loaded translations via legacy "
                "_update_translations (langs=%s)", target_langs
            )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "[special_dates] Translation auto-reload failed: %s", exc
        )


def _post_init_load_translations(env):
    """Runs once on module install."""
    _load_translations_overwrite(env)
