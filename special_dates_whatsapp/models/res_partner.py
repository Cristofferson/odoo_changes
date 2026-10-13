# -*- coding: utf-8 -*-
"""Reusable anniversary-campaign actions.

The same three intents (cleaning gift, ring repair, opt-out) can arrive
either from a WhatsApp quick-reply button or from a link in the email.
The business logic lives here on ``res.partner`` so both channels call
exactly the same code; the WhatsApp handler and the email controller
only differ in how they acknowledge the customer.
"""
from datetime import timedelta

from odoo import fields, models, _

# CRM / partner tag names (created on first use).
TAG_CLEANING = "Aniversario Anello"
TAG_REPAIR = "Restauración argollas"
TAG_NOVADIAM = "Prospecto NOVADIAM"


class ResPartner(models.Model):
    _inherit = "res.partner"

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _xb_anniv_responsible(self, company, purpose="anello"):
        """Who gets the lead/activity, by purpose.

        Configurable without code via ``ir.config_parameter``:
        * ``special_dates_whatsapp.anello_responsible_uid``   (limpieza/ajuste)
        * ``special_dates_whatsapp.novadiam_responsible_uid`` (prospecto NOVADIAM)

        Falls back to the WhatsApp account's first notified user, then admin.
        """
        param = self.env["ir.config_parameter"].sudo()
        key = "special_dates_whatsapp.%s_responsible_uid" % (
            "novadiam" if purpose == "novadiam" else "anello")
        try:
            uid = int(param.get_param(key) or 0)
        except (TypeError, ValueError):
            uid = 0
        if uid:
            user = self.env["res.users"].sudo().browse(uid)
            if user.exists() and user.active:
                return user
        acc = self.env["whatsapp.account"].sudo().search(
            [("allowed_company_ids", "in", company.id)], limit=1)
        if acc and acc.notify_user_ids:
            return acc.notify_user_ids[0]
        return self.env.ref("base.user_admin", raise_if_not_found=False) \
            or self.env["res.users"]

    def _xb_anniv_crm_tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        return Tag.search([("name", "=", name)], limit=1) \
            or Tag.create({"name": name})

    def _xb_anniv_partner_tag(self, name):
        Cat = self.env["res.partner.category"].sudo()
        return Cat.search([("name", "=", name)], limit=1) \
            or Cat.create({"name": name})

    def _xb_anniv_recent_lead(self, tag, company):
        """Open lead with same partner+tag in the last 30 days (dedup)."""
        horizon = fields.Datetime.now() - timedelta(days=30)
        return self.env["crm.lead"].sudo().search([
            ("partner_id", "=", self.id),
            ("tag_ids", "in", tag.id),
            ("company_id", "=", company.id),
            ("active", "=", True),
            ("create_date", ">=", fields.Datetime.to_string(horizon)),
        ], limit=1)

    def _xb_anniv_make_lead(self, company, name, tag, description,
                            responsible=None):
        self.ensure_one()
        existing = self._xb_anniv_recent_lead(tag, company)
        if existing:
            existing.message_post(
                body=_("Customer requested the same option again."),
                subtype_xmlid="mail.mt_note",
            )
            return existing
        responsible = responsible or self._xb_anniv_responsible(company)
        return self.env["crm.lead"].sudo().with_company(company).create({
            "name": name,
            "type": "lead",
            "partner_id": self.id,
            "contact_name": self.name,
            "phone": self.phone,
            "company_id": company.id,
            "user_id": responsible.id or False,
            "tag_ids": [(4, tag.id)],
            "description": description,
        })

    # ------------------------------------------------------------------
    # Intents
    # ------------------------------------------------------------------
    def _xb_anniv_cleaning(self, company, responsible=None):
        self.ensure_one()
        responsible = responsible or self._xb_anniv_responsible(company, "anello")
        lead = self._xb_anniv_make_lead(
            company,
            _("💍 Limpieza de argollas (aniversario) — %s") % self.name,
            self._xb_anniv_crm_tag(TAG_CLEANING),
            _("El cliente pidió su limpieza profesional de argollas de "
              "regalo, respondiendo a la campaña de aniversario."),
            responsible=responsible,
        )
        lead.activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=fields.Date.context_today(self) + timedelta(days=3),
            summary=_("Agendar limpieza gratis de argollas"),
            note=_("Contactar al cliente para agendar su limpieza de "
                   "aniversario. Aprovechar para ofrecer restauración/ajuste."),
            user_id=responsible.id or self.env.uid,
        )
        return lead

    def _xb_anniv_repair(self, company, responsible=None):
        self.ensure_one()
        responsible = responsible or self._xb_anniv_responsible(company, "anello")
        lead = self._xb_anniv_make_lead(
            company,
            _("🔧 Restauración/ajuste de argollas — %s") % self.name,
            self._xb_anniv_crm_tag(TAG_REPAIR),
            _("El cliente pidió ayuda con sus argollas (restauración, ajuste "
              "de talla o volver a hacerlas), desde la campaña de aniversario."),
            responsible=responsible,
        )
        lead.activity_schedule(
            "mail.mail_activity_data_todo",
            date_deadline=fields.Date.context_today(self) + timedelta(days=2),
            summary=_("Cotizar restauración/ajuste/fabricación"),
            note=_("Contactar al cliente para diagnosticar y cotizar el "
                   "trabajo en sus argollas."),
            user_id=responsible.id or self.env.uid,
        )
        return lead

    def _xb_anniv_stop(self, company, reminder=None):
        """Stop future anniversary messages and nothing else.

        Split out of ``_xb_anniv_optout`` because the two are NOT the same
        request. Someone who taps "Ya no celebro esta fecha" is telling us
        the marriage anniversary is over, which is a decent NOVADIAM lead.
        Someone who says "wrong number", or an agent running ``/baja`` on
        the customer's behalf, is telling us nothing of the sort -- opening
        a prospect on them would be putting words in their mouth.

        Returns the number of reminders deactivated.
        """
        self.ensure_one()
        if reminder is not None and reminder.exists():
            reminders = reminder
        else:
            reminders = self.env["xb.wish.reminders"].sudo().search([
                ("partner_id", "=", self.id),
                ("company_id", "=", company.id),
                ("active", "=", True),
                ("period_type", "=", "year"),
            ])
        n = len(reminders)
        if reminders:
            reminders.sudo().write({"active": False})
        return n

    def _xb_anniv_resume(self, company):
        """Undo ``_xb_anniv_stop``: bring the anniversary reminders back.

        Only for fixing an operator mistake -- there is no customer-facing
        path into this. Returns the number of reminders reactivated.
        """
        self.ensure_one()
        reminders = self.env["xb.wish.reminders"].sudo() \
            .with_context(active_test=False).search([
                ("partner_id", "=", self.id),
                ("company_id", "=", company.id),
                ("active", "=", False),
                ("period_type", "=", "year"),
            ])
        n = len(reminders)
        if reminders:
            reminders.write({"active": True})
        return n

    def _xb_anniv_optout(self, company, responsible=None, reminder=None):
        """Stop the anniversary greeting and turn the customer into a
        NOVADIAM prospect. Works from WhatsApp (no specific reminder) or
        from the email link (a concrete reminder).

        Returns a dict: {'deactivated': n, 'novadiam_lead': lead|False}.
        """
        self.ensure_one()
        responsible = responsible or self._xb_anniv_responsible(
            company, "novadiam")

        # 1) Stop future anniversary messages (email + WhatsApp).
        n = self._xb_anniv_stop(company, reminder=reminder)

        # 2) Tag the contact.
        self.sudo().write({
            "category_id": [(4, self._xb_anniv_partner_tag(TAG_NOVADIAM).id)],
        })

        # 3) Open a NOVADIAM prospect (new engagement rings). NOVADIAM is a
        # brand/website, not a company name, so resolve its operating company
        # from the website record and fall back to the main company.
        novadiam = self.env["website"].sudo().search(
            [("name", "ilike", "novadiam")], limit=1).company_id
        if not novadiam:
            novadiam = self.env.ref("base.main_company",
                                    raise_if_not_found=False) \
                or self.env["res.company"]
        lead = self.env["crm.lead"]
        if novadiam:
            vals = {
                "name": _("Prospecto NOVADIAM (dejó aniversario Anello) — %s")
                % self.name,
                "type": "lead",
                "partner_id": self.id,
                "contact_name": self.name,
                "phone": self.phone,
                "company_id": novadiam.id,
                "user_id": responsible.id or False,
                "tag_ids": [(4, self._xb_anniv_crm_tag(TAG_NOVADIAM).id)],
                "description": _(
                    "El cliente pidió dejar de recibir la felicitación de "
                    "aniversario de Anello. Posible prospecto para NOVADIAM "
                    "(argollas nuevas)."
                ),
            }
            try:
                # Real customers are company-shared; the savepoint keeps a
                # company-bound edge case from aborting the whole request.
                with self.env.cr.savepoint():
                    lead = self.env["crm.lead"].sudo().with_company(
                        novadiam).create(vals)
            except Exception:  # noqa: BLE001 - company crossover, etc.
                vals["company_id"] = False
                lead = self.env["crm.lead"].sudo().create(vals)
            lead.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=fields.Date.context_today(self)
                + timedelta(days=5),
                summary=_("Prospecto NOVADIAM — dar seguimiento"),
                note=_("El cliente dejó su aniversario de Anello; evaluar "
                       "interés en argollas nuevas de NOVADIAM."),
                user_id=responsible.id or self.env.uid,
            )
        return {"deactivated": n, "novadiam_lead": lead}
