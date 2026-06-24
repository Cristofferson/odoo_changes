# -*- coding: utf-8 -*-
import logging

from . import models
from . import controllers

_logger = logging.getLogger(__name__)

# Defensive: make sure the showcase columns exist on pos_config even if the
# module is upgraded in-place (files dropped + restart) without going through
# Apps -> Upgrade. Idempotent (ADD COLUMN IF NOT EXISTS).
_POS_CONFIG_COLUMNS = [
    ('xibo_showcase_enabled', 'BOOLEAN DEFAULT FALSE'),
    ('xibo_showcase_url', 'VARCHAR'),
    ('xibo_showcase_category_id', 'INTEGER'),
    ('xibo_showcase_count', 'INTEGER DEFAULT 12'),
    ('xibo_showcase_interval', 'INTEGER DEFAULT 6'),
    ('xibo_showcase_heading', 'VARCHAR'),
    ('xibo_showcase_order', "VARCHAR DEFAULT 'price_desc'"),
]


def pre_init_showcase_schema(env_or_cr):
    cr = getattr(env_or_cr, 'cr', env_or_cr)
    try:
        cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name='pos_config'")
        if not cr.fetchone():
            return
        cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='pos_config'")
        existing = {r[0] for r in cr.fetchall()}
        for name, pg_type in _POS_CONFIG_COLUMNS:
            if name in existing:
                continue
            try:
                cr.execute('ALTER TABLE "pos_config" ADD COLUMN IF NOT EXISTS "%s" %s' % (name, pg_type))
                _logger.info("[XIBO SHOWCASE PRE-INIT] added column pos_config.%s", name)
            except Exception as e:
                _logger.warning("[XIBO SHOWCASE PRE-INIT] could not add %s: %s", name, e)
    except Exception as e:
        _logger.exception("[XIBO SHOWCASE PRE-INIT] hook failed (non-fatal): %s", e)
