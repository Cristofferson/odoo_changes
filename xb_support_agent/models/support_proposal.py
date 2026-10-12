# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class XbSupportProposal(models.Model):
    """Lo que el agente quiere que se haga y que una persona tiene que aprobar:
    un arreglo en el sistema del cliente o dar de alta un número nuevo."""
    _name = "xb.support.proposal"
    _description = "Propuesta del agente de WhatsApp"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char("Resumen", required=True, tracking=True)
    kind = fields.Selection([
        ("fix", "Arreglo en el sistema"),
        ("add_number", "Autorizar un número"),
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

    def _xb_decide(self, state):
        self.write({"state": state, "decided_by_id": self.env.uid,
                    "decided_date": fields.Datetime.now()})
        self.activity_ids.action_feedback(feedback=dict(
            self._fields["state"].selection)[state])

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
                if rec.channel_id:
                    rec.channel_id._xb_sa_send(_(
                        "Listo, ya quedó autorizado el número de %(name)s para %(system)s.",
                        name=rec.new_name, system=rec.project_id.name))
            else:
                # La ejecución automática llega en la fase 2: por ahora una
                # persona lo hace a mano y luego marca «Hecho».
                rec._xb_decide("approved")

    def action_done(self):
        self.filtered(lambda r: r.state in ("pending", "approved"))._xb_decide("done")

    def action_done_notify(self):
        for rec in self.filtered(lambda r: r.state in ("pending", "approved")):
            rec._xb_decide("done")
            if rec.channel_id:
                rec.channel_id._xb_sa_send(_(
                    "Hola, ya quedó atendido: %(name)s. Si algo sigue fallando, "
                    "escríbenos por aquí.", name=rec.name))

    def action_reject(self):
        self.filtered(lambda r: r.state in ("pending", "approved"))._xb_decide("rejected")
