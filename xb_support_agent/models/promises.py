# -*- coding: utf-8 -*-
"""Seguimiento de las promesas del agente.

Cuando el agente pasa un tema al equipo («ya le avisé a la tienda») y nadie del equipo le escribe al cliente,
cada 2 horas de tienda abierta el agente vuelve a revisar:
- si ya lo puede resolver solo (el pedido ya está listo, ya entró el pago…), se lo dice al cliente y cierra el pendiente;
- si no, le recuerda al equipo y, una vez por día de tienda, le escribe al cliente que sigue al pendiente;
- con un día de tienda sin respuesta, el aviso al equipo sube a urgente.
Solo dentro del horario de atención de la cuenta y por los pendientes de los últimos 3 días.
"""
import json
import logging
import re
from datetime import timedelta

import pytz
from markupsafe import Markup

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)

XB_PROMISE_EVERY_HOURS = 2        # horas de tienda entre una revisión y otra
XB_PROMISE_URGENT_HOURS = 13      # un día de tienda (8 a 21 h) sin respuesta = urgente
XB_PROMISE_MAX_DAYS = 3           # después de esto ya no se le da seguimiento automático
XB_PROMISE_RUN_MINUTES = 15       # cada cuánto se revisa la lista
XB_PROMISE_MARK = "🔁 Seguimiento del agente"
XB_PROMISE_NONE = "SIN_MENSAJE"

XB_CLOSE_TOOL = {
    "name": "cerrar_pendiente",
    "description": "Marca como RESUELTO el tema que se había pasado al equipo, porque ya se lo resolviste tú al cliente "
                   "(o el cliente ya no lo necesita). Así se deja de darle seguimiento.",
    "input_schema": {"type": "object", "properties": {
        "como": {"type": "string", "description": "En una línea, cómo quedó resuelto."}}, "required": ["como"]},
}


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _xb_sa_promise_store_hours(self, desde):
        """Horas de tienda abierta desde «desde» hasta ahora (calendario de atención de la cuenta)."""
        acc = self.wa_account_id.sudo()
        ahora = fields.Datetime.now()
        calendario = acc.xb_calendar_id if "xb_calendar_id" in acc._fields else False
        if not calendario:
            return (ahora - desde).total_seconds() / 3600
        utc = pytz.utc
        return calendario.get_work_hours_count(utc.localize(desde), utc.localize(ahora), compute_leaves=True)

    def _xb_sa_promise_handoff(self):
        """(trabajo, entrada) del último pasar_a_humano de esta plática."""
        trabajo = self.env["xb.support.job"].sudo().search([
            ("channel_id", "=", self.id), ("log", "ilike", "▸ pasar_a_humano("),
            ("create_date", "<=", (self.xb_sa_hold_dt or fields.Datetime.now()) + timedelta(minutes=5))],
            order="id desc", limit=1)
        entrada = {}
        if trabajo:
            encontrados = re.findall(r"▸ pasar_a_humano\((\{.*?\})\)\n", trabajo.log or "", re.S)
            if encontrados:
                try:
                    entrada = json.loads(encontrados[-1])
                except ValueError:
                    entrada = {}
        return trabajo, entrada

    def _xb_sa_promise_notes(self):
        return self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("message_type", "=", "comment"),
            ("body", "ilike", XB_PROMISE_MARK), ("create_date", ">=", self.xb_sa_hold_dt)], order="id desc")

    def _xb_sa_promise_close(self, motivo):
        self.ensure_one()
        self.sudo().write({"xb_sa_pause_reason": False, "xb_sa_hold_dt": False})
        self.sudo().message_post(body=Markup("<p>✅ %s: %s</p>") % (XB_PROMISE_MARK, motivo),
                                 message_type="comment", subtype_xmlid="mail.mt_note",
                                 author_id=self.env.ref("base.partner_root").id)

    def _xb_sa_tool_cerrar_pendiente(self, job, entrada):
        if self.xb_sa_pause_reason != "handoff":
            return {"ok": True, "nota": "No había nada pendiente."}
        self._xb_sa_promise_close(f"resuelto por el agente — {(entrada.get('como') or '').strip()}")
        return {"ok": True, "nota": "Listo: el pendiente quedó cerrado."}

    def _xb_sa_promise_step(self):
        """Una revisión de la promesa de esta plática. Devuelve lo que hizo (para el registro)."""
        self.ensure_one()
        acc = self.wa_account_id.sudo()
        ahora = fields.Datetime.now()
        root = self.env.ref("base.partner_root")
        # ¿Alguien del equipo ya le escribió al cliente después del aviso? Entonces la promesa se cumplió.
        humano = self.env["mail.message"].sudo().search_count([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("message_type", "=", "whatsapp_message"),
            ("create_date", ">", self.xb_sa_hold_dt), ("author_id", "!=", root.id),
            ("author_id.user_ids.share", "=", False)], limit=1)
        if humano:
            self._xb_sa_promise_close("una persona del equipo ya le contestó")
            return "cumplida por una persona"
        notas = self._xb_sa_promise_notes()
        ultimo = max([self.xb_sa_hold_dt] + notas[:1].mapped("create_date"))
        if self._xb_sa_promise_store_hours(ultimo) < XB_PROMISE_EVERY_HOURS:
            return "aún no toca"
        if self.env["xb.support.job"].sudo().search_count([("channel_id", "=", self.id), ("state", "=", "pending")]):
            return "hay un mensaje del cliente en cola"
        trabajo, entrada = self._xb_sa_promise_handoff()
        resumen = (entrada.get("resumen") or "el tema que se pasó al equipo").strip()
        horas = self._xb_sa_promise_store_hours(self.xb_sa_hold_dt)
        numero = len(notas) + 1
        # ¿Se le puede escribir? WhatsApp solo deja mensajes libres 24 h después del último del cliente.
        ultimo_cliente = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("message_type", "=", "whatsapp_message"),
            ("wa_message_ids.message_type", "=", "inbound")], order="id desc", limit=1)
        ventana = bool(ultimo_cliente and ultimo_cliente.create_date > ahora - timedelta(hours=23, minutes=30))
        escrito_hoy = any("le escribió al cliente" in (n.body or "") and
                          self._xb_sa_promise_store_hours(n.create_date) < XB_PROMISE_URGENT_HOURS for n in notas)
        hizo = "revisó"
        if ventana and acc.xb_sa_enabled and not (self.xb_sa_paused_until and self.xb_sa_paused_until > ahora):
            job = self.env["xb.support.job"].sudo().create({
                "channel_id": self.id, "state": "pending", "reason": f"Seguimiento #{numero} de un pendiente"})
            aviso = (
                f"[Aviso del SISTEMA, no lo escribió el cliente] SEGUIMIENTO #{numero}: hace {horas:.0f} horas de tienda le "
                f"dijiste al cliente que el equipo le contestaría sobre: «{resumen}». Nadie del equipo le ha escrito todavía. "
                "1) Revisa con tus herramientas si YA puedes resolverlo tú (ver_pedidos para ver si ya está listo o pagado, "
                "cotizar, buscar_servicios, anotar_en_pedido, ya_lo_recogio…). Si sí, escríbele la respuesta completa y usa "
                "cerrar_pendiente. 2) Si todavía depende de una persona, "
                + ("NO le escribas: ya le mandaste un seguimiento hoy; contesta exactamente SIN_MENSAJE."
                   if escrito_hoy else
                   "escríbele UN mensaje corto y honesto: que sigues al pendiente y que la tienda aún no te confirma, sin "
                   "prometer horas ni fechas y sin repetir datos que ya le diste. Si el cliente ya dio por cerrado el tema, "
                   "usa cerrar_pendiente y contesta SIN_MENSAJE."))
            try:
                with self.env.cr.savepoint():
                    self.with_context(xb_sa_followup=aviso)._xb_sa_answer(job)
            except Exception as e:  # noqa: BLE001 - un seguimiento nunca tumba la revisión
                _logger.exception("xb_support_agent: falló el seguimiento de la plática %s", self.id)
                job.write({"state": "error", "reason": f"Seguimiento: {e}"[:250]})
            if self.xb_sa_pause_reason != "handoff":
                return "resuelto por el agente"
            hizo = "le escribió al cliente" if job.state in ("done", "draft") and job.reply else "revisó sin escribirle"
        else:
            hizo = "fuera de la ventana de 24 h de WhatsApp: solo aviso al equipo"
        # Aviso al equipo: recordatorio en su bandeja; con un día de tienda sin respuesta, urgente (una vez).
        registro = self.xb_sa_lead_id.sudo() or trabajo or self
        usuarios = acc.xb_sa_support_user_ids | acc.xb_sa_sales_user_ids | (self.xb_sa_lead_id.user_id if self.xb_sa_lead_id else self.env["res.users"])
        urgente = horas >= XB_PROMISE_URGENT_HOURS and not any("urgente" in (n.body or "") for n in notas)
        texto = (f"Sigue pendiente desde hace {horas:.0f} h de tienda ({self.whatsapp_partner_id.name or self.whatsapp_number}, "
                 f"WhatsApp {self.whatsapp_number}): {resumen}")
        if urgente:
            self._xb_sa_notify(registro, usuarios, texto, urgente=True)
        elif usuarios:
            registro.sudo().message_post(body=Markup(tools.plaintext2html(f"🔔 {texto}")),
                                         partner_ids=usuarios.partner_id.ids, subtype_xmlid="mail.mt_comment")
        self.sudo().message_post(
            body=Markup("<p>%s #%s: %s%s.</p>") % (XB_PROMISE_MARK, numero, hizo, " · aviso urgente al equipo" if urgente else ""),
            message_type="comment", subtype_xmlid="mail.mt_note", author_id=self.env.ref("base.partner_root").id)
        return hizo

    @api.model
    def _xb_sa_cron_promises(self):
        """Revisa las promesas pendientes de las cuentas de tienda (dentro de su horario)."""
        params = self.env["ir.config_parameter"].sudo()
        ahora = fields.Datetime.now()
        ultima = params.get_param("xb_support_agent.promises_last_run")
        if ultima and fields.Datetime.to_datetime(ultima) > ahora - timedelta(minutes=XB_PROMISE_RUN_MINUTES):
            return
        params.set_param("xb_support_agent.promises_last_run", fields.Datetime.to_string(ahora))
        cuentas = self.env["whatsapp.account"].sudo().search([("xb_sa_enabled", "=", True), ("xb_sa_profile", "=", "tienda")])
        for acc in cuentas:
            if "xb_calendar_id" in acc._fields and acc.xb_calendar_id and hasattr(acc, "_xb_is_open") and not acc._xb_is_open():
                continue
            canales = self.sudo().search([
                ("wa_account_id", "=", acc.id), ("xb_sa_pause_reason", "=", "handoff"),
                ("xb_sa_hold_dt", ">=", ahora - timedelta(days=XB_PROMISE_MAX_DAYS))])
            for canal in canales:
                try:
                    with self.env.cr.savepoint():
                        hizo = canal._xb_sa_promise_step()
                    _logger.info("xb_support_agent: seguimiento plática %s: %s", canal.id, hizo)
                except Exception:  # noqa: BLE001
                    _logger.exception("xb_support_agent: falló la revisión de la promesa en %s", canal.id)
                self.env.cr.commit()
