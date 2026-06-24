# -*- coding: utf-8 -*-
"""Post-migration for v19.0.1.5.31.

Apply sane defaults to the new audio fields on existing pos.config rows so
existing customers get safe values out of the box (no surprise sounds on
their next sale).

The pre_init_hook in __init__.py already guaranteed the columns exist;
this script just normalises values that ended up NULL because they
existed before the columns did.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("[XIBO POS MIGRATION] running 19.0.1.5.31 post-migration")

    # 1) Default audio_enabled=False for all existing configs.
    #    (Users explicitly enable it; we don't surprise them with sounds.)
    cr.execute(
        "UPDATE pos_config SET xibo_thanks_audio_enabled = FALSE "
        "WHERE xibo_thanks_audio_enabled IS NULL"
    )
    n1 = cr.rowcount

    # 2) Default audio_preset='chime' where NULL.
    cr.execute(
        "UPDATE pos_config SET xibo_thanks_audio_preset = 'chime' "
        "WHERE xibo_thanks_audio_preset IS NULL"
    )
    n2 = cr.rowcount

    # 3) Default audio_volume=80 where NULL or out of range.
    cr.execute(
        "UPDATE pos_config SET xibo_thanks_audio_volume = 80 "
        "WHERE xibo_thanks_audio_volume IS NULL "
        "   OR xibo_thanks_audio_volume < 0 "
        "   OR xibo_thanks_audio_volume > 100"
    )
    n3 = cr.rowcount

    if n1 or n2 or n3:
        _logger.info(
            "[XIBO POS MIGRATION] normalised %s audio_enabled, %s audio_preset, "
            "%s audio_volume row(s) on pos_config",
            n1, n2, n3,
        )
    else:
        _logger.info(
            "[XIBO POS MIGRATION] no rows needed normalisation (fresh install or already good)"
        )
