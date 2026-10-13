# -*- coding: utf-8 -*-
"""Amounts in WhatsApp templates, written the way people read them.

The native renderer turns every variable into ``str(value)``
(``whatsapp/models/whatsapp_template_variable.py`` ``_get_variables_value``
-> ``mail`` ``_find_value_from_field_path``), so a Monetary field reaches the
customer as ``14616.0`` or ``4509.68``: no thousands separator and a stray
``.0`` on round amounts.

Every approved template that shows money binds the currency symbol and the
amount as two separate variables (``{{4}}{{5}}``), so here we format ONLY
Monetary fields, WITHOUT the symbol, with the currency's decimals and the
separators of the template's language: ``14,616.00``. Anything else comes back
untouched. Meta does not re-review anything: it approves the template text,
not which Odoo field feeds each variable.

It lives here because this is the WhatsApp companion already installed in the
database; the code itself is generic (not tied to Special Dates) and covers
every template, future ones included.
"""
import logging

from odoo import models
from odoo.tools import formatLang

_logger = logging.getLogger(__name__)


class WhatsAppTemplateVariable(models.Model):
    _inherit = "whatsapp.template.variable"

    def _find_value_from_field_chain(self, record):
        value = super()._find_value_from_field_chain(record)
        try:
            amount = self._xb_format_monetary(record)
        except Exception:  # noqa: BLE001 - a format problem must never block a send
            _logger.exception(
                "special_dates_whatsapp: could not format %s on %s",
                self.field_name, record)
            amount = None
        return value if amount is None else amount

    def _xb_format_monetary(self, record):
        """``14,616.00`` for a Monetary field, None for anything else."""
        self.ensure_one()
        if self.field_type != "field" or not self.field_name or not record:
            return None
        owner_path, _dot, fname = self.field_name.rpartition(".")
        owner = record.sudo(False)
        if owner_path:
            owner = owner.mapped(owner_path)
        if len(owner) != 1:
            return None
        field = owner._fields.get(fname)
        if not field or field.type != "monetary":
            return None
        currency_fname = field.get_currency_field(owner)
        currency = owner[currency_fname] if currency_fname else False
        lang = self.wa_template_id.lang_code
        installed = {code for code, _name in owner.env["res.lang"].get_installed()}
        env = owner.with_context(lang=lang).env if lang in installed else owner.env
        return formatLang(env, owner[fname] or 0.0,
                          digits=currency.decimal_places if currency else 2)
