# -*- coding: utf-8 -*-
"""Seguimiento de las citas que aparta el agente: recordatorio, «¿llegó?» a la tienda y,
si no llegó, hasta tres mensajes para reagendar. El estado de la cita es el nativo de Citas
(Reservada / Asistió / No asistió): lo marca la tienda y el agente lo lee."""
import logging
import unicodedata
from datetime import timedelta

import pytz
from markupsafe import Markup

from odoo import api, fields, models

from .support_contact import xb_phone_key

_logger = logging.getLogger(__name__)

XB_TZ = "America/Mexico_City"
XB_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
XB_REMIND_BEFORE = timedelta(hours=2)    # recordatorio: unas 2 h antes
XB_ASK_STORE_AFTER = timedelta(minutes=30)  # «¿llegó?» a la tienda: 30 min después de la hora
# Mensajes si no llegó: el mismo día, al día siguiente y a los 3 días (desde la cita).
XB_NOSHOW_STEPS = [timedelta(0), timedelta(hours=20), timedelta(days=3)]


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    xb_sa_channel_id = fields.Many2one("discuss.channel", "Plática de WhatsApp", copy=False, index="btree_not_null",
                                       help="La plática donde el agente apartó la cita: por ahí le da seguimiento.")
    xb_sa_reminded = fields.Boolean("Recordatorio enviado", copy=False)
    xb_sa_store_asked = fields.Boolean("Se preguntó a la tienda si llegó", copy=False)
    xb_sa_noshow_step = fields.Integer("Mensajes por no asistir", copy=False)
    xb_sa_noshow_dt = fields.Datetime("Último mensaje por no asistir", copy=False)
    xb_sa_arrival_channel_id = fields.Many2one("discuss.channel", "Se preguntó por WhatsApp en", copy=False,
                                               help="Plática de quien atiende: su «SÍ» o «NO» marca la cita.")
    xb_sa_arrival_chat_id = fields.Many2one("discuss.channel", "Se preguntó en el chat de Odoo", copy=False)

    def write(self, vals):
        if "start" in vals:
            # Cita movida: le toca su recordatorio y su pregunta a la tienda otra vez.
            vals = dict(vals, xb_sa_reminded=False, xb_sa_store_asked=False)
        return super().write(vals)

    def _xb_sa_customer(self):
        return self.appointment_booker_id or (self.partner_ids - self.user_id.partner_id)[:1]

    def _xb_sa_when(self, ahora):
        tz = pytz.timezone(XB_TZ)
        local = pytz.utc.localize(self.start).astimezone(tz)
        hoy = pytz.utc.localize(ahora).astimezone(tz).date()
        dia = "hoy" if local.date() == hoy else f"el {XB_DIAS[local.weekday()]} {local:%d/%m}"
        return dia, f"{local:%H:%M}"

    def _xb_sa_where(self):
        if self.videocall_location:
            return f" por videollamada; entras con esta liga: {self.videocall_location}"
        tipo = self.appointment_type_id
        lugar = tipo.location_id
        if lugar:
            direccion = (lugar._display_address(without_company=True) or "").replace("\n", ", ").strip(", ")
            return f" en {lugar.name}" + (f" ({direccion})" if direccion else "")
        return ""

    def _xb_sa_offer(self, canal):
        """Los horarios libres de los dos próximos días, como texto («domingo 25/10 a las 11:00 o 14:45, o …»)."""
        tz = pytz.timezone(XB_TZ)
        modalidad = "videollamada" if self.videocall_location else ""
        por_dia = {}
        for t, _u in canal._xb_sa_demo_slots(None, modalidad):
            local = t.astimezone(tz)
            por_dia.setdefault(local.date(), []).append(f"{local:%H:%M}")
        textos = []
        for dia in sorted(por_dia)[:2]:
            horas = por_dia[dia]
            textos.append(f"{XB_DIAS[dia.weekday()]} {dia:%d/%m} a las "
                          + (", ".join(horas[:-1]) + " o " if len(horas) > 1 else "") + horas[-1])
        return ", o el ".join(textos)

    def _xb_sa_say(self, canal, texto):
        """Al cliente por su plática (en ensayo, como nota). False si ya no hay ventana de 24 h."""
        if not self.env["xb.support.proposal"]._xb_window_open(canal):
            return False
        if canal.wa_account_id.sudo().xb_sa_shadow:
            canal._xb_sa_post_draft(texto)
        else:
            canal._xb_sa_send(texto)
        return True

    def _xb_sa_answered_since(self, canal, desde):
        """¿El cliente escribió después de ``desde``?"""
        mensajes = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", canal.id),
            ("message_type", "=", "whatsapp_message"), ("date", ">", desde)], limit=20)
        return any(m.wa_message_ids.filtered(lambda w: w.message_type == "inbound") for m in mensajes)

    def _xb_sa_lead(self):
        return self.opportunity_id if "opportunity_id" in self._fields else self.env["crm.lead"]

    def _xb_sa_todo(self, usuario, resumen):
        """Actividad para una persona del equipo, en la oportunidad (o en el contacto del cliente). Nada en el
        historial de la cita: sus invitados lo recibirían por correo."""
        registro = self._xb_sa_lead() or self.xb_sa_channel_id.xb_sa_lead_id or self._xb_sa_customer()
        if usuario and registro:
            registro.sudo().activity_schedule(
                "mail.mail_activity_data_todo", summary=resumen[:120], note=resumen, user_id=usuario.id)

    def _xb_sa_ask_store(self, canal, quien, hora):
        """«¿Llegó?» a quien atiende la cita, por los medios marcados en la cuenta. Si ninguno llegó, actividad."""
        acc = canal.wa_account_id.sudo()
        usuario = self.user_id
        if not usuario:
            return
        pregunta = f"¿Llegó {quien} a su cita de las {hora}?"
        liga = f"{self.get_base_url()}/odoo/calendar.event/{self.id}"
        avisado = False
        if acc.xb_sa_arrival_whatsapp:
            llave = xb_phone_key(usuario.partner_id.phone)
            suyo = llave and self.env["discuss.channel"].sudo().search([
                ("channel_type", "=", "whatsapp"), ("wa_account_id", "=", acc.id)], order="id desc").filtered(
                lambda c: xb_phone_key(c.whatsapp_number) == llave)[:1]
            if suyo and self._xb_sa_say(suyo, f"{pregunta} Respóndeme SÍ o NO y la marco en la cita."):
                self.xb_sa_arrival_channel_id = suyo
                avisado = True
        if acc.xb_sa_arrival_inbox:
            odoobot = self.env.ref("base.partner_root")
            chat = self.env["discuss.channel"].sudo()._get_or_create_chat([usuario.partner_id.id, odoobot.id])
            chat.message_post(
                body=Markup("{} Contéstame aquí SÍ o NO y la marco, o <a href='{}'>ábrela</a> y márcala tú.").format(
                    pregunta, liga),
                author_id=odoobot.id, message_type="comment", subtype_xmlid="mail.mt_comment")
            self.xb_sa_arrival_chat_id = chat
            avisado = True
        if acc.xb_sa_arrival_email and usuario.email:
            self.env["mail.mail"].sudo().create({
                "subject": pregunta, "email_to": usuario.email_formatted, "auto_delete": True,
                "body_html": Markup("<p>{}</p><p><a href='{}'>Abrir la cita</a> y marcarla «Asistió» o «No asistió». "
                                    "Si no llegó, el agente le escribe para reagendar.</p>").format(pregunta, liga),
            })
            avisado = True
        if acc.xb_sa_arrival_activity or not avisado:
            self._xb_sa_todo(usuario, f"{pregunta} Márcalo en la cita: «Asistió» o «No asistió». "
                                      "Si no llegó, el agente le escribe para reagendar.")

    @api.model
    def _xb_sa_arrival_reply(self, canal, texto):
        """La persona de la tienda contestó «SÍ» o «NO» a «¿llegó?»: marca la cita. False si no era eso."""
        pendiente = self.sudo().search([
            "|", ("xb_sa_arrival_channel_id", "=", canal.id), ("xb_sa_arrival_chat_id", "=", canal.id),
            ("appointment_status", "=", "booked"),
            ("start", ">", fields.Datetime.now() - timedelta(days=1))], order="start desc", limit=1)
        if not pendiente:
            return False
        plano = unicodedata.normalize("NFKD", (texto or "").strip().lower())
        plano = "".join(c for c in plano if not unicodedata.combining(c)).strip(" .!¡¿?👍")
        palabras = plano.split()
        if not palabras or len(palabras) > 4:
            return False
        if palabras[0] in ("no",) or plano in ("no llego", "no vino", "no asistio"):
            estado = "no_show"
        elif palabras[0] in ("si", "ya", "llego", "vino", "asistio") or plano == "ok":
            estado = "attended"
        else:
            return False
        quien = pendiente._xb_sa_customer().name or "el cliente"
        pendiente.write({"appointment_status": estado, "xb_sa_arrival_channel_id": False, "xb_sa_arrival_chat_id": False})
        listo = (f"Listo, marqué la cita de {quien} como «Asistió». ¡Gracias!" if estado == "attended"
                 else f"Listo, marqué la cita de {quien} como «No asistió». Le escribo para reagendar.")
        if canal.channel_type == "chat":
            canal.sudo().message_post(body=listo, author_id=self.env.ref("base.partner_root").id,
                                      message_type="comment", subtype_xmlid="mail.mt_comment")
        else:
            pendiente._xb_sa_say(canal, listo)
        return True

    @api.model
    def _xb_sa_cron_followup(self):
        ahora = fields.Datetime.now()
        eventos = self.sudo().search([
            ("xb_sa_channel_id", "!=", False), ("start", ">", ahora - timedelta(days=4)),
            ("start", "<", ahora + XB_REMIND_BEFORE),
            ("appointment_status", "in", ("booked", "no_show")), ("xb_sa_noshow_step", "<", len(XB_NOSHOW_STEPS) + 1)])
        for ev in eventos:
            try:
                with self.env.cr.savepoint():
                    ev._xb_sa_followup(ahora)
            except Exception:  # noqa: BLE001 - una cita no debe frenar a las demás
                _logger.exception("xb_support_agent: falló el seguimiento de la cita %s", ev.id)

    def _xb_sa_followup(self, ahora):
        self.ensure_one()
        canal = self.xb_sa_channel_id
        if not canal.wa_account_id.sudo().xb_sa_enabled:
            return
        cliente = self._xb_sa_customer()
        nombre = (cliente.name or "").split()[0].title() if cliente.name else ""
        hola = f"Hola, {nombre} 👋" if nombre else "Hola 👋"
        dia, hora = self._xb_sa_when(ahora)
        if self.appointment_status == "booked":
            if not self.xb_sa_reminded and ahora < self.start <= ahora + XB_REMIND_BEFORE:
                self.xb_sa_reminded = True
                # Si la apartó hace menos de una hora, ya la tiene fresca: no hace falta recordársela.
                if self.create_date < ahora - timedelta(hours=1):
                    self._xb_sa_say(canal, f"{hola} Te recuerdo tu cita de {dia} a las {hora}{self._xb_sa_where()}. "
                                           "¿Sigue en pie? Si necesitas cambiar el horario, dime y te busco otro.")
            elif not self.xb_sa_store_asked and ahora >= self.start + XB_ASK_STORE_AFTER:
                self.xb_sa_store_asked = True
                self._xb_sa_ask_store(canal, cliente.name or canal.whatsapp_number, hora)
            return
        # No asistió: hasta tres mensajes; si contesta, la plática sigue normal con el agente.
        paso = self.xb_sa_noshow_step
        if paso >= len(XB_NOSHOW_STEPS):
            return
        if self._xb_sa_answered_since(canal, self.start):
            self.xb_sa_noshow_step = len(XB_NOSHOW_STEPS) + 1
            return
        otra = self.sudo().search_count([
            ("id", "!=", self.id), ("start", ">", ahora), ("appointment_type_id", "!=", False),
            "|", ("appointment_booker_id", "=", cliente.id), ("partner_ids", "in", cliente.ids)], limit=1) if cliente else 0
        if otra:  # ya reagendó
            self.xb_sa_noshow_step = len(XB_NOSHOW_STEPS) + 1
            return
        # Aunque la tienda marque tarde la inasistencia, entre un mensaje y otro pasan al menos 18 h.
        if ahora < self.start + XB_NOSHOW_STEPS[paso] or (
                self.xb_sa_noshow_dt and ahora < self.xb_sa_noshow_dt + timedelta(hours=18)):
            return
        horarios = self._xb_sa_offer(canal)
        tipo = self.appointment_type_id
        liga = canal._xb_sa_appointment_url("videollamada" if self.videocall_location else "") if tipo.is_published else ""
        if paso == 0:
            texto = (f"{hola} Te esperábamos {dia} a las {hora}. ¿Todo bien? Si quieres, te aparto otro horario"
                     + (f": {horarios}. ¿Cuál te acomoda?" if horarios else ". ¿Qué día te acomoda?"))
        elif paso == 1:
            texto = (f"{hola} ¿Pudiste ver lo de tu cita? Con gusto te aparto otro horario"
                     + (f": {horarios}." if horarios else ".") + " Me dices cuál te queda 🙂")
        else:
            texto = (f"{hola} Te dejo por aquí la liga para que escojas el horario que mejor te quede: {liga}. "
                     "Aquí sigo para lo que necesites." if liga else
                     f"{hola} Aquí sigo para cuando quieras reagendar tu cita; solo dime qué día te acomoda.")
        self.write({"xb_sa_noshow_step": paso + 1, "xb_sa_noshow_dt": ahora})
        if not self._xb_sa_say(canal, texto):
            # Ya pasaron 24 h sin que escriba: WhatsApp exige plantilla. Que lo vea una persona.
            self.xb_sa_noshow_step = len(XB_NOSHOW_STEPS) + 1
            self._xb_sa_todo(self._xb_sa_lead().user_id or self.user_id,
                             f"{cliente.name or canal.whatsapp_number} no llegó a su cita de {dia} a las {hora} y ya no "
                             "se le puede escribir por WhatsApp sin plantilla (no ha escrito en 24 h). Dale seguimiento.")
        elif paso == len(XB_NOSHOW_STEPS) - 1:
            self._xb_sa_todo(self._xb_sa_lead().user_id or self.user_id,
                             f"{cliente.name or canal.whatsapp_number} no llegó a su cita y no contestó a 3 mensajes "
                             "para reagendar. Dale seguimiento tú.")
