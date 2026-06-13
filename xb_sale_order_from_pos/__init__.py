# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Packaging/install-time data heal (NOT a runtime feature).

    The native ``pos_sale._compute_amount_unpaid`` subtracts the FULL ``amount_total``
    of every linked pos.order, so a loose product sold in the same ticket as a down
    payment is wrongly credited against the Sale Order balance. This module overrides
    that compute to subtract only the linked lines' ``price_subtotal_incl``
    (see ``SaleOrder._compute_amount_unpaid``).

    Installing over EXISTING data leaves the previously stored (native-computed)
    ``amount_unpaid`` values stale. This hook recomputes them — exactly the staging
    batch logic — so balances are correct right after install. Idempotent: orders that
    were already native==fix do not change.
    """
    sale_orders = env["sale.order"].search([("order_line.pos_order_line_ids", "!=", False)])
    sale_orders._compute_amount_unpaid()
