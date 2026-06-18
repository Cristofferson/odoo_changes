# -*- coding: utf-8 -*-
"""xb_social_ai_planner - module bootstrap.

Auto-loads Spanish translations from i18n/*.po on install via the manifest's
`post_init_hook` (same pattern as the `special_dates` module).
"""
import logging
import os

from . import models
from . import wizard

_logger = logging.getLogger(__name__)

_MODULE = "xb_social_ai_planner"


def _load_translations_overwrite(env):
    """Force-reload the module's bundled .po files with overwrite=True."""
    try:
        from odoo.modules import get_module_path
        module_path = get_module_path(_MODULE)
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
                    "[%s] Auto-loaded %d .po file(s) via TranslationImporter "
                    "(overwrite=True)", _MODULE, loaded,
                )
                return
        except ImportError:
            pass

        modules = env["ir.module.module"].sudo().search([
            ("name", "=", _MODULE),
            ("state", "=", "installed"),
        ])
        if modules and target_langs:
            modules.with_context(
                overwrite=True,
                overwrite_existing_translations=True,
            )._update_translations(filter_lang=target_langs)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("[%s] Translation auto-reload failed: %s", _MODULE, exc)


def _post_init_load_translations(env):
    """Runs once on module install."""
    _load_translations_overwrite(env)
