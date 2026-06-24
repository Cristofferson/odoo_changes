# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    # Customer display is now layout-based with a permanent URL stored in pos.config.
    # No per-session refresh needed because pos.config.access_token is stable.
    # If the user changes the screen or URL, they re-apply manually via the
    # Customer Display Mirror "Apply in Xibo" button.
