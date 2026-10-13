# -*- coding: utf-8 -*-
"""Computed helper fields for WhatsApp anniversary templates.

These expose, on each reminder record, two ready-to-render values that
WhatsApp template variables can bind to:

* ``x_wa_first_name`` – the customer's diminutive / first name (reuses the
  Xibo connector's resolver when available, with a safe inline fallback).
* ``x_wa_anniv_phrase`` – a grammatical Spanish phrase for the upcoming
  anniversary, e.g. "tu décimo aniversario de bodas" or, for high counts,
  "tu aniversario de bodas número 15".
"""
import re
from urllib.parse import quote

from odoo import fields, models, _
from odoo.tools import hmac

# Signed-link scope for the email opt-out route.
_OPTOUT_SCOPE = "anello-anniv-optout"

# Spanish ordinals that still read naturally as "tu <ord> aniversario".
_ORDINALS = {
    1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto", 5: "quinto",
    6: "sexto", 7: "séptimo", 8: "octavo", 9: "noveno", 10: "décimo",
}


class XbWishReminders(models.Model):
    _inherit = "xb.wish.reminders"

    x_wa_first_name = fields.Char(
        string="WhatsApp First Name",
        compute="_compute_x_wa_first_name",
        help="Diminutive / first name used as {{1}} in WhatsApp templates.",
    )
    x_wa_anniv_phrase = fields.Char(
        string="WhatsApp Anniversary Phrase",
        compute="_compute_x_wa_anniv_phrase",
        help="Ready-to-render phrase used as {{2}} in WhatsApp templates, "
             "e.g. 'tu décimo aniversario de bodas'.",
    )
    x_wa_chat_url = fields.Char(
        string="WhatsApp Chat Link",
        compute="_compute_x_wa_chat_url",
        help="click-to-chat wa.me link to the company's WhatsApp number, "
             "for use in the anniversary email.",
    )
    x_wa_optout_url = fields.Char(
        string="Anniversary Opt-out Link",
        compute="_compute_x_wa_optout_url",
        help="Signed public link that stops the anniversary greeting and "
             "flags the contact as a NOVADIAM prospect.",
    )

    # ------------------------------------------------------------------
    def _compute_x_wa_chat_url(self):
        Acc = self.env["whatsapp.account"].sudo()
        for rec in self:
            digits = ""
            if rec.company_id:
                acc = Acc.search(
                    [("allowed_company_ids", "in", rec.company_id.id)], limit=1)
                if acc:
                    digits = re.sub(r"\D", "", acc.phone_number or "")
            if digits:
                text = quote(_("Hola, escribo por mi aniversario 💍"))
                rec.x_wa_chat_url = "https://wa.me/%s?text=%s" % (digits, text)
            else:
                rec.x_wa_chat_url = ""

    def _compute_x_wa_optout_url(self):
        base = self.get_base_url()
        for rec in self:
            if not rec.id:
                rec.x_wa_optout_url = ""
                continue
            token = hmac(rec.env(su=True), _OPTOUT_SCOPE, str(rec.id))
            rec.x_wa_optout_url = "%s/anello/aniversario/baja?r=%s&t=%s" % (
                base, rec.id, token)

    @staticmethod
    def _xb_optout_token(env, reminder_id):
        """Expected signed token for an opt-out link. Shared with the
        controller so both sides compute it identically."""
        return hmac(env(su=True), _OPTOUT_SCOPE, str(reminder_id))

    # ------------------------------------------------------------------
    def _wa_extract_first_name(self, full):
        """Inline fallback: first given name from a full name string."""
        full = (full or "").strip()
        if not full:
            return ""
        if "," in full:
            after = full.split(",", 1)[1].strip()
            return after.split()[0] if after else ""
        parts = full.split()
        return parts[0] if parts else ""

    def _compute_x_wa_first_name(self):
        for rec in self:
            partner = rec.partner_id
            name = ""
            if partner:
                # Reuse the Xibo connector resolver when installed
                # (handles manual nickname -> first name -> fallback).
                resolver = getattr(partner, "_xibo_resolve_display_name", None)
                if callable(resolver):
                    try:
                        name = resolver() or ""
                    except Exception:  # noqa: BLE001
                        name = ""
                if not name:
                    name = self._wa_extract_first_name(partner.name)
            rec.x_wa_first_name = name or _("hola")

    def _compute_x_wa_anniv_phrase(self):
        for rec in self:
            years = 0
            # next_occurrence_date already returns the next FUTURE occurrence
            # (skips today), so year subtraction gives the count being greeted.
            if rec.date and rec.period_type == "year" and rec.next_occurrence_date:
                years = rec.next_occurrence_date.year - rec.date.year
            # Guard against data typos (future wedding dates, absurd values).
            if years <= 0 or years > 75:
                rec.x_wa_anniv_phrase = _("tu aniversario de bodas")
            elif years in _ORDINALS:
                rec.x_wa_anniv_phrase = (
                    _("tu %s aniversario de bodas") % _ORDINALS[years]
                )
            else:
                rec.x_wa_anniv_phrase = (
                    _("tu aniversario de bodas número %s") % years
                )
