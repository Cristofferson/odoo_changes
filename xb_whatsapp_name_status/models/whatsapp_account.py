# -*- coding: utf-8 -*-
import logging
import re

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.whatsapp.tools.whatsapp_api import WhatsAppApi

_logger = logging.getLogger(__name__)

# Motivos de rechazo que manda Meta, en palabras sencillas.
XB_REASONS = {
    "NAME_NOT_CONSISTENT": "el nombre no coincide con la marca que se ve en el sitio web o en la empresa verificada",
    "NAME_ENDCLIENT_NOTRELATED": "el nombre es de un negocio que no se ve relacionado con la empresa verificada",
    "NAME_FORMAT_UNACCEPTABLE": "el formato no se permite (mayúsculas, símbolos, descripción o eslogan)",
    "NAME_EMPLOYEE_ISSUE": "parece el nombre de un empleado o de una persona",
    "NAME_INDIVIDUAL_ISSUE": "parece el nombre de una persona",
    "UNKNOWN": "Meta no dio el motivo; hay que preguntarle a su soporte",
}
XB_STATUS = [
    ("approved", "Aprobado"),
    ("pending", "En revisión"),
    ("rejected", "Rechazado"),
    ("deferred", "Decisión aplazada"),
    ("none", "Sin solicitud"),
]
# name_status de la API → nuestro estado
XB_API_STATUS = {"APPROVED": "approved", "AVAILABLE_WITHOUT_REVIEW": "approved", "PENDING_REVIEW": "pending",
                 "DECLINED": "rejected", "EXPIRED": "rejected", "NONE": "none"}


class WhatsAppAccount(models.Model):
    _inherit = "whatsapp.account"

    xb_name_requested = fields.Char("Nombre visible pedido", readonly=True, copy=False)
    xb_name_status = fields.Selection(XB_STATUS, string="Estado del nombre en Meta", readonly=True, copy=False)
    xb_name_reason = fields.Char("Motivo del rechazo", readonly=True, copy=False)
    xb_name_checked = fields.Datetime("Revisado", readonly=True, copy=False)

    @api.model
    def _xb_name_update(self, waba_uid, value):
        """Aviso de Meta: ``decision`` (APPROVED / REJECTED / PENDING / DEFERRED) y ``rejection_reason``."""
        numero = re.sub(r"\D", "", value.get("display_phone_number") or "")
        cuentas = self.search([("account_uid", "=", waba_uid)])
        cuenta = cuentas.filtered(lambda a: numero and re.sub(r"\D", "", a.phone_number or "")[-10:] == numero[-10:])[:1]
        if not cuenta:
            _logger.warning("xb_whatsapp_name_status: aviso de nombre sin cuenta (WABA %s, número %s): %s",
                            waba_uid, numero, value)
            return
        decision = (value.get("decision") or "").lower()
        motivo = value.get("rejection_reason") or ""
        cuenta._xb_name_set({"approved": "approved", "rejected": "rejected", "pending": "pending",
                             "deferred": "deferred"}.get(decision, "pending"),
                            value.get("requested_verified_name"), motivo, aviso=True)

    def _xb_name_set(self, estado, nombre, motivo, aviso=False):
        self.ensure_one()
        texto_motivo = XB_REASONS.get(motivo, motivo) if motivo and motivo != "NONE" else ""
        cambio = (estado, nombre or self.xb_name_requested) != (self.xb_name_status, self.xb_name_requested)
        self.write({"xb_name_status": estado, "xb_name_requested": nombre or self.xb_name_requested,
                    "xb_name_reason": texto_motivo or False, "xb_name_checked": fields.Datetime.now()})
        if not (aviso or cambio):
            return
        etiqueta = dict(XB_STATUS)[estado]
        cuerpo = Markup("<p>📛 <b>Nombre visible «%s»: %s</b>%s</p>") % (
            self.xb_name_requested or "?", etiqueta,
            Markup("<br/>Motivo: %s (%s)") % (texto_motivo, motivo) if texto_motivo else "")
        admins = self.env.ref("base.group_system").sudo().user_ids.filtered(lambda u: not u.share and u.active)
        self.message_post(body=cuerpo, partner_ids=admins.partner_id.ids if aviso else [],
                          message_type="comment", subtype_xmlid="mail.mt_comment" if aviso else "mail.mt_note")

    def action_xb_name_check(self):
        """Consulta a Meta el estado del nombre visible de este número."""
        for cuenta in self:
            try:
                res = WhatsAppApi(cuenta)._WhatsAppApi__api_requests(
                    "GET", f"/{cuenta.phone_uid}", auth_type="bearer",
                    params={"fields": "verified_name,name_status,new_name_status,new_display_name"}).json()
            except Exception as e:  # noqa: BLE001
                raise UserError(_("No se pudo consultar a Meta: %s") % e)
            # Si hay un nombre NUEVO en revisión, ese es el que importa.
            nuevo = res.get("new_name_status")
            if nuevo and nuevo != "NONE":
                estado, nombre = XB_API_STATUS.get(nuevo, "pending"), res.get("new_display_name") or cuenta.xb_name_requested
            else:
                estado, nombre = XB_API_STATUS.get(res.get("name_status"), "pending"), res.get("verified_name")
            cuenta._xb_name_set(estado, nombre, cuenta.xb_name_reason if estado == "rejected" else "")
        return True
