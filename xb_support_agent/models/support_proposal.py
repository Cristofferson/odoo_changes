# -*- coding: utf-8 -*-
import logging
import re
from datetime import datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.tools import html2plaintext as tools_html2plaintext
from odoo.exceptions import UserError


from .support_service import XB_SERVICE_PRODUCT

_logger = logging.getLogger(__name__)
XB_OWNER_TEMPLATE = "solicitudes_agente_xubax"
# Respuestas del dueño por WhatsApp: «SÍ 12», «aprobar #12», «NO 12 ya lo hice yo», «ver solicitudes».
XB_OWNER_YES = re.compile(r"^\W*(s[ií]|aprobar|apruebo|autorizo|ok)\s*#?\s*(\d+)\W*$", re.I)
XB_OWNER_NO = re.compile(r"^\W*(no|rechazar|rechazo)\s*#?\s*(\d+)\b[\s,.:;-]*(.*)$", re.I | re.S)
XB_OWNER_LIST = re.compile(r"^\W*(ver solicitudes|solicitudes|pendientes)\W*$", re.I)
# «Sí» / «No, ya lo hice» sin número: vale si CITA el mensaje de una solicitud (o si solo hay una pendiente).
XB_OWNER_YES_BARE = re.compile(r"^\W*(s[ií]|aprobar|apruebo|autorizo|ok|va|dale)\W*$", re.I)
XB_OWNER_NO_BARE = re.compile(r"^\W*(no|rechazar|rechazo)\b[\s,.:;-]*(.*)$", re.I | re.S)
XB_OWNER_QUOTED_ID = re.compile(r"#(\d+)")


class XbSupportProposal(models.Model):
    """Lo que el agente quiere que se haga y que una persona tiene que aprobar:
    un arreglo en el sistema del cliente o dar de alta un número nuevo.

    El dueño la aprueba o rechaza desde su WhatsApp («SÍ 12» / «NO 12»); al cliente se
    le avisa y, si lo pidió él, se anota el servicio para su cobro del mes. El arreglo
    lo hace una persona del equipo."""
    _name = "xb.support.proposal"
    _description = "Propuesta del agente de WhatsApp"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("Resumen", required=True, tracking=True)
    kind = fields.Selection([
        ("fix", "Arreglo en el sistema"),
        ("add_number", "Autorizar un número"),
        ("b2b", "Verificar cliente (solo negocios)"),
    ], string="Tipo", required=True, default="fix")
    state = fields.Selection([
        ("pending", "Por aprobar"),
        ("approved", "Aprobada"),
        ("done", "Hecha"),
        ("rejected", "Rechazada"),
    ], default="pending", required=True, tracking=True, string="Estado")
    urgency = fields.Selection([
        ("normal", "Normal"),
        ("high", "Urgente"),
    ], default="normal", string="Urgencia")
    channel_id = fields.Many2one("discuss.channel", string="Conversación", ondelete="set null")
    project_id = fields.Many2one("project.project", string="Sistema",
                                 domain=[("database_name", "!=", False)])
    contact_id = fields.Many2one("xb.support.contact", string="Lo pidió")
    whatsapp_number = fields.Char("Número que escribió")
    problem = fields.Text("Qué encontró el agente")
    suggestion = fields.Text("Qué propone hacer")
    new_name = fields.Char("Nombre a autorizar")
    new_phone = fields.Char("Celular a autorizar")
    new_role = fields.Selection([("owner", "Titular"), ("employee", "Empleado")],
                                string="Tipo a autorizar", default="employee")
    decided_by_id = fields.Many2one("res.users", string="Decidió", readonly=True)
    decided_date = fields.Datetime("Fecha de decisión", readonly=True)
    billable = fields.Boolean("Se cobra al cliente", help="Lo pidió el cliente: se suma a su cobro del mes.")
    minutes = fields.Integer("Minutos a cobrar", default=15)
    service_id = fields.Many2one("xb.support.service", string="Servicio cobrado", readonly=True, copy=False)
    owner_notified_dt = fields.Datetime("Se le pidió al dueño", readonly=True, copy=False)
    reject_reason = fields.Char("Motivo del rechazo")
    partner_id = fields.Many2one("res.partner", string="Cliente a verificar")

    @api.model
    def _get_whatsapp_safe_fields(self):
        return {"name", "project_id.name"}

    def _xb_decide(self, state):
        self.write({"state": state, "decided_by_id": self.env.uid,
                    "decided_date": fields.Datetime.now()})
        self.activity_ids.action_feedback(feedback=dict(
            self._fields["state"].selection)[state])

    # ------------------------------------------------------------------
    # Aprobar / rechazar
    # ------------------------------------------------------------------
    def action_approve(self):
        for rec in self.filtered(lambda r: r.state == "pending"):
            if rec.kind == "add_number":
                if not (rec.project_id and rec.new_phone and rec.new_name):
                    raise UserError(_("Para autorizar el número elige el sistema y "
                                      "revisa nombre y celular."))
                self.env["xb.support.contact"].create({
                    "name": rec.new_name,
                    "phone": rec.new_phone,
                    "project_id": rec.project_id.id,
                    "role": rec.new_role or "employee",
                    "can_billing": rec.new_role == "owner",
                    "note": _("Alta aprobada desde la propuesta %s") % rec.id,
                })
                rec._xb_decide("done")
                rec._xb_tell_client(_("Listo, ya quedó autorizado el número de %(name)s para %(system)s.",
                                      name=rec.new_name, system=rec.project_id.name))
            elif rec.kind == "b2b":
                categoria = rec.channel_id.wa_account_id.sudo().xb_sa_store_b2b_category_id
                if not (categoria and rec.partner_id):
                    raise UserError(_("Falta el cliente o la etiqueta de verificación de la cuenta de WhatsApp."))
                clientes = rec.partner_id | rec.partner_id.commercial_partner_id
                clientes.sudo().write({"category_id": [(4, categoria.id)]})
                rec._xb_decide("done")
                rec._xb_tell_client(_("¡Listo, %(name)s! Ya quedó verificado tu negocio con %(company)s. Dime qué piedra "
                                      "buscas y te paso opciones con precio. 💎", name=rec.partner_id.name.split()[0],
                                      company=rec._xb_where()))
            else:
                rec._xb_decide("approved")
                rec._xb_bill()
                rec._xb_notify_team(_("Arreglo aprobado para hacer en %(system)s: %(name)s",
                                      system=rec.project_id.name or "-", name=rec.name))
                if rec.billable:
                    rec._xb_tell_client(_("Ya quedó autorizado: «%s». Una persona del equipo lo hace en horario "
                                          "de oficina y te confirma por aquí.") % rec.name)
        return True

    def _xb_bill(self):
        """Si lo pidió el cliente, deja el servicio en manos del equipo; al marcarlo hecho entra al cobro del mes."""
        self.ensure_one()
        if not (self.billable and self.project_id) or self.service_id:
            return
        self.service_id = self.env["xb.support.service"].sudo().create({
            "name": self.name, "state": "team", "executor": "team",
            "channel_id": self.channel_id.id, "project_id": self.project_id.id, "contact_id": self.contact_id.id,
            "whatsapp_number": self.whatsapp_number, "minutes": max(self.minutes, 15),
            "preview": self.suggestion, "quote_dt": self.create_date,
            "authorized_dt": self.decided_date or fields.Datetime.now(),
        })

    def action_done(self):
        for rec in self.filtered(lambda r: r.state in ("pending", "approved")):
            rec._xb_decide("done")
            if rec.service_id.state == "team":
                rec.service_id.action_done()

    def action_done_notify(self):
        for rec in self.filtered(lambda r: r.state in ("pending", "approved")):
            rec.action_done()
            rec._xb_tell_client(_("Hola, ya quedó atendido: %(name)s. Si algo sigue fallando, "
                                  "escríbenos por aquí.", name=rec.name))

    def action_reject(self):
        for rec in self.filtered(lambda r: r.state in ("pending", "approved")):
            rec._xb_decide("rejected")
            if rec.service_id.state == "team":
                rec.service_id.action_cancel()
            if rec.kind == "b2b":
                rec._xb_tell_client(_("Gracias por mandarnos tus datos. Por ahora no pudimos verificar tu negocio como "
                                      "joyería.%(reason)s Si crees que es un error, cuéntanos por aquí.",
                                      reason=f" {rec.reject_reason}." if rec.reject_reason else ""))
            elif rec.billable:
                rec._xb_tell_client(_("Sobre «%(name)s»: por ahora no lo vamos a hacer.%(reason)s Si quieres, "
                                      "lo platicamos por aquí.", name=rec.name,
                                      reason=f" {rec.reject_reason}." if rec.reject_reason else ""))

    # ------------------------------------------------------------------
    # Avisos
    # ------------------------------------------------------------------
    def _xb_tell_client(self, texto):
        """Al cliente por su plática, solo dentro de las 24 h de WhatsApp. Devuelve si se pudo."""
        self.ensure_one()
        canal = self.channel_id
        if not (canal and self._xb_window_open(canal)):
            if canal:
                self._xb_notify_team(_("No se le pudo avisar al cliente de «%(name)s» (pasaron 24 h desde su último "
                                       "mensaje). Mensaje pendiente: %(text)s", name=self.name, text=texto))
            return False
        try:
            canal._xb_sa_send(texto)
            return True
        except Exception:  # noqa: BLE001
            _logger.warning("xb_support_agent: no se pudo avisar al cliente de la propuesta %s", self.id)
            return False

    def _xb_notify_team(self, texto, urgente=False):
        acc = self.channel_id.wa_account_id.sudo() or self._xb_owner_account()
        if acc:
            self.env["discuss.channel"]._xb_sa_notify(self, acc.xb_sa_support_user_ids, texto, urgente)

    @api.model
    def _xb_window_open(self, canal):
        """¿Esa persona escribió en las últimas 23 h? (fuera de eso WhatsApp exige plantilla)."""
        mensajes = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", canal.id), ("message_type", "=", "whatsapp_message"),
            ("date", ">", fields.Datetime.now() - timedelta(hours=23))], order="id desc", limit=20)
        return any(m.wa_message_ids.filtered(lambda w: w.message_type == "inbound") for m in mensajes)

    @api.model
    def _xb_owner_account(self):
        return self.env["whatsapp.account"].sudo().search(
            [("xb_sa_enabled", "=", True), ("xb_sa_approver_phone", "!=", False)], limit=1)

    @api.model
    def _xb_owner_number(self, acc):
        numero = re.sub(r"\D", "", acc.xb_sa_approver_phone or "")
        return "52" + numero if len(numero) == 10 else numero

    @api.model
    def _xb_owner_channel(self):
        acc = self._xb_owner_account()
        if not acc:
            return self.env["discuss.channel"]
        return self.env["discuss.channel"].sudo()._get_whatsapp_channel(
            self._xb_owner_number(acc), acc, sender_name=_("Aprobaciones del agente"), create_if_not_found=True)

    @api.model
    def _xb_hour_price(self):
        return self.env["product.product"].sudo().browse(XB_SERVICE_PRODUCT).lst_price or 680.0

    def _xb_where(self):
        """Dónde aplica: el sistema del cliente o, al verificar un cliente, la empresa de la cuenta de WhatsApp."""
        self.ensure_one()
        if self.kind == "b2b":
            return self.channel_id.wa_account_id.sudo().xb_sa_company_name or self.channel_id.wa_account_id.name
        return self.project_id.name or _("sin sistema")

    def _xb_owner_line(self):
        self.ensure_one()
        partes = [f"*#{self.id}* · {self._xb_where()}"
                  f"{' · 🚨 urgente' if self.urgency == 'high' else ''}", self.name]
        if self.kind == "add_number":
            partes.append(_("Dar acceso a %(name)s (%(phone)s).", name=self.new_name, phone=self.new_phone))
        elif self.kind == "b2b":
            partes.append(self.problem or "")
            partes.append(_("Su constancia quedó en su contacto. Si apruebas, ya puede ver precios y comprar."))
        else:
            if self.problem:
                partes.append(_("Qué pasa: %s") % self.problem[:400])
            if self.suggestion:
                partes.append(_("Propuesta: %s") % self.suggestion[:400])
            partes.append(_("Se cobra: %(min)s min ($%(amount)s más IVA).", min=self.minutes,
                            amount=f"{self.minutes / 60.0 * self._xb_hour_price():,.2f}")
                          if self.billable else _("Sin cobro."))
        partes.append(_("Responde *SÍ %(id)s* para aprobar o *NO %(id)s* para rechazar.", id=self.id))
        return "\n".join(partes)

    def _xb_ask_owner(self):
        """Le pide al dueño que decida: el detalle si la ventana de 24 h está abierta; si no, la plantilla."""
        pendientes = self.filtered(lambda r: r.state == "pending")
        canal = self._xb_owner_channel()
        if not (pendientes and canal):
            return False
        if self._xb_window_open(canal):
            for rec in pendientes:
                canal._xb_sa_send(rec._xb_owner_line())
        elif not self._xb_owner_template_ping(canal, pendientes[0]):
            return False
        pendientes.write({"owner_notified_dt": fields.Datetime.now()})
        return True

    @api.model
    def _xb_owner_template_ping(self, canal, propuesta):
        """Fuera de las 24 h: plantilla con el botón «Ver solicitudes»."""
        tmpl = self.env["whatsapp.template"].sudo().search([
            ("template_name", "=", XB_OWNER_TEMPLATE), ("wa_account_id", "=", canal.wa_account_id.id),
            ("status", "=", "approved")], limit=1)
        if not tmpl:
            _logger.warning("xb_support_agent: falta la plantilla aprobada %s", XB_OWNER_TEMPLATE)
            return False
        composer = self.env["whatsapp.composer"].sudo().with_context(
            active_model=self._name, active_id=propuesta.id, default_wa_template_id=tmpl.id,
        ).create({"phone": "+" + canal.whatsapp_number, "wa_template_id": tmpl.id, "res_model": self._name})
        composer._send_whatsapp_template()
        return True

    @api.model
    def _xb_is_owner_channel(self, canal):
        """¿Es la plática del dueño (donde llegan las solicitudes)?"""
        acc = self._xb_owner_account()
        if not (acc and canal.wa_account_id == acc):
            return False
        numero = self._xb_owner_number(acc)[-10:]
        return bool(numero) and (canal.whatsapp_number or "").endswith(numero)

    @api.model
    def _xb_quoted_id(self, message):
        """Número de la solicitud del mensaje que el dueño citó al contestar («*#5* · …»)."""
        citado = message.parent_id if message else False
        if not citado:
            return None
        hallado = XB_OWNER_QUOTED_ID.search(tools_html2plaintext(citado.body or "")[:80])
        return int(hallado.group(1)) if hallado else None

    @api.model
    def _xb_last_bot_was_request(self, canal):
        """¿Lo último que le escribió el agente al dueño fue una solicitud (o el resumen de la mañana)?"""
        ultimo = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", canal.id), ("message_type", "=", "whatsapp_message"),
            ("author_id", "=", self.env.ref("base.partner_root").id)], order="id desc", limit=1)
        cuerpo = ultimo.body or ""
        return "#" in cuerpo and any(p in cuerpo for p in ("SÍ", "aprobada", "rechazada", "¿Cuál?", "ya estaba"))

    @api.model
    def _xb_owner_command(self, canal, texto, message=None):
        """Respuesta del dueño (desde su WhatsApp o escrita en su plática en Odoo). Devuelve True si era
        una orden (y no va al agente). «SÍ 5» siempre vale; un «Sí» a secas vale si cita el mensaje de la
        solicitud o si solo hay una pendiente; si no, se le pregunta cuál."""
        if not self._xb_is_owner_channel(canal):
            return False
        numero = self._xb_owner_number(self._xb_owner_account())[-10:]
        texto = (texto or "").strip()
        si, no, lista = XB_OWNER_YES.match(texto), XB_OWNER_NO.match(texto), XB_OWNER_LIST.match(texto)
        rec_id, motivo, aprobar = None, "", None
        if si or no:
            rec_id, aprobar = int((si or no).group(2)), bool(si)
            motivo = no.group(3) if no else ""
        elif not lista:
            si_solo, no_solo = XB_OWNER_YES_BARE.match(texto), XB_OWNER_NO_BARE.match(texto)
            citado = self._xb_quoted_id(message)
            if not (si_solo or no_solo) or (no_solo and not citado):
                return False  # «no …» sin citar una solicitud es plática normal
            if not citado and not self._xb_last_bot_was_request(canal):
                return False  # «sí» que contesta otra pregunta del agente
            aprobar = bool(si_solo)
            motivo = no_solo.group(2) if no_solo else ""
            if citado:
                rec_id = citado
            else:
                pendientes = self.sudo().search([("state", "=", "pending")])
                if len(pendientes) != 1:
                    if not pendientes:
                        return False  # un «sí» suelto sin nada pendiente: es plática normal
                    canal._xb_sa_send(_(
                        "¿Cuál? Hay %(n)s solicitudes pendientes (%(ids)s). Contesta citando el mensaje de la "
                        "solicitud, o escribe *SÍ 5* / *NO 5*.", n=len(pendientes),
                        ids=", ".join(f"#{i}" for i in pendientes.sorted("id").ids)))
                    return True
                rec_id = pendientes.id
        dueno = self.env["res.users"].sudo().search([("partner_id.phone_sanitized", "like", "%" + numero)], limit=1)
        yo = self.with_user(dueno).sudo() if dueno else self.sudo()
        if lista:
            pendientes = yo.search([("state", "=", "pending")], order="id")
            if not pendientes:
                canal._xb_sa_send(_("No hay solicitudes pendientes. 🙌"))
            for rec in pendientes:
                canal._xb_sa_send(rec._xb_owner_line())
            return True
        rec = yo.browse(rec_id).exists()
        if not rec:
            canal._xb_sa_send(_("No encontré la solicitud #%s.") % rec_id)
        elif rec.state != "pending":
            canal._xb_sa_send(_("La #%(id)s ya estaba %(state)s.", id=rec.id,
                                state=dict(rec._fields["state"].selection)[rec.state].lower()))
        elif aprobar:
            rec.action_approve()
            canal._xb_sa_send(_("👍 #%(id)s aprobada.%(extra)s", id=rec.id,
                                extra=_(" Quedó como tarea para el equipo.") if rec.state == "approved" else ""))
        else:
            rec.reject_reason = (motivo or "").strip()[:200] or False
            rec.action_reject()
            canal._xb_sa_send(_("👌 #%s rechazada.") % rec.id)
        return True

    @api.model
    def _cron_owner_digest(self):
        """Cada mañana, UNA vez al día: la lista corta de lo que sigue esperando decisión
        (el detalle de cada una ya le llegó al crearse; «ver solicitudes» lo repite)."""
        pendientes = self.sudo().search([("state", "=", "pending")], order="id")
        if not pendientes:
            return
        # Al actualizar el módulo el cron puede correr otra vez el mismo día: solo la primera vale.
        Param = self.env["ir.config_parameter"].sudo()
        hoy = datetime.now(pytz.timezone("America/Mexico_City")).date().isoformat()
        if Param.get_param("xb_support_agent.digest_date") == hoy:
            return
        canal = self._xb_owner_channel()
        if not canal:
            return
        if self._xb_window_open(canal):
            lineas = [_("Buenos días. Siguen esperando tu decisión (%s):") % len(pendientes)]
            lineas += [f"• *#{r.id}* · {r._xb_where()} · {r.name}"
                       f"{' 🚨' if r.urgency == 'high' else ''}" for r in pendientes]
            lineas.append(_("Responde *SÍ n* o *NO n*. Para ver el detalle de todas, escribe *ver solicitudes*."))
            canal._xb_sa_send("\n".join(lineas))
            pendientes.write({"owner_notified_dt": fields.Datetime.now()})
        elif not self._xb_owner_template_ping(canal, pendientes[0]):
            return
        Param.set_param("xb_support_agent.digest_date", hoy)

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs.filtered(lambda r: r.state == "pending"):
            try:
                rec._xb_ask_owner()
            except Exception:  # noqa: BLE001 - que no avise no debe impedir guardar la propuesta
                _logger.exception("xb_support_agent: no se pudo avisar al dueño de la propuesta %s", rec.id)
        return recs
