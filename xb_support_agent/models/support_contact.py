# -*- coding: utf-8 -*-
import logging
import re
import time

from odoo import api, fields, models

_logger = logging.getLogger(__name__)
XB_LOCAL_SERVER = "odoo19"
_XB_RESOLVE_CACHE = {}


def xb_phone_key(number):
    """Llave de comparación de un teléfono: los últimos 10 dígitos.

    WhatsApp entrega ``+5214433244511`` y en Odoo se captura ``443 324 4511``,
    ``+52 443 324 4511``... Los 10 dígitos finales son el número nacional en
    México y bastan para distinguir a una persona.
    """
    digitos = re.sub(r"\D", "", number or "")
    return digitos[-10:] if len(digitos) >= 10 else ""


class XbSupportContact(models.Model):
    _name = "xb.support.contact"
    _description = "Número autorizado para soporte por WhatsApp"
    _order = "project_id, role, name"

    name = fields.Char("Nombre", required=True)
    phone = fields.Char("Celular", required=True)
    phone_key = fields.Char("Llave del celular", compute="_compute_phone_key",
                            store=True, index=True)
    project_id = fields.Many2one(
        "project.project", string="Sistema", required=True, ondelete="cascade",
        domain=[("database_name", "!=", False)], index=True)
    database_name = fields.Char(related="project_id.database_name", string="Base de datos")
    partner_id = fields.Many2one("res.partner", string="Contacto en Odoo")
    role = fields.Selection([
        ("owner", "Titular"),
        ("employee", "Empleado"),
    ], string="Tipo", required=True, default="employee")
    can_billing = fields.Boolean(
        "Puede ver temas de dinero",
        help="Facturas, pagos y precios de SU cuenta. Aun así el agente pasa "
             "los temas de dinero a una persona.")
    active = fields.Boolean(default=True)
    note = fields.Text("Notas")
    # Identidad tomada del sistema del cliente (el teléfono del usuario de Odoo).
    auto = fields.Boolean("Identificado por teléfono", readonly=True)
    remote_user_id = fields.Integer("Usuario en su sistema (id)", readonly=True)
    remote_login = fields.Char("Usuario en su sistema", readonly=True)
    confirmed_user_id = fields.Integer("Usuario confirmado (id)", readonly=True,
                                       help="El usuario que la persona confirmó ser por WhatsApp.")
    challenge_dt = fields.Datetime("Se le pidió confirmar", readonly=True)
    confirmed = fields.Boolean("Identidad confirmada", compute="_compute_confirmed")
    guest = fields.Boolean(
        "Invitado del titular", readonly=True,
        help="Persona sin usuario en su sistema a la que el titular dio acceso por WhatsApp. Consulta sin "
             "dinero, recibe capturas (sin pantallas de dinero) y puede pedir cambios con costo, que autoriza el titular "
             "con un SÍ desde su número; ve lo mismo que el titular que la invitó. Si luego tiene usuario propio con ese teléfono, se reconoce como usuario.")
    guest_by = fields.Char("Autorizado por", readonly=True)

    @api.depends("remote_user_id", "confirmed_user_id", "guest")
    def _compute_confirmed(self):
        for rec in self:
            rec.confirmed = bool(rec.guest or (rec.remote_user_id and rec.remote_user_id == rec.confirmed_user_id))

    _phone_project_unique = models.Constraint(
        "UNIQUE(phone_key, project_id)",
        "Ese celular ya está autorizado en este sistema.")

    @api.depends("phone")
    def _compute_phone_key(self):
        for rec in self:
            rec.phone_key = xb_phone_key(rec.phone)

    @api.onchange("role")
    def _onchange_role(self):
        self.can_billing = self.role == "owner"

    @api.model
    def _xb_find(self, number):
        return self._xb_resolve(number).filtered("confirmed")

    @api.model
    def _xb_resolve(self, number):
        """Quién es este número: el USUARIO de Odoo, activo e interno, de algún sistema
        con soporte activo, cuyo teléfono (últimos 10 dígitos) coincide.

        * Exactamente un usuario por sistema; si hay dos, no se liga y se avisa.
        * Quien autoriza cobros = pertenece al grupo «Autoriza servicios XUBAX» de SU sistema.
        * Si el número pasa a otro usuario, se pide confirmar de nuevo y se avisa al equipo.
        Devuelve los contactos (confirmados o pendientes de confirmar).
        """
        from . import client_query, remote
        key = xb_phone_key(number)
        if not key:
            return self.browse()
        cache = _XB_RESOLVE_CACHE.get((self.env.cr.dbname, key))
        if cache and time.time() - cache[0] < 60:
            return self.sudo().browse(cache[1]).exists().filtered("active")
        Contacto = self.sudo().with_context(active_test=False)
        resultado = self.sudo().browse()
        proyectos = self.env["project.project"].sudo().search([
            ("xb_support_active", "=", True), ("database_name", "!=", False)])
        for p in proyectos:
            local = p.despacho_db_local and p.despacho_server == XB_LOCAL_SERVER
            if not local and not remote.configurado(self.env, p.despacho_server):
                continue
            try:
                usuarios = (client_query.usuarios_por_telefono(p.database_name, key) if local
                            else remote.llamar(self.env, p.despacho_server, "usuarios_por_telefono",
                                               db=p.database_name, key=key))
            except Exception:  # noqa: BLE001 - un sistema caído no tumba a los demás
                _logger.exception("xb_support_agent: no se pudo buscar el teléfono en %s", p.database_name)
                continue
            previo = Contacto.search([("phone_key", "=", key), ("project_id", "=", p.id)], limit=1)
            if len(usuarios) != 1:
                if previo.guest and not usuarios:
                    resultado |= previo if previo.active else previo.browse()
                    continue
                if previo.active:
                    previo.active = False
                if len(usuarios) > 1:
                    self._xb_alert(p, f"El teléfono {number} coincide con {len(usuarios)} usuarios de {p.name} "
                                      f"({', '.join(u['login'] for u in usuarios)}): no se ligó a ninguno.")
                continue
            u = usuarios[0]
            vals = {"name": u["name"], "phone": number, "auto": True, "active": True,
                    "guest": False, "guest_by": False,
                    "remote_user_id": u["id"], "remote_login": u["login"],
                    "role": "owner" if u["autoriza"] else "employee", "can_billing": u["autoriza"]}
            if previo:
                if previo.confirmed_user_id and previo.confirmed_user_id != u["id"]:
                    vals.update(confirmed_user_id=0, challenge_dt=False)
                    self._xb_alert(p, f"El teléfono {number} ahora corresponde a otro usuario de {p.name} "
                                      f"({u['login']}); se pidió confirmar su identidad otra vez.")
                previo.write(vals)
                contacto = previo
            else:
                contacto = Contacto.create(dict(vals, project_id=p.id))
            resultado |= contacto
        _XB_RESOLVE_CACHE[(self.env.cr.dbname, key)] = (time.time(), resultado.ids)
        return resultado

    @api.model
    def _xb_alert(self, proyecto, texto):
        """Aviso al equipo de soporte (actividad en el proyecto)."""
        _logger.warning("xb_support_agent: %s", texto)
        cuentas = self.env["whatsapp.account"].sudo().search([("xb_sa_enabled", "=", True)])
        for user in cuentas.xb_sa_support_user_ids:
            proyecto.sudo().activity_schedule("mail.mail_activity_data_todo", summary="🔐 " + texto[:120],
                                              note=texto, user_id=user.id)
