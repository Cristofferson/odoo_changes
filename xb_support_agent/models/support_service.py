# -*- coding: utf-8 -*-
"""Servicio de escritura: lo que el cliente pide que hagamos por él y se cobra.

Consultar y explicar está incluido; hacerlo por el cliente se cobra como tiempo
de servicio (producto «Hora de servicios»), mínimo 15 minutos por tarea. Cada
servicio queda con la cotización que se le dio, el «SÍ» del titular y lo que se
hizo; a fin de mes se juntan los de cada cliente en una orden de venta.
"""
import json
import logging
import math
import re
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
XB_SERVICE_PRODUCT = 1828          # [0001029] Hora de servicios ($680)
XB_MIN_MINUTES = 15
XB_AI_MAX_MINUTES = 60
XB_QUOTE_HOURS = 24
# «Sí», «si», «sí, adelante», «autorizo», «ok», «de acuerdo», «hágalo»…
XB_YES = re.compile(r"^\W*(s[ií]|sip|claro|ok|okay|autorizo|adelante|de acuerdo|h[aá]g[ao]l[oa]|dale)\b", re.I)


class XbSupportService(models.Model):
    _name = "xb.support.service"
    _description = "Servicio cobrado del agente de WhatsApp"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("Qué se hace", required=True, tracking=True)
    state = fields.Selection([
        ("quoted", "Cotizado (espera el SÍ)"),
        ("team", "Autorizado: lo hace el equipo"),
        ("done", "Hecho"),
        ("cancelled", "Cancelado"),
    ], default="quoted", required=True, tracking=True, string="Estado")
    executor = fields.Selection([("ai", "La IA"), ("team", "El equipo")], string="Lo hace", required=True)
    channel_id = fields.Many2one("discuss.channel", string="Conversación", ondelete="set null")
    project_id = fields.Many2one("project.project", string="Sistema", required=True)
    partner_id = fields.Many2one("res.partner", related="project_id.partner_id", store=True, string="Se le cobra a")
    contact_id = fields.Many2one("xb.support.contact", string="Lo pidió")
    approver_id = fields.Many2one(
        "xb.support.contact", string="Debe autorizarlo",
        help="Si lo pidió un invitado, el titular que lo invitó es quien tiene que responder SÍ (desde su número).")
    whatsapp_number = fields.Char("Número")
    operations = fields.Text("Operaciones (JSON)")
    preview = fields.Text("Lo que se le enseñó al cliente")
    result = fields.Text("Lo que se hizo")
    minutes = fields.Integer("Minutos cobrados", default=XB_MIN_MINUTES, tracking=True)
    currency_id = fields.Many2one("res.currency", default=lambda s: s.env.ref("base.MXN"))
    amount = fields.Monetary("Importe (más IVA)", compute="_compute_amount", store=True)
    quote_dt = fields.Datetime("Cotizado", default=fields.Datetime.now)
    authorized_dt = fields.Datetime("Autorizado")
    authorization_message_id = fields.Many2one("mail.message", string="Mensaje con el SÍ")
    done_dt = fields.Datetime("Hecho")
    sale_order_id = fields.Many2one("sale.order", string="Orden de venta", copy=False, tracking=True)

    @api.depends("minutes")
    def _compute_amount(self):
        precio = self.env["product.product"].sudo().browse(XB_SERVICE_PRODUCT).lst_price or 680.0
        for rec in self:
            rec.amount = rec.minutes / 60.0 * precio

    @api.model
    def _xb_round_minutes(self, minutos, maximo=None):
        m = max(XB_MIN_MINUTES, int(math.ceil((minutos or 0) / XB_MIN_MINUTES) * XB_MIN_MINUTES))
        return min(m, maximo) if maximo else m

    @api.model
    def _xb_inbound_yes(self, channel, since, horas=XB_QUOTE_HOURS):
        """Un «SÍ» entrante del cliente en esa plática, después de ``since`` y dentro de ``horas``.
        Se busca en código, no se le cree al modelo."""
        if not channel or not since or fields.Datetime.now() - since > timedelta(hours=horas):
            return False
        mensajes = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", channel.id),
            ("message_type", "=", "whatsapp_message"), ("create_date", ">", since),
        ], order="id desc", limit=5)
        for m in mensajes:
            if not m.wa_message_ids.filtered(lambda w: w.message_type == "inbound"):
                continue
            if XB_YES.search(re.sub(r"<[^>]+>", " ", m.body or "")):
                return m
        return False

    def _xb_authorization(self, channel=None):
        """El SÍ debe venir de quien autoriza: en la plática del invitado no cuenta, en la del titular sí."""
        self.ensure_one()
        return self._xb_inbound_yes(channel or self.channel_id, self.quote_dt)

    def _xb_ask_approver(self):
        """Le pide el SÍ al titular por su WhatsApp (si escribió hace menos de 23 h). Devuelve si pudo avisarle."""
        self.ensure_one()
        from .support_contact import xb_phone_key
        ap = self.approver_id
        canal = self.env["discuss.channel"].sudo().search([
            ("channel_type", "=", "whatsapp"), ("wa_account_id", "=", self.channel_id.wa_account_id.id),
            ("whatsapp_number", "like", "%" + xb_phone_key(ap.phone))], limit=1)
        if not canal:
            return False
        ultimos = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", canal.id), ("message_type", "=", "whatsapp_message"),
            ("date", ">", fields.Datetime.now() - timedelta(hours=23))], order="id desc", limit=10)
        if not any(m.wa_message_ids.filtered(lambda w: w.message_type == "inbound") for m in ultimos):
            return False
        canal._xb_sa_send(
            f"Hola, {self.contact_id.name} pide en {self.project_id.name}: {self.name}. "
            f"Cuesta ${self.amount:,.2f} más IVA ({self.minutes} min de servicio). "
            f"Si lo autorizas, responde SÍ; si no, ignora este mensaje.")
        return True

    @api.model
    def _xb_cap_minutes(self):
        return int(self.env["ir.config_parameter"].sudo().get_param("xb_support_agent.service_cap_minutes", 180))

    @api.model
    def _xb_month_minutes(self, project):
        """Minutos ya autorizados este mes en ese sistema."""
        inicio = fields.Datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        previos = self.sudo().search([("project_id", "=", project.id), ("state", "in", ("team", "done")),
                                      ("authorized_dt", ">=", inicio)])
        return sum(previos.mapped("minutes"))

    def _xb_notify_authorizers(self):
        """Correo a quienes autorizan servicios en su sistema: quién autorizó, qué y cuánto."""
        from . import client_query
        self.ensure_one()
        try:
            gente = client_query.autorizadores_de(self.env, self.project_id)
        except Exception:  # noqa: BLE001 - el aviso no debe tumbar el servicio
            return
        correos = [mail for _n, mail in gente if mail and "@" in mail]
        if not correos:
            return
        cuerpo = Markup(
            "<p>Se autorizó un servicio de XUBAX en <b>%s</b>.</p><ul><li>Autorizó: <b>%s</b> (por WhatsApp)</li>"
            "<li>Servicio: %s</li><li>Tiempo: %s min · $%s más IVA</li></ul>"
            "<p>Se suma a la factura del mes. Si no lo reconoces, responde a este correo.</p>") % (
            self.project_id.name, (self.approver_id or self.contact_id).name or self.whatsapp_number, self.name, self.minutes,
            f"{self.amount:,.2f}")
        self.env["mail.mail"].sudo().create({
            "subject": "Servicio autorizado por WhatsApp · %s" % self.project_id.name,
            "body_html": cuerpo, "email_to": ",".join(correos), "auto_delete": True}).send()

    # ------------------------------------------------------------------
    # Botones del equipo
    # ------------------------------------------------------------------
    def action_done(self):
        for rec in self.filtered(lambda r: r.state == "team"):
            rec.write({"state": "done", "done_dt": fields.Datetime.now()})
            rec.activity_ids.action_feedback(feedback=_("Hecho"))

    def action_done_notify(self):
        for rec in self.filtered(lambda r: r.state == "team"):
            rec.action_done()
            if rec.channel_id:
                rec.channel_id._xb_sa_send(_("Listo, ya quedó: %s.") % rec.name)

    def action_cancel(self):
        self.filtered(lambda r: r.state in ("quoted", "team") and not r.sale_order_id).write({"state": "cancelled"})

    def action_create_sale_orders(self):
        """Junta los servicios hechos y sin cobrar de cada cliente en una orden de venta."""
        pendientes = self.filtered(lambda r: r.state == "done" and not r.sale_order_id)
        if not pendientes:
            raise UserError(_("No hay servicios hechos pendientes de cobrar en lo seleccionado."))
        sin_cliente = pendientes.filtered(lambda r: not r.partner_id).project_id
        if sin_cliente:
            raise UserError(_("Falta decir a quién se le cobra (campo Cliente del proyecto) en: %s")
                            % ", ".join(sin_cliente.mapped("name")))
        ordenes = self.env["sale.order"]
        for partner in pendientes.partner_id:
            ordenes |= self._xb_make_order(pendientes.filtered(lambda r: r.partner_id == partner))
        return {"type": "ir.actions.act_window", "res_model": "sale.order", "name": _("Órdenes de servicios"),
                "view_mode": "list,form", "domain": [("id", "in", ordenes.ids)]}

    def _xb_make_order(self, servicios):
        """Una orden de venta (borrador) con todos esos servicios, del mismo cliente."""
        producto = self.env["product.product"].browse(XB_SERVICE_PRODUCT)
        orden = self.env["sale.order"].create({
            "partner_id": servicios.partner_id.id,
            "company_id": producto.company_id.id or self.env.company.id,
            "origin": _("Servicios del agente de WhatsApp"),
            # Suscripciones pone un plan recurrente por omisión: estas órdenes son de cobro único.
            **({"plan_id": False} if "plan_id" in self.env["sale.order"]._fields else {}),
            "order_line": [(0, 0, {
                "product_id": producto.id,
                "name": f"{s.done_dt:%d/%m/%Y} · {s.project_id.name} · {s.name}",
                "product_uom_qty": s.minutes / 60.0,
            }) for s in servicios.sorted("done_dt")],
        })
        servicios.sale_order_id = orden
        return orden

    def _xb_send_order(self, orden, force=True):
        """Manda la orden por correo: al correo del cliente o, si no tiene, a quienes
        autorizan servicios en sus sistemas. Devuelve la lista de correos usados."""
        from . import client_query
        correos = [orden.partner_id.email] if orden.partner_id.email else []
        if not correos:
            for proyecto in self.mapped("project_id"):
                try:
                    correos += [m for _n, m in client_query.autorizadores_de(self.env, proyecto) if m and "@" in m]
                except Exception:  # noqa: BLE001
                    continue
        correos = sorted(set(correos))
        plantilla = self.env.ref("sale.email_template_edi_sale", raise_if_not_found=False)
        if not (correos and plantilla):
            return []
        plantilla.sudo().send_mail(orden.id, force_send=force, email_layout_xmlid="mail.mail_notification_light",
                                   email_values={"email_to": ",".join(correos), "recipient_ids": [(5, 0, 0)]})
        orden.sudo().write({"state": "sent"})
        orden.sudo().message_post(body=_("Enviada automáticamente por correo a: %s") % ", ".join(correos),
                                  message_type="comment", subtype_xmlid="mail.mt_note")
        return correos

    @api.model
    def _cron_monthly_billing(self, enviar=True, force=True):
        """El día 1: junta los servicios hechos antes de este mes, una orden por cliente,
        y la manda por correo. Avisa al equipo de lo que hizo (y de lo que no pudo)."""
        inicio = fields.Datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pendientes = self.sudo().search([("state", "=", "done"), ("sale_order_id", "=", False),
                                         ("done_dt", "<", inicio)])
        cuentas = self.env["whatsapp.account"].sudo().search([("xb_sa_enabled", "=", True)])
        equipo = cuentas.xb_sa_support_user_ids
        resumen, ordenes = [], self.env["sale.order"]
        for partner in pendientes.partner_id:
            servicios = pendientes.filtered(lambda r: r.partner_id == partner)
            try:
                with self.env.cr.savepoint():
                    orden = self._xb_make_order(servicios)
                    correos = servicios._xb_send_order(orden, force=force) if enviar else []
                ordenes |= orden
                resumen.append(f"{orden.name} · {partner.name} · ${orden.amount_total:,.2f} · " +
                               (("enviada a " + ", ".join(correos)) if correos else "SIN correo: revísala y envíala tú"))
            except Exception as e:  # noqa: BLE001 - un cliente con problema no frena a los demás
                _logger.exception("xb_support_agent: cobro mensual de %s", partner.display_name)
                resumen.append(f"{partner.display_name}: ERROR {e}")
        sin_cliente = pendientes.filtered(lambda r: not r.partner_id)
        if sin_cliente:
            resumen.append("Sin cliente de facturación en el proyecto: " + ", ".join(sin_cliente.project_id.mapped("name")))
        if resumen and equipo:
            texto = "Cobro mensual de servicios del agente de WhatsApp:\n" + "\n".join(resumen)
            ancla = pendientes[:1]
            for user in equipo:
                ancla.activity_schedule("mail.mail_activity_data_todo", summary="Cobro mensual de servicios",
                                        note=texto, user_id=user.id)
        return ordenes

    def _xb_note(self):
        self.ensure_one()
        return Markup(
            "<p>🤖 Hecho por el Agente IA de XUBAX a petición de <b>%s</b> por WhatsApp "
            "(servicio #%s, autorizado el %s).</p>") % (
            self.contact_id.name or self.whatsapp_number, self.id,
            fields.Datetime.context_timestamp(self, self.authorized_dt).strftime("%d/%m/%Y %H:%M"))

    def _xb_preview_text(self, hechos):
        lineas = []
        for h in hechos:
            t = f"- {h['accion']} {h['modelo']}: {h['nombre']}"
            if h.get("total") is not None:
                t += f" (total ${h['total']:,.2f})"
            lineas.append(t)
        return "\n".join(lineas)

    @api.model
    def _xb_dump(self, datos):
        return json.dumps(datos, ensure_ascii=False, default=str)
