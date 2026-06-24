# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    xibo_show_in_public_screens = fields.Boolean(
        string='Show on Public Screens',
        default=True,
        help="If enabled, this customer's name may appear on digital signage "
             "screens connected via the Xibo Connector add-ons (welcome, "
             "thank-you, etc.). When disabled, a generic fallback such as "
             "'valued customer' is shown instead.",
    )

    xibo_display_nickname = fields.Char(
        string='Display Nickname',
        help="Friendly short name (or diminutive) shown on Xibo screens "
             "instead of the full name. Example: 'Paco' for 'Francisco "
             "Pérez Cruz'. Can be auto-filled via the AI action button. "
             "Not applicable to companies.",
    )

    def _xibo_first_name(self):
        """Extract the first given name from the full name."""
        self.ensure_one()
        full = (self.name or '').strip()
        if not full:
            return ''
        if ',' in full:
            after_comma = full.split(',', 1)[1].strip()
            return after_comma.split()[0] if after_comma else ''
        parts = full.split()
        return parts[0] if parts else ''

    def _xibo_resolve_display_name(self):
        """Return the name to display on public screens.

        Resolution order:
        1. If `xibo_show_in_public_screens` is False -> generic fallback.
        2. If `is_company` is True -> use the company name.
        3. If `xibo_display_nickname` is set -> use it.
        4. Else -> first name only (heuristic).
        5. Last resort -> generic fallback.

        The AI is invoked via the server action button on the contact form
        or via the bulk action "Detect Nickname with AI" in the contacts list.
        """
        self.ensure_one()
        if not self.xibo_show_in_public_screens:
            return _("valued customer")
        if self.is_company:
            return self.name or _("valued customer")
        if self.xibo_display_nickname:
            return self.xibo_display_nickname.strip()
        first = self._xibo_first_name()
        if first:
            return first
        return _("valued customer")
