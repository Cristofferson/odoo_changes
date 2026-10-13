# -*- coding: utf-8 -*-
"""Inbound handling for the anniversary WhatsApp campaign.

The approved ``aniversario_de_boda_anello`` template ships three
quick-reply buttons. When the customer taps one, Meta delivers a
``button`` message whose text equals the button label. Odoo posts that
text into the WhatsApp ``discuss.channel`` and creates an inbound
``whatsapp.message`` from ``_notify_thread``.

We hook the same method to turn those taps into concrete CRM actions
(shared with the email channel via ``res.partner``), while leaving every
other inbound message untouched for human handling in Discuss.

We ALSO override ``_get_whatsapp_channel`` so that when the customer
replies to a template we sent (anniversaries, POS follow-up, order ready,
payment reminders, ...), the outbound message is mirrored into the channel
as an internal note right above the reply. Without this the agent sees a bare
reply ("who chose my ring?") with no idea what it answers -- the native
code only drops a "Related <doc>:" link, never the message text.
"""
import logging
import re
import unicodedata

from markupsafe import Markup

from odoo import models, tools, _

_logger = logging.getLogger(__name__)

# Exact button labels of the aniversario_de_boda_anello template
# (lower-cased, whitespace-stripped for comparison).
BTN_CLEANING = "quiero mi limpieza"
BTN_REPAIR = "ayuda con mis argollas"
BTN_OPTOUT = "ya no celebro esta fecha"

# Free-text safety net so a plain "BAJA"/"STOP" also unsubscribes,
# per Meta good-practice for marketing conversations.
OPTOUT_KEYWORDS = {"baja", "stop", "cancelar", "unsubscribe", "darme de baja"}

# "You have the wrong person" is NOT the same request as "stop writing me",
# and until now it fell through to a human -- who then promised the removal
# in the chat and had no way to actually perform it. (Real case, 22-jul-2026:
# a customer answered "Perdón está equivocado", Anello replied "Te borramos
# de nuestro listado", and the reminder stayed active.)
#
# These are matched against the WHOLE message, after stripping a leading
# courtesy word, and only when the contact really has an active anniversary
# reminder in this company. That is what keeps "el precio está equivocado"
# in a live sales conversation from unsubscribing anybody.
WRONG_PERSON_PHRASES = {
    "esta equivocado", "esta equivocada", "estas equivocado",
    "estan equivocados", "numero equivocado", "numero incorrecto",
    "el numero esta equivocado", "es el numero equivocado",
    "persona equivocada", "es la persona equivocada",
    "no soy la persona", "no soy esa persona", "no soy yo", "yo no soy",
    "se equivocaron", "se equivoco", "te equivocaste",
    "se equivocaron de numero", "se equivoco de numero",
}

# Dropped from the START of the message before matching. "no" is deliberately
# absent: it would turn "no soy yo" into "soy yo" and invert the meaning.
COURTESY_LEADING = (
    "buenos dias", "buen dia", "buenas tardes", "buenas noches", "buenas",
    "perdon", "perdona", "perdone", "disculpa", "disculpe", "disculpen",
    "hola", "oye", "hey", "creo que", "me parece que", "pero", "es que",
    "señor", "senor", "señora", "senora", "amigo", "amiga",
)

# Commands an agent can run from the channel itself (see
# ``_xb_handle_agent_command``). Written as an INTERNAL NOTE they never reach
# the customer.
CMD_STOP = "/baja"
CMD_RESUME = "/alta"


def _xb_loose(text):
    """Lower-case, drop accents and punctuation, collapse whitespace.

    Deliberately NOT the normalisation used by ``_xb_is_campaign_reply`` for
    button labels: those must match the dispatcher byte for byte (accents
    included). This one is for free-form human text.
    """
    txt = unicodedata.normalize("NFKD", text or "")
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"[^\w\s]", " ", txt.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", txt).strip()


def _xb_strip_courtesy(norm):
    """Peel leading courtesy words: "Perdón está equivocado" -> "esta equivocado"."""
    changed = True
    while changed and norm:
        changed = False
        for lead in COURTESY_LEADING:
            if norm == lead:
                return ""
            if norm.startswith(lead + " "):
                norm = norm[len(lead) + 1:]
                changed = True
                break
    return norm


def _xb_is_wrong_person(text):
    """True when the WHOLE message says "you have the wrong person".

    Whole-message matching is the point: it is what separates a bare
    "Perdón está equivocado" from "el precio está equivocado" inside a live
    quotation thread.
    """
    return _xb_strip_courtesy(_xb_loose(text)) in WRONG_PERSON_PHRASES


# ``ir.config_parameter`` holding the comma-separated ids of the
# ``whatsapp.account`` records these campaigns belong to. Everything this
# module does (cleaning leads, repair leads, anniversary opt-out, NOVADIAM
# prospects) is Anello-specific, but ``_notify_thread`` fires on EVERY
# WhatsApp channel. Once a second company got its own number, a customer
# writing "cancelar" to XUBAX support would have run the Anello opt-out.
# Empty/unset keeps the old behaviour (all accounts) for back-compat.
CAMPAIGN_ACCOUNTS_PARAM = "special_dates_whatsapp.wa_account_ids"


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    # ------------------------------------------------------------------
    # Account gate (shared with xb_pos_followup)
    # ------------------------------------------------------------------
    def _xb_is_campaign_channel(self):
        """True when this channel belongs to an account running our campaigns."""
        self.ensure_one()
        raw = self.env["ir.config_parameter"].sudo().get_param(
            CAMPAIGN_ACCOUNTS_PARAM, "")
        allowed = {int(x) for x in str(raw).replace(" ", "").split(",") if x.isdigit()}
        if not allowed:
            return True  # not configured: behave as before
        return self.wa_account_id.id in allowed

    def _xb_is_campaign_reply(self, message):
        """True when this inbound is a button/keyword a campaign dispatcher
        owns, so the generic autoreply (xb_whatsapp_autoreply) must stand down
        instead of firing its menu/escalation on top.

        Order-independent by design: it re-derives the answer from the message
        text + channel, so it does not matter whether the campaign dispatcher
        ran before or after in the ``_notify_thread`` super() chain. Sibling
        campaign modules (e.g. xb_pos_followup) extend it via super()."""
        self.ensure_one()
        if self.channel_type != "whatsapp" or not self._xb_is_campaign_channel():
            return False
        norm = tools.html2plaintext(message.body or "").strip().lower()
        if not norm:
            return False
        if norm in {BTN_CLEANING, BTN_REPAIR, BTN_OPTOUT} or norm in OPTOUT_KEYWORDS:
            return True
        # A "wrong number" is handled by the campaign dispatcher too, so the
        # generic autoreply must not answer it with a menu.
        return _xb_is_wrong_person(norm)

    def _xb_has_live_anniversary(self, partner, company):
        """True when this contact really is on the anniversary list here.

        This is the gate for the fuzzy "wrong person" phrases: with no active
        reminder there is nothing to switch off, so there is no reason to
        second-guess what the customer meant.
        """
        if not partner or not company:
            return False
        return bool(self.env["xb.wish.reminders"].sudo().search_count([
            ("partner_id", "=", partner.id),
            ("company_id", "=", company.id),
            ("active", "=", True),
            ("period_type", "=", "year"),
        ]))

    # ------------------------------------------------------------------
    # Greeting context: when a customer answers a template we sent, put
    # that template's text right above the answer, as an internal note.
    #
    # Until 14-sep-2026 this only ran when the native lookup handed us
    # ``related_message``, which NEVER happened with Mexican numbers:
    # ``_process_messages`` passes Meta's raw ``from`` (``521`` + 10 digits)
    # to ``_find_active_channel``, which compares it verbatim with
    # ``mobile_number_formatted`` (``52`` + 10 digits) -> no match, no
    # related message, no mirror. Real case: Mariana Gudino answered "Ok" to
    # her "order ready" notice and the agent saw nothing above it.
    # We now look the template up ourselves with the number as the channel
    # stores it, and we also cover a reply landing in an EXISTING channel.
    # Routing stays exactly native (we never pass the related message down),
    # so conversations keep being grouped as before.
    # ------------------------------------------------------------------
    _XB_MIRROR_MARKER = "Mensaje enviado al cliente"

    def _get_whatsapp_channel(self, whatsapp_number, wa_account_id, sender_name=False,
                              create_if_not_found=False, related_message=False):
        channel = super()._get_whatsapp_channel(
            whatsapp_number, wa_account_id, sender_name=sender_name,
            create_if_not_found=create_if_not_found, related_message=related_message,
        )
        # Only the inbound webhook asks for creation (whatsapp_account.
        # _process_messages); outbound sends pass create_if_not_found=False.
        if create_if_not_found and len(channel) == 1:
            try:
                greeting = related_message or channel._xb_last_template_message(
                    whatsapp_number)
                if channel._xb_greeting_missing(greeting):
                    channel._xb_mirror_greeting(greeting)
            except Exception:  # noqa: BLE001 - never break reception
                _logger.exception(
                    "special_dates_whatsapp: could not mirror greeting into "
                    "channel %s", channel.id)
        return channel

    def _xb_last_template_message(self, raw_number=False):
        """``mail.message`` of the last template this account sent to the
        channel's number: the native ``_find_active_channel`` search, but with
        the number normalised the way the channel stores it."""
        self.ensure_one()
        numbers = {self.whatsapp_number, (raw_number or "").lstrip("+")} - {False, ""}
        wa_msg = self.env["whatsapp.message"].sudo().search([
            ("mobile_number_formatted", "in", list(numbers)),
            ("wa_account_id", "=", self.wa_account_id.id),
            ("wa_template_id", "!=", False),
            ("state", "not in", ["outgoing", "error", "cancel"]),
        ], limit=1, order="id desc")
        return wa_msg.mail_message_id

    def _xb_greeting_missing(self, greeting):
        """True when the customer is answering ``greeting`` and its text is
        not in this conversation yet.

        Only what happened in the channel AFTER the template went out counts:
        if the customer already wrote since then, the context belonged to that
        earlier message, not to this one; if the template text is already
        there (our note, or the native full copy posted when the sender was a
        member), there is nothing to add."""
        self.ensure_one()
        if (not greeting or not greeting.body or not greeting.model
                or greeting.model in ("discuss.channel", "mailing.mailing")):
            return False
        customer = self.whatsapp_partner_id
        later = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"),
            ("res_id", "=", self.id),
            ("id", ">", greeting.id),
        ], limit=200)
        for msg in later:
            if (msg.message_type == "whatsapp_message" and customer
                    and msg.author_id == customer):
                return False
            if msg.body and (msg.body == greeting.body
                             or self._XB_MIRROR_MARKER in msg.body):
                return False
        return True

    def _xb_mirror_greeting(self, greeting):
        """Post the template we sent as an internal note (it never reaches the
        customer): what it said, from which document, and when."""
        self.ensure_one()
        header = Markup("<b>%s:</b>") % self._XB_MIRROR_MARKER
        record = False
        if greeting.model in self.env and greeting.res_id:
            record = self.env[greeting.model].sudo().browse(greeting.res_id).exists()
        if record:
            header += Markup(' <a href="/odoo/%s/%s" target="_blank">%s</a>') % (
                greeting.model, greeting.res_id, record.display_name)
        if greeting.date:
            tz = (self.wa_account_id.notify_user_ids[:1].tz
                  or self.env.user.tz or "America/Mexico_City")
            header += Markup(" &middot; %s") % tools.format_datetime(
                self.env, greeting.date, tz=tz, dt_format="dd/MM/yyyy HH:mm")
        self.message_post(
            body=Markup("<p>%s</p>") % header + Markup(greeting.body or ""),
            author_id=self.env.ref("base.partner_root").id,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    # ------------------------------------------------------------------
    # Hook: inbound WhatsApp messages
    # ------------------------------------------------------------------
    def _notify_thread(self, message, msg_vals=False, **kwargs):
        res = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        # ``whatsapp_inbound_msg_uid`` is the reliable inbound signal used
        # by the native module itself.
        if kwargs.get("whatsapp_inbound_msg_uid"):
            for channel in self:
                if channel.channel_type != "whatsapp":
                    continue
                if not channel._xb_is_campaign_channel():
                    continue
                try:
                    channel._xb_dispatch_anniversary_reply(message)
                except Exception:  # noqa: BLE001 - never break reception
                    _logger.exception(
                        "special_dates_whatsapp: failed to process inbound "
                        "reply on channel %s (msg %s)", channel.id, message.id
                    )
        return res

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def _xb_dispatch_anniversary_reply(self, message):
        self.ensure_one()
        partner = self.whatsapp_partner_id
        if not partner:
            return
        norm = tools.html2plaintext(message.body or "").strip().lower()
        if not norm:
            return
        company = self._xb_anello_company()
        # Responsible users are resolved per purpose inside res.partner
        # (configurable via ir.config_parameter), so we don't pass one here.
        # ``Markup % dict`` escapes the substituted values: lead names carry
        # the customer's own name, which is untrusted input.
        if norm == BTN_CLEANING:
            lead = partner._xb_anniv_cleaning(company)
            self._xb_note(Markup(_(
                "🧼 <b>Quiere su limpieza</b>. Prospecto <b>%(lead)s</b> "
                "creado con actividad para agendarla."
            )) % {"lead": lead.name})
        elif norm == BTN_REPAIR:
            lead = partner._xb_anniv_repair(company)
            self._xb_note(Markup(_(
                "🔧 <b>Pide ayuda con sus argollas</b>. Prospecto "
                "<b>%(lead)s</b> creado con actividad para cotizar."
            )) % {"lead": lead.name})
        elif norm in OPTOUT_KEYWORDS and norm != BTN_OPTOUT and not self._xb_has_live_anniversary(
                partner, company):
            # «Stop» / «baja» a un mensaje que NO es de aniversario (p. ej. el seguimiento
            # de un pedido): no está en la lista, no se le etiqueta ni se le abre prospecto.
            self._xb_note(Markup(_(
                "🛑 <b>Escribió «%(txt)s»</b>, pero no está en la lista de aniversarios, así que "
                "no se hizo nada automático (sin etiqueta ni prospecto). Una persona debe decidir "
                "si no se le escribe más (Contactos › Lista negra de teléfonos)."
            )) % {"txt": norm})
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                date_deadline=fields.Date.context_today(self),
                summary=_("Pidió «%s»: revisar si no se le escribe más") % norm,
                user_id=self.env.uid)
        elif norm == BTN_OPTOUT or norm in OPTOUT_KEYWORDS:
            info = partner._xb_anniv_optout(company)
            lead = info.get("novadiam_lead")
            lead_txt = Markup(_(" Prospecto NOVADIAM <b>%s</b> creado.")) \
                % lead.name if lead else Markup("")
            self._xb_note(Markup(_(
                "🚫 <b>Pidió no recibir su aniversario</b>. Se desactivaron "
                "%(n)s recordatorio(s) y se etiquetó al contacto.%(lead)s"
            )) % {"n": info.get("deactivated", 0), "lead": lead_txt})
        elif _xb_is_wrong_person(norm) and self._xb_has_live_anniversary(
                partner, company):
            n = partner._xb_anniv_stop(company)
            self._xb_note(Markup(_(
                "🙈 <b>Dice que nos equivocamos de persona.</b> Se "
                "desactivaron %(n)s recordatorio(s) de aniversario para que "
                "no le vuelva a llegar. <b>No</b> se le abrió prospecto ni se "
                "le etiquetó: no pidió eso, solo avisó del error. Si fue una "
                "confusión, se revierte con <code>/alta</code> en una nota "
                "interna de este canal."
            )) % {"n": n})
        # any other text: intentionally left for a human in Discuss.

    # ------------------------------------------------------------------
    # Agent commands (internal notes)
    # ------------------------------------------------------------------
    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        try:
            self._xb_handle_agent_command(message)
        except Exception:  # noqa: BLE001 - never break posting a message
            _logger.exception(
                "special_dates_whatsapp: agent command failed on channel %s",
                self.ids)
        return message

    def _xb_handle_agent_command(self, message):
        """Let whoever is answering in Discuss run the opt-out themselves.

        Why this exists: the machinery to unsubscribe someone was complete,
        but only the CUSTOMER could trigger it (a button or a keyword). When
        the request arrived in any other shape -- "wrong number", said over
        the phone, a friend asking on their behalf -- the agent would promise
        the removal in the chat and nothing happened in the database.

        Written in the *Log note* tab the command never reaches the customer;
        Odoo only pushes ``message_type='whatsapp_message'`` out to Meta. If
        it is typed in the wrong box we still honour it, but we say so, since
        by then the customer has already received the literal "/baja".
        """
        if not message or len(self) != 1:
            return
        if self.channel_type != "whatsapp" or not self._xb_is_campaign_channel():
            return
        body = tools.html2plaintext(message.body or "").strip().lower()
        if not body.startswith((CMD_STOP, CMD_RESUME)):
            return
        # Our own notes never start with a slash, but do not act on them.
        root = self.env.ref("base.partner_root", raise_if_not_found=False)
        if root and message.author_id and message.author_id.id == root.id:
            return

        partner = self.whatsapp_partner_id
        company = self._xb_anello_company()
        leaked = message.message_type == "whatsapp_message"
        warn = Markup(_(
            "<br/>⚠️ Lo escribiste en la caja de mensaje, así que <b>el "
            "cliente recibió el texto del comando</b>. La próxima vez usa la "
            "pestaña <b>Nota interna</b>."
        )) if leaked else Markup("")

        if not partner:
            self._xb_note(Markup(_(
                "No pude ejecutar el comando: este canal no tiene un "
                "contacto ligado.")) + warn)
            return

        # ``Markup % dict`` escapes every substituted value, so a contact
        # named "<img onerror=...>" cannot inject anything into the chatter.
        if body.startswith(CMD_STOP):
            n = partner._xb_anniv_stop(company)
            if n:
                self._xb_note(Markup(_(
                    "🚫 <b>Baja aplicada por %(agent)s.</b> %(n)s "
                    "recordatorio(s) de aniversario desactivado(s) para "
                    "<b>%(name)s</b>. Se revierte con <code>/alta</code>."
                )) % {"agent": self.env.user.name, "n": n,
                      "name": partner.name} + warn)
            else:
                self._xb_note(Markup(_(
                    "Nada que dar de baja: <b>%(name)s</b> no tiene "
                    "recordatorios de aniversario activos en %(company)s."
                )) % {"name": partner.name, "company": company.name} + warn)
        else:
            n = partner._xb_anniv_resume(company)
            self._xb_note(Markup(_(
                "↩️ <b>Alta restituida por %(agent)s.</b> %(n)s "
                "recordatorio(s) reactivado(s) para <b>%(name)s</b>."
            )) % {"agent": self.env.user.name, "n": n,
                  "name": partner.name} + warn)

    # ------------------------------------------------------------------
    # Channel-scoped helpers
    # ------------------------------------------------------------------
    def _xb_anello_company(self):
        acc = self.wa_account_id
        if acc and acc.allowed_company_ids:
            return acc.allowed_company_ids[0]
        return self.company_id or self.env.company

    def _xb_responsible_user(self):
        acc = self.wa_account_id
        if acc and acc.notify_user_ids:
            return acc.notify_user_ids[0]
        return self.env["res.users"]

    def _xb_note(self, body):
        """Internal note in the WhatsApp channel for the human agent."""
        self.message_post(
            body=body,
            author_id=self.env.ref("base.partner_root").id,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
