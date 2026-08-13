# -*- coding: utf-8 -*-
import logging

from . import models
from . import controllers

_logger = logging.getLogger(__name__)

# Defensive: ensure columns exist even on in-place upgrades. Idempotent.
_COLUMNS = [
    ('sale_order', 'self_service_reserved', 'BOOLEAN DEFAULT FALSE'),
    ('website', 'self_service_enabled', 'BOOLEAN DEFAULT FALSE'),
    ('website', 'self_service_appointment_url', 'VARCHAR'),
    ('website', 'self_service_team_id', 'INTEGER'),
]


def pre_init_self_service_schema(env_or_cr):
    cr = getattr(env_or_cr, 'cr', env_or_cr)
    try:
        for table, name, pg_type in _COLUMNS:
            cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (table,))
            if not cr.fetchone():
                continue
            try:
                cr.execute('ALTER TABLE "%s" ADD COLUMN IF NOT EXISTS "%s" %s' % (table, name, pg_type))
            except Exception as e:
                _logger.warning("[XB SELF-SERVICE PRE-INIT] could not add %s.%s: %s", table, name, e)
    except Exception as e:
        _logger.exception("[XB SELF-SERVICE PRE-INIT] hook failed (non-fatal): %s", e)
