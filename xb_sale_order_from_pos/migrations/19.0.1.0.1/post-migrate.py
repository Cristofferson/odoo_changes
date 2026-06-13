# -*- coding: utf-8 -*-
# XUBAX - Sales, Quotations & Layaway from POS
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Drop the orphan column left by a removed field (xb_layaway_min_advance_pct,
    # the old configurable layaway minimum advance %, replaced by the simple
    # "advance > 0" rule). The field no longer exists on pos.config; the column may
    # persist on databases upgraded from an earlier build. IF EXISTS makes this
    # idempotent and safe on databases that never had it.
    cr.execute("ALTER TABLE pos_config DROP COLUMN IF EXISTS xb_layaway_min_advance_pct")
    _logger.info("[XB-MIG 19.0.1.0.1] dropped orphan column pos_config.xb_layaway_min_advance_pct (if existed)")
