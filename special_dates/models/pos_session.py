# -*- coding: utf-8 -*-
# Special Dates does NOT register any extra model in pos.session.
# All POS data is fetched via RPC on demand from the partner_reminder
# popup, welcome popup and bell. This keeps the POS startup completely
# untouched and avoids interference with order/line setup.
#
# This file is intentionally left as an empty module on purpose, so that
# the import chain in models/__init__.py remains stable across versions.
