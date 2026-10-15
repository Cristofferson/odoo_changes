# -*- coding: utf-8 -*-
"""El agente: escucha la conversación de WhatsApp, piensa con Claude y contesta.

Seguridad, lo que NO depende del prompt:
* Quién es quién lo decide el código con el número de WhatsApp contra la lista
  de números autorizados. El modelo no puede "elegir" un sistema ajeno:
  seleccionar_sistema solo acepta sistemas donde ESE número está autorizado.
* revisar_sistema solo lee, en una transacción READ ONLY.
* Las acciones con efecto (arreglos, altas de número) solo crean propuestas que
  una persona aprueba.
"""
import base64
import io
import json
import re
import logging
from datetime import datetime, timedelta

import pytz
import requests
from PIL import Image, ImageOps
from markupsafe import Markup

from odoo import api, fields, models, sql_db, tools
from odoo.tools import html2plaintext

from .support_contact import xb_phone_key
import mimetypes

from . import bni_card, client_query, client_write, remote, screenshots, support_service

_logger = logging.getLogger(__name__)

XB_HISTORY_HOURS = 72
XB_HISTORY_LIMIT = 40
# Cada cuántas horas se repite el aviso cuando el cliente insiste en pausa.
XB_HOLD_HOURS = 2
# Lo que escribe la persona en el chat para devolverle la plática al agente.
XB_RESUME_WORDS = {"#agente", "#bot"}
XB_DRAFT_MARK = "Ensayo (no se envió)"
XB_DRAFT_HTML = f"<p><b>🤖 {XB_DRAFT_MARK}:</b></p>"
XB_MAX_TOOL_ROUNDS = 14
# Imágenes que el agente puede ver: las más recientes que mandó el cliente.
XB_VOZ_MARK = "[transcripción] "
XB_VOZ_MODEL = "gpt-4o-mini-transcribe"
XB_VOZ_MAX_BYTES = 8 * 1024 * 1024
XB_VISION_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
XB_VISION_MAX = 3
XB_WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 2}
XB_PDF_MAX = 4 * 1024 * 1024
XB_HORLI_TYPES = ("application/pdf", "application/vnd.ms-powerpoint", "image/jpeg", "image/png",
                  "application/vnd.openxmlformats-officedocument.presentationml.presentation")
XB_VISION_SIDE = 1568
XB_FALLBACK_BETA = "server-side-fallback-2026-07-01"
XB_TZ = "America/Mexico_City"
# Nombre con el que el servidor local aparece en el inventario de Despacho:
# solo esas bases se pueden revisar por dentro.
XB_LOCAL_SERVER = "odoo19"
XB_BACKUP_STATUS = "/var/lib/xb_support_agent/backups.json"
XB_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _tool(name, description, properties, required=None):
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required if required is not None else list(properties),
            "additionalProperties": False,
        },
    }


XB_TOOLS = [
    _tool("seleccionar_sistema",
          "Fija sobre qué sistema (base de datos) se está platicando, cuando el cliente tiene más de uno. "
          "Solo acepta sistemas donde su número está autorizado.",
          {"base_de_datos": {"type": "string", "description": "Nombre de la base tal como aparece en el contexto."}}),
    _tool("revisar_sistema",
          "Revisa en solo lectura el sistema del cliente: si su sitio responde, su último respaldo, y por dentro "
          "(si es posible) correos atorados, tareas automáticas con fallas, timbrado de facturas con error, cajas "
          "abiertas y usuarios. Úsala antes de responder cualquier duda técnica.", {}),
    _tool("buscar_modelos",
          "Busca en el sistema del cliente qué modelos (tablas de Odoo) existen, por palabra: p. ej. «venta», "
          "«pos.order», «inventario». Úsala cuando no sepas el nombre técnico del modelo.",
          {"texto": {"type": "string"}}),
    _tool("describir_modelo",
          "Lista los campos de un modelo (nombre técnico, etiqueta, tipo, relación). Filtra por palabra con texto "
          "(cadena vacía = todos).",
          {"modelo": {"type": "string"}, "texto": {"type": "string"}}),
    _tool("consultar_registros",
          "Lee registros del sistema del cliente, en solo lectura y con SUS permisos. Devuelve cuántos cumplen y "
          "hasta 50. Fechas y horas guardadas en UTC (Ciudad de México = UTC-6).",
          {"modelo": {"type": "string", "description": "Nombre técnico, p. ej. pos.order, sale.order, stock.quant."},
           "filtro": {"type": "string", "description": 'Dominio de Odoo en JSON, p. ej. [["state","=","paid"],'
                                                        '["date_order",">=","2026-10-10 06:00:00"]]. Cadena vacía = todos.'},
           "campos": {"type": "array", "items": {"type": "string"}},
           "orden": {"type": "string", "description": "p. ej. «date_order desc»; cadena vacía = el normal."},
           "limite": {"type": "integer"}}),
    _tool("resumir_registros",
          "Cuenta y suma registros agrupados (como un reporte): p. ej. ventas por día, por caja o por vendedor. "
          "Agrupar por fecha con «campo:day», «campo:month».",
          {"modelo": {"type": "string"},
           "filtro": {"type": "string", "description": "Dominio en JSON; cadena vacía = todos."},
           "agrupar_por": {"type": "array", "items": {"type": "string"}},
           "totales": {"type": "array", "items": {"type": "string"},
                       "description": "p. ej. [\"amount_total:sum\"]; lista vacía = solo contar."},
           "orden": {"type": "string"},
           "limite": {"type": "integer"}}),
    _tool("historial_de_cambios",
          "Quién creó un registro y qué se le cambió, cuándo y quién (el historial del chatter).",
          {"modelo": {"type": "string"}, "registro_id": {"type": "integer"}}),
    _tool("errores_del_servidor",
          "Errores técnicos recientes del servidor en el sistema del cliente (cuando dice que «algo marca error»).",
          {"horas": {"type": "integer", "description": "Cuántas horas hacia atrás (máx. 168)."}}),
    _tool("enviar_captura",
          "Le manda al cliente (titular, empleado o invitado) una captura REAL de una pantalla de su sistema, con un texto resaltado "
          "en rojo, para enseñarle dónde picar. Úsala cuando no encuentre algo o pida «capturas». Va antes de tu texto.",
          {"menu": {"type": "string", "description": "Ruta del menú como se ve en Odoo, p. ej. «Punto de venta» o "
                                                      "«Punto de venta / Pedidos / Sesiones»."},
           "registro_id": {"type": "integer", "description": "Id de un registro de esa pantalla para abrirlo; 0 = la lista."},
           "resaltar": {"type": "string", "description": "Texto visible del botón o campo a marcar en rojo; cadena vacía = nada."},
           "pie": {"type": "string", "description": "Una línea que acompaña la imagen."}}),
    _tool("cotizar_servicio",
          "SERVICIO COBRADO: cuando el titular pide que NOSOTROS hagamos algo en su sistema (crear una cotización, "
          "un contacto, una tarea, cambiar datos). Ensaya el cambio sin guardarlo y devuelve el precio. Después "
          "dile al cliente qué se va a hacer y el precio MÁS IVA, y pídele que responda SÍ. No hace el cambio.",
          {"descripcion": {"type": "string", "description": "Una línea: qué se va a hacer."},
           "operaciones": {"type": "string", "description":
               'Lista JSON de operaciones: [{"accion":"crear"|"modificar","modelo":"sale.order",'
               '"registro_id":0,"valores":{...}}]. «$1» en un valor = id de lo creado en la operación 1. '
               'Líneas de venta: "order_line":[[0,0,{"product_id":ID,"product_uom_qty":2}]]. '
               'Cadena vacía si es algo que solo puede hacer una persona.'},
           "minutos": {"type": "integer", "description": "Tiempo estimado (mínimo 15; múltiplos de 15)."}}),
    _tool("ejecutar_servicio",
          "Hace el servicio cotizado SOLO después de que el cliente respondió SÍ a la cotización. El sistema "
          "verifica ese SÍ por su cuenta.",
          {"servicio_id": {"type": "integer"}}),
    _tool("proponer_arreglo",
          "Deja una propuesta de arreglo para que el equipo la apruebe. No arregla nada por sí misma.",
          {"resumen": {"type": "string", "description": "Una línea: qué hay que hacer."},
           "problema": {"type": "string", "description": "Qué encontraste, con datos."},
           "propuesta": {"type": "string", "description": "Qué sugieres hacer, paso a paso."},
           "urgente": {"type": "boolean"}}),
    _tool("proponer_alta_numero",
          "Solo para el titular (quien autoriza servicios): da acceso de CONSULTA a otra persona que no tiene usuario en el "
          "sistema actual, o se lo quita (quitar=true). El invitado consulta (sin dinero) y recibe capturas; si pide un cambio "
          "con costo, lo autoriza el titular desde su número. "
          "Antes de usarla, confirma con el titular nombre y celular y que de verdad quiere compartir la consulta.",
          {"nombre": {"type": "string"},
           "celular": {"type": "string", "description": "10 dígitos."},
           "quitar": {"type": "boolean", "description": "true = quitarle el acceso."}}),
    _tool("pasar_a_humano",
          "Pasa la conversación a una persona del equipo con un resumen. Después de usarla sigues contestando al cliente lo demás (dudas generales, otros temas); solo no repitas el mismo aviso.",
          {"motivo": {"type": "string", "enum": ["no_sabe", "dinero", "pide_humano", "caida_grave", "otro"]},
           "resumen": {"type": "string", "description": "Qué pide el cliente y qué revisaste ya."},
           "urgente": {"type": "boolean"}}),
    _tool("registrar_prospecto",
          "Registra (o actualiza) a un prospecto nuevo en el CRM con lo que se sabe de su negocio. Usa cadena vacía en lo que no sepas.",
          {"nombre": {"type": "string"},
           "empresa": {"type": "string"},
           "giro": {"type": "string"},
           "ciudad": {"type": "string"},
           "correo": {"type": "string"},
           "necesidad": {"type": "string", "description": "Qué busca y qué le duele hoy."}}),
    _tool("marcar_miembro_bni",
          "La persona es miembro de BNI (dice serlo, viene de parte de Josette o quiere un 1 a 1). La marca con la etiqueta BNI, "
          "y avisa a Josette; lo que se sabe queda en su contacto y en la cita (no crea oportunidad: no es una venta). Usa cadena vacía en lo que no sepas.",
          {"nombre": {"type": "string"},
           "negocio": {"type": "string", "description": "Nombre de su empresa o negocio."},
           "giro": {"type": "string", "description": "A qué se dedica."},
           "busca": {"type": "string", "description": "Qué busca o para qué quiere el 1 a 1."},
           "referido_ideal": {"type": "string", "description": "Su referido ideal, si lo dijo."},
           "formato": {"type": "string", "description": "videollamada, presencial o por definir."},
           "ficha_publica": {"type": "string", "description":
               "Solo si buscaste su NEGOCIO en internet: 2 o 3 líneas de lo público y profesional (qué hace, qué ofrece) y la "
               "liga de donde salió. NADA personal. Cadena vacía si no buscaste o no estás seguro de que sea su negocio."}}),
    _tool("avisar_salida_bni",
          "BNI: la persona dice que ya no es miembro del capítulo (o que dejó BNI). Solo avisa a Josette para que lo confirme; no cambia nada por sí sola.",
          {"comentario": {"type": "string", "description": "Lo que dijo la persona, en una frase."}}),
    _tool("enviar_horli_xubax",
          "BNI: manda al miembro la HORLI de XUBAX (el documento de Josette) para que llegue sabiendo con quién va a hablar.",
          {}),
    _tool("guardar_horli_miembro",
          "BNI: guarda la HORLI que el miembro acaba de mandar (PDF, PowerPoint o imagen) en su contacto y en la cita de Josette.",
          {"resumen": {"type": "string", "description": "Qué dice su HORLI: quién es, qué ofrece y qué busca, en 3 líneas."}}),
    _tool("registrar_referido_ideal",
          "BNI: guarda el referido ideal del miembro y deja a Josette una actividad para buscárselo.",
          {"referido": {"type": "string", "description": "El perfil de persona o negocio que le serviría conocer."}}),
    _tool("enviar_tarjeta_bni",
          "BNI: manda al miembro una tarjeta personalizada «3 cosas que XUBAX automatizaría en tu negocio». "
          "Usa SOLO cosas que XUBAX hace según la base de conocimiento; cada una en menos de 100 caracteres.",
          {"persona": {"type": "string"}, "negocio": {"type": "string"},
           "cosa1": {"type": "string"}, "cosa2": {"type": "string"}, "cosa3": {"type": "string"}}),
    _tool("registrar_interes_compra",
          "Un cliente actual quiere contratar algo más: registra la oportunidad en el CRM para que un asesor cotice.",
          {"resumen": {"type": "string", "description": "Una línea."},
           "detalle": {"type": "string"}}),
    _tool("ver_horarios_demo",
          "Devuelve horarios libres para la cita/demo (hora de Ciudad de México), sacados de la app de Citas, "
          "y la liga donde el cliente puede escoger otro horario él mismo.",
          {"desde": {"type": "string", "description": "AAAA-MM-DD si el cliente quiere a partir de cierta fecha; cadena vacía = lo más pronto."}}),
    _tool("agendar_demo",
          "Aparta la cita/demo en uno de los horarios devueltos por ver_horarios_demo.",
          {"inicio": {"type": "string", "description": "Fecha y hora exactamente como la dio ver_horarios_demo (AAAA-MM-DD HH:MM)."},
           "nombre": {"type": "string"},
           "correo": {"type": "string", "description": "Cadena vacía si no lo dio."}}),
]


# Solo para el EQUIPO de XUBAX reconocido por su teléfono (ver _xb_sa_team_user).
XB_TEAM_TOOLS = [
    _tool("ver_citas_bni",
          "EQUIPO: lista los 1 a 1 de BNI próximos (id, miembro, fecha y hora).",
          {}),
    _tool("mover_cita_bni",
          "EQUIPO: cambia la fecha y hora de un 1 a 1 de BNI. Avisa al miembro por WhatsApp si escribió hace menos de 24 h.",
          {"cita_id": {"type": "integer", "description": "Id de la cita, de ver_citas_bni."},
           "inicio": {"type": "string", "description": "Nueva fecha y hora de Ciudad de México, AAAA-MM-DD HH:MM (puede ser cualquier minuto, p. ej. 09:10)."}}),
    _tool("cancelar_cita_bni",
          "EQUIPO: cancela un 1 a 1 de BNI. Úsala SOLO después de que la persona del equipo confirme que la quiere cancelar.",
          {"cita_id": {"type": "integer", "description": "Id de la cita, de ver_citas_bni."}}),
]
for _t in XB_TEAM_TOOLS:
    _t.pop("strict", None)


# La API acepta como máximo 20 herramientas «strict»: las de BNI van sin ese modo
# (los manejadores leen la entrada con .get, así que toleran campos faltantes).
XB_NON_STRICT = {"marcar_miembro_bni", "avisar_salida_bni", "enviar_horli_xubax", "guardar_horli_miembro",
                 "registrar_referido_ideal", "enviar_tarjeta_bni"}
for _herramienta in XB_TOOLS:
    if _herramienta["name"] in XB_NON_STRICT:
        _herramienta.pop("strict", None)
assert sum(1 for _h in XB_TOOLS if _h.get("strict")) <= 20, "Demasiadas herramientas strict (máx. 20)"


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    xb_sa_project_id = fields.Many2one("project.project", string="Sistema en la plática", copy=False)
    xb_sa_paused_until = fields.Datetime("Agente en pausa hasta", copy=False)
    xb_sa_pause_reason = fields.Selection([
        ("human", "Contestó una persona"),
        ("handoff", "El agente la pasó a una persona"),
    ], string="Motivo de la pausa", copy=False)
    xb_sa_hold_dt = fields.Datetime("Último aviso en pausa", copy=False)
    xb_sa_is_paused = fields.Boolean("Atendida por una persona", compute="_compute_xb_sa_is_paused",
                                     search="_search_xb_sa_is_paused")

    def _compute_xb_sa_is_paused(self):
        ahora = fields.Datetime.now()
        for channel in self:
            channel.xb_sa_is_paused = bool(channel.xb_sa_paused_until and channel.xb_sa_paused_until > ahora)

    def _search_xb_sa_is_paused(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        pausadas = [("xb_sa_paused_until", ">", fields.Datetime.now())]
        return pausadas if (operator == "=") == value else ["!", *pausadas]

    xb_wa_last_text = fields.Char("Último mensaje", compute="_compute_xb_wa_last")
    # Guardada para poder ordenar la lista; se actualiza en _notify_thread.
    xb_wa_last_dt = fields.Datetime("Fecha", compute="_compute_xb_wa_last_dt", store=True)
    xb_wa_last_inbound = fields.Boolean("Lo escribió el cliente", compute="_compute_xb_wa_last")

    xb_wa_attended_by = fields.Selection([("person", "Persona"), ("agent", "Agente IA")],
                                         string="La atiende", compute="_compute_xb_wa_attended_by")
    xb_wa_origin = fields.Selection([("ad", "Anuncio de Meta"), ("web", "Sitio web"), ("direct", "Directo")],
                                    string="Origen", compute="_compute_xb_wa_origin", store=True)
    xb_wa_origin_detail = fields.Char("De dónde", compute="_compute_xb_wa_origin_detail")

    @api.depends("xb_sa_paused_until", "wa_account_id.xb_sa_enabled")
    def _compute_xb_wa_attended_by(self):
        ahora = fields.Datetime.now()
        for channel in self:
            # sudo: quien ve la plática puede no tener la empresa de la cuenta activa.
            if channel.xb_sa_paused_until and channel.xb_sa_paused_until > ahora:
                channel.xb_wa_attended_by = "person"
            elif channel.sudo().wa_account_id.xb_sa_enabled:
                channel.xb_wa_attended_by = "agent"
            else:
                channel.xb_wa_attended_by = False

    @api.depends("xb_wa_source_lead_id.source_id")
    def _compute_xb_wa_origin(self):
        """De dónde vino el clic: anuncio Click-to-WhatsApp, botón del sitio o escribió directo."""
        for channel in self:
            fuente = channel.sudo().xb_wa_source_lead_id.source_id.name
            if not fuente:
                channel.xb_wa_origin = "direct"
            elif fuente == "Anuncio Meta":
                channel.xb_wa_origin = "ad"
            else:
                channel.xb_wa_origin = "web"

    def _compute_xb_wa_origin_detail(self):
        for channel in self:
            lead = channel.xb_wa_source_lead_id.sudo()
            if not lead:
                channel.xb_wa_origin_detail = False
                continue
            # El prospecto se llama «Sitio web — <producto> — <cliente>».
            partes = (lead.name or "").split(" — ")
            que = partes[1] if len(partes) == 3 and partes[1] != "Consulta" else ""
            channel.xb_wa_origin_detail = " · ".join(filter(None, [lead.source_id.name, que]))

    def _compute_xb_wa_last(self):
        """Último mensaje de WhatsApp de cada plática (para la lista de Conversaciones)."""
        ultimos = {}
        if self.ids:
            self.env.cr.execute("""
                SELECT DISTINCT ON (m.res_id) m.res_id, m.body, m.create_date, w.message_type
                  FROM mail_message m
             LEFT JOIN whatsapp_message w ON w.mail_message_id = m.id
                 WHERE m.model = 'discuss.channel' AND m.res_id IN %s
                   AND m.message_type = 'whatsapp_message'
              ORDER BY m.res_id, m.id DESC
            """, (tuple(self.ids),))
            ultimos = {r[0]: r[1:] for r in self.env.cr.fetchall()}
        for channel in self:
            body, _fecha, tipo = ultimos.get(channel.id, (False, False, False))
            texto = html2plaintext(body or "").strip().replace("\n", " ")
            if not texto and channel.id in ultimos:
                texto = "📎 Archivo o imagen"
            channel.xb_wa_last_text = (texto[:120] + "…") if len(texto) > 120 else texto
            channel.xb_wa_last_inbound = tipo == "inbound"

    def _compute_xb_wa_last_dt(self):
        fechas = {}
        if self.ids:
            self.env.cr.execute("""
                SELECT res_id, max(create_date) FROM mail_message
                 WHERE model = 'discuss.channel' AND res_id IN %s AND message_type = 'whatsapp_message'
              GROUP BY res_id
            """, (tuple(self.ids),))
            fechas = dict(self.env.cr.fetchall())
        for channel in self:
            channel.xb_wa_last_dt = fechas.get(channel.id, False)

    def action_xb_open_chat(self):
        """Clic en la lista de Conversaciones: abre la plática completa en Conversaciones (Discuss)."""
        self.ensure_one()
        return self._get_access_action()

    def action_xb_sa_resume(self):
        """La persona terminó: el agente vuelve a atender estas pláticas."""
        for channel in self.sudo():
            if channel.xb_sa_paused_until:
                channel._xb_sa_resume_note()
        return True

    def _xb_sa_resume_note(self):
        """Quita la pausa y deja la nota en la plática. Devuelve la nota."""
        self.ensure_one()
        channel = self.sudo()
        if channel.xb_sa_paused_until:
            channel.write({"xb_sa_paused_until": False, "xb_sa_pause_reason": False, "xb_sa_hold_dt": False})
            texto = f"{self.env.user.name} devolvió la plática al agente."
        else:
            texto = "La plática ya estaba con el agente."
        return channel.message_post(
            body=Markup("<p>↩️ %s</p>") % texto,
            message_type="comment", subtype_xmlid="mail.mt_note",
            author_id=self.env.user.partner_id.id)

    def message_post(self, *args, body="", message_type="notification", **kwargs):
        # «#agente» escrito por alguien del equipo: no se le manda al cliente,
        # solo le devuelve la plática al agente.
        if (self.channel_type == "whatsapp" and message_type == "whatsapp_message"
                and not kwargs.get("whatsapp_inbound_msg_uid")
                and self.env.user._is_internal()
                and html2plaintext(body or "").strip().lower() in XB_RESUME_WORDS):
            # Se devuelve la nota (un mensaje NUEVO): si se devolviera uno que ya
            # está en pantalla, Discuss lo pinta dos veces y truena.
            return self._xb_sa_resume_note()
        return super().message_post(*args, body=body, message_type=message_type, **kwargs)
    xb_sa_lead_id = fields.Many2one("crm.lead", string="Prospecto u oportunidad", copy=False)
    xb_sa_bni = fields.Boolean("Miembro de BNI", copy=False)
    xb_sa_bni_welcomed = fields.Boolean("Ya recibió el video de Josette", copy=False)
    xb_sa_bni_notes = fields.Text("Lo que se sabe del miembro de BNI", copy=False)

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------
    def _notify_thread(self, message, msg_vals=False, **kwargs):
        res = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        if message.message_type == "whatsapp_message":
            self.filtered(lambda c: c.channel_type == "whatsapp").sudo().xb_wa_last_dt = message.create_date
        for channel in self:
            if channel.channel_type != "whatsapp" or not channel.wa_account_id.xb_sa_enabled:
                continue
            if not channel.wa_account_id.sudo()._xb_sa_allows(channel.whatsapp_number):
                continue
            try:
                if kwargs.get("whatsapp_inbound_msg_uid"):
                    if hasattr(channel, "_xb_is_campaign_reply") and channel._xb_is_campaign_reply(message):
                        continue
                    self.env["xb.support.job"]._xb_enqueue(channel, message)
                elif channel._xb_sa_is_human_reply(message):
                    channel.sudo().write({
                        "xb_sa_paused_until": fields.Datetime.now() + timedelta(
                            hours=max(channel.wa_account_id.xb_sa_pause_hours, 0)),
                        "xb_sa_pause_reason": "human",
                    })
            except Exception:  # noqa: BLE001 - nunca romper la recepción
                _logger.exception("xb_support_agent: no se pudo encolar el mensaje %s", message.id)
        return res

    def _xb_sa_is_human_reply(self, message):
        """Una persona del equipo contestó por WhatsApp desde Odoo."""
        if message.message_type != "whatsapp_message":
            return False
        if message.author_id == self.env.ref("base.partner_root"):
            return False
        return bool(message.author_id.user_ids.filtered(lambda u: not u.share))

    # ------------------------------------------------------------------
    # Quién escribe
    # ------------------------------------------------------------------
    def _xb_sa_contacts(self):
        self.ensure_one()
        return self._xb_sa_by_profile(self.env["xb.support.contact"]._xb_find(self.whatsapp_number).filtered(
            lambda c: c.project_id.active))

    def _xb_sa_by_profile(self, contactos):
        """El agente de tienda solo ve el sistema de la tienda; el de soporte de XUBAX, todos menos ese."""
        tienda = self.wa_account_id.sudo().xb_sa_profile == "tienda"
        return contactos.filtered(lambda c: bool(c.project_id.xb_sa_store) == tienda)

    def _xb_sa_current(self):
        """(contacto, sistema) vigentes. Si solo hay un sistema, es ese."""
        self.ensure_one()
        contactos = self._xb_sa_contacts()
        proyecto = self.xb_sa_project_id
        if proyecto and proyecto not in contactos.project_id:
            proyecto = self.env["project.project"]
        if not proyecto and len(contactos.project_id) == 1:
            proyecto = contactos.project_id
        contacto = contactos.filtered(lambda c: c.project_id == proyecto)[:1]
        return contactos, contacto, proyecto

    def _xb_sa_context_text(self, contactos, contacto, proyecto):
        ahora = datetime.now(pytz.timezone(XB_TZ))
        lineas = [f"Contexto (lo escribe el sistema, no el cliente). Fecha y hora en Ciudad de México: {XB_DIAS[ahora.weekday()]} {ahora:%d/%m/%Y %H:%M}."]
        if not contactos:
            lineas.append("Este número NO corresponde al teléfono de ningún usuario de un sistema con soporte: trátalo como PROSPECTO nuevo. No tiene acceso a información de ningún sistema.")
        else:
            lineas.append(f"Este número está autorizado en {len(contactos)} sistema(s):")
            for c in contactos:
                rol = dict(c._fields["role"].selection)[c.role]
                dinero = "sí" if c.can_billing else "no"
                lineas.append(f"- {c.name} ({'INVITADO sin usuario propio: consulta sin dinero, capturas y puede pedir cambios que autoriza el titular' if c.guest else 'usuario ' + (c.remote_login or '')}) · {rol} · sistema «{c.project_id.name}» (base {c.database_name}) · ve temas de dinero y autoriza servicios: {dinero}")
            if proyecto:
                lineas.append(f"Sistema de esta plática: «{proyecto.name}» (base {proyecto.database_name}).")
            else:
                lineas.append("Todavía no se sabe de cuál sistema habla: pregúntale y usa seleccionar_sistema.")
        pendiente = self.env["xb.support.service"].sudo().search(
            [("channel_id", "=", self.id), ("state", "=", "quoted")], order="id desc", limit=1)
        de_invitado = self.env["xb.support.service"].sudo().search(
            [("approver_id", "in", contactos.ids), ("state", "=", "quoted"),
             ("quote_dt", ">", fields.Datetime.now() - timedelta(hours=24))], order="id desc", limit=1)
        if de_invitado:
            lineas.append(
                f"SERVICIO PEDIDO POR UN INVITADO ESPERANDO EL SÍ DE ESTA PERSONA: id {de_invitado.id} «{de_invitado.name}», "
                f"lo pidió {de_invitado.contact_id.name}, ${de_invitado.amount:,.2f} más IVA. Si el último mensaje de esta persona "
                f"es SÍ (o equivalente), llama ejecutar_servicio con servicio_id={de_invitado.id}. Si dice que no, no hagas nada.")
        if pendiente and pendiente.approver_id:
            lineas.append(
                f"SERVICIO PEDIDO POR ESTA PERSONA (invitada) ESPERANDO EL SÍ DE {pendiente.approver_id.name}: id {pendiente.id} "
                f"«{pendiente.name}». Tú NO puedes autorizarlo: NO llames ejecutar_servicio en esta plática; si pregunta, dile que "
                "está esperando esa autorización.")
        elif pendiente:
            lineas.append(
                f"SERVICIO COTIZADO ESPERANDO EL SÍ: id {pendiente.id} «{pendiente.name}», ${pendiente.amount:,.2f} más IVA. "
                f"Si el último mensaje del cliente es SÍ (o equivalente), llama ejecutar_servicio con servicio_id={pendiente.id} "
                "y NO vuelvas a cotizar. Solo cotiza de nuevo si el cliente cambió lo que pidió.")
        if (self.xb_sa_pause_reason == "handoff" and not self.xb_sa_paused_until and self.xb_sa_hold_dt
                and self.xb_sa_hold_dt > fields.Datetime.now() - timedelta(hours=48)):
            lineas.append(
                "YA SE AVISÓ a una persona del equipo sobre esta plática y ella contestará lo pendiente. NO te quedes callado: "
                "sigue contestando con normalidad todo lo demás que pregunte (qué es XUBAX, dudas generales, etc.). No vuelvas a "
                "usar pasar_a_humano por el mismo tema ni repitas «ya le avisé»; solo si pide algo NUEVO que tampoco puedas resolver. "
                "No prometas fechas ni hagas lo que quedó en manos de la persona.")
        equipo = self._xb_sa_team_user()
        if equipo:
            lineas.append(
                f"Esta persona es del EQUIPO de XUBAX: {equipo.name} (usuario interno, reconocida por su teléfono). No es prospecto ni "
                "miembro: no le vendas ni le des el trato de BNI. Si pide ver, mover o cancelar un 1 a 1 de BNI, usa ver_citas_bni y "
                "luego mover_cita_bni o cancelar_cita_bni (la hora puede ser cualquier minuto, p. ej. 9:10). Mover: hazlo directo y dile qué "
                "quedó y si el miembro fue avisado. Cancelar: confirma primero con ella. Si la persona del equipo pide mover algo que NO es "
                "un 1 a 1 de BNI, dile que eso lo haga ella desde Odoo. Si pregunta otra cosa, contesta con naturalidad y trátala de tú.")
        if self._xb_sa_is_bni():
            lineas.append("Esta persona es MIEMBRO DE BNI: trátala como colega (cálida, breve, sin vender). Su 1 a 1 es con "
                          "Josette Salinas Gil, 1 hora: ofrece horarios con ver_horarios_demo y pregunta si prefiere "
                          "videollamada o presencial. Conoce su negocio y su referido ideal. No tiene acceso a ningún sistema. "
                          "En esta plática de BNI NO uses ni menciones datos del sistema de un cliente ni pendientes de soporte o servicios, "
                          "aunque la persona también sea cliente; solo información pública o lo que ella diga, salvo que ella pida soporte. "
                          "En BNI Josette está registrada como IMPLEMENTADORA DE ERP (Odoo): si preguntan a qué se dedican, dilo así; "
                          "NO ofrezcas, enumeres ni cotices otros servicios de XUBAX (sitios web, tiendas en línea, hosting, dominios, marketing, apps) ni des sus precios; "
                          "si piden algo fuera del ERP Odoo, explica con amabilidad que en BNI su especialidad es el ERP, que el ERP sí hace varias cosas y que en el 1 a 1 Josette les explicará con detenimiento qué sí y qué no; invítalos a agendar o confirmar su 1 a 1 (sin pasar a humano) y anota lo que pidieron en el campo busca de marcar_miembro_bni."
                          + (" Lo que sabes de su negocio por internet está en las notas. Tu PRIMER saludo SIEMPRE incluye su nombre, el de su negocio (si es distinto) y su giro, más UN dato curioso o simpático si lo sabes; lo que no sepas, pregúntalo, no lo inventes; "
                             "lo demás NO lo menciones ni lo uses para halagar, solo si la persona pregunta qué sabes de ella o de su negocio, y entonces di de dónde salió. "
                             "Notas: " + (self.xb_sa_bni_notes or "")[:900] if self.xb_sa_bni_notes else "")
                          + (f" En nuestra base figura como «{self.whatsapp_partner_id.sudo().name}»: salúdale por su nombre."
                             if self.whatsapp_partner_id else "")
                          + self._xb_sa_bni_lista())
        elif self._xb_sa_is_ex_bni():
            lineas.append("Esta persona es EXMIEMBRO de BNI: trátala con cordialidad como a cualquier persona que escribe, "
                          "sin video de bienvenida, sin HORLI, sin referido ideal y SIN 1 a 1 con Josette (si lo pide, explícale con "
                          "amabilidad que son para miembros del capítulo y ofrécele, si le interesa, hablar de XUBAX como prospecto o cliente normal). "
                          "Si es cliente y pide soporte, atiéndelo como a cualquier cliente.")
        if self.xb_sa_lead_id:
            lineas.append(f"Ya hay un registro en el CRM para esta plática: «{self.xb_sa_lead_id.name}».")
        # La agenda manda: si el equipo movió o canceló una cita, el historial ya no es cierto.
        if self.whatsapp_partner_id:
            tz = pytz.timezone(XB_TZ)
            citas = self.env["calendar.event"].sudo().search([
                ("appointment_type_id", "!=", False), ("start", ">", fields.Datetime.now()),
                ("partner_ids", "in", self.whatsapp_partner_id.ids)], order="start", limit=3)
            if citas:
                lineas.append("Citas agendadas vigentes: " + "; ".join(
                    f"{XB_DIAS[pytz.utc.localize(c.start).astimezone(tz).weekday()]} "
                    f"{pytz.utc.localize(c.start).astimezone(tz):%d/%m/%Y %H:%M} con {c.user_id.name}" for c in citas) + ".")
            else:
                lineas.append("No tiene citas agendadas vigentes (si en la plática se habló de una, ya no está en la agenda: no la menciones como apartada).")
        return "\n".join(lineas)

    # ------------------------------------------------------------------
    # Historial → mensajes para Claude
    # ------------------------------------------------------------------
    def _xb_sa_history(self):
        self.ensure_one()
        desde = fields.Datetime.now() - timedelta(hours=XB_HISTORY_HOURS)
        mensajes = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("date", ">=", desde),
            "|", ("message_type", "=", "whatsapp_message"),
            "&", ("message_type", "=", "comment"), ("body", "ilike", XB_DRAFT_MARK),
        ], order="id desc", limit=XB_HISTORY_LIMIT).sorted("id")
        bot = self.env.ref("base.partner_root")
        # Solo las imágenes más recientes del cliente van como imagen (cuestan
        # tokens); las anteriores quedan como «[Adjuntó: imagen]».
        imagenes = mensajes.filtered(lambda m: m.wa_message_ids.filtered(lambda w: w.message_type == "inbound")) \
            .attachment_ids.filtered(lambda a: (a.mimetype or "") in XB_VISION_TYPES)
        vistas = set(imagenes.sorted("id", reverse=True)[:XB_VISION_MAX].ids)
        # Miembros de BNI: la HORLI en PDF más reciente se le da a Claude para que la lea.
        pdf_vistos = set()
        if self._xb_sa_is_bni():
            pdfs = mensajes.filtered(lambda m: m.wa_message_ids.filtered(lambda w: w.message_type == "inbound")) \
                .attachment_ids.filtered(lambda a: a.mimetype == "application/pdf" and a.file_size <= XB_PDF_MAX)
            pdf_vistos = set(pdfs.sorted("id", reverse=True)[:1].ids)
        turnos = []
        # Avisos automáticos del módulo de respuestas (bienvenida / fuera de horario): no son parte de la plática.
        acc = self.wa_account_id.sudo()
        automaticos = {html2plaintext(str(getattr(acc, campo, "") or "")).strip()
                       for campo in ("xb_offhours_body", "xb_welcome_body")} - {""}
        for msg in mensajes:
            ensayo = msg.message_type == "comment"
            if ensayo and msg.author_id != bot:
                continue
            if (automaticos and not ensayo and not msg.wa_message_ids.filtered(lambda w: w.message_type == "inbound")
                    and any(html2plaintext(str(msg.body or "")).strip().startswith(a[:60]) for a in automaticos)):
                continue
            # En modo ensayo las respuestas son notas: sin ellas el agente no
            # recordaría lo que ya dijo y repetiría el saludo cada vez.
            cuerpo = str(msg.body or "").replace(XB_DRAFT_HTML, "")
            texto = html2plaintext(cuerpo).strip()
            bloques = []
            otros = msg.attachment_ids.filtered(lambda a: a.id not in vistas)
            for adjunto in msg.attachment_ids.filtered(lambda a: a.id in vistas):
                bloque = self._xb_sa_image_block(adjunto)
                if bloque:
                    bloques.append(bloque)
                else:
                    otros |= adjunto
            for adjunto in otros.filtered(lambda a: a.id in pdf_vistos):
                bloques.append({"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf",
                    "data": base64.b64encode(adjunto.sudo().raw).decode()}})
                otros -= adjunto
            for adjunto in otros.filtered(lambda a: (a.mimetype or "").startswith("audio/")
                                          and msg.wa_message_ids.filtered(lambda w: w.message_type == "inbound")):
                voz = self._xb_sa_transcribe(adjunto)
                if voz:
                    texto = f"{texto}\n[Nota de voz transcrita]: {voz}".strip()
                    otros -= adjunto
            if otros:
                tipos = ", ".join(sorted({self._xb_sa_attach_label(a) for a in otros}))
                texto = f"{texto}\n[Adjuntó: {tipos}]".strip()
            if not texto and not bloques:
                continue
            entrante = not ensayo and bool(msg.wa_message_ids.filtered(lambda w: w.message_type == "inbound"))
            if entrante:
                rol = "user"
            else:
                rol = "assistant"
                if msg.author_id != bot:
                    # Al cliente de la tienda nunca se le nombra a una persona del equipo.
                    anonimo = acc.xb_sa_profile == "tienda" and not self._xb_sa_store_team()
                    quien = "una persona de la tienda (sin nombre; NO la nombres ni digas que otra persona contestó)" if anonimo \
                        else f"{msg.author_id.name}, del equipo"
                    texto = f"[Contestó {quien}]: {texto}"
            if texto:
                bloques.append({"type": "text", "text": texto})
            if turnos and turnos[-1]["role"] == rol:
                turnos[-1]["content"] += bloques
            else:
                turnos.append({"role": rol, "content": bloques})
        while turnos and turnos[0]["role"] != "user":
            turnos.pop(0)
        return turnos

    def _xb_sa_transcribe(self, adjunto):
        """Texto de una nota de voz (OpenAI). Se guarda en el adjunto para pagar una sola vez."""
        adjunto = adjunto.sudo()
        if (adjunto.description or "").startswith(XB_VOZ_MARK):
            return adjunto.description[len(XB_VOZ_MARK):]
        llave = self.wa_account_id.sudo().xb_sa_openai_key
        if not llave or not adjunto.raw or adjunto.file_size > XB_VOZ_MAX_BYTES:
            return ""
        try:
            resp = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {llave}"},
                data={"model": XB_VOZ_MODEL, "language": "es", "response_format": "text"},
                files={"file": (adjunto.name or "voz.ogg", adjunto.raw, adjunto.mimetype or "audio/ogg")},
                timeout=60)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001 - sin transcripción se le pide que escriba
            _logger.warning("xb_support_agent: falló la transcripción del adjunto %s: %s", adjunto.id, e)
            return ""
        texto = (resp.text or "").strip()
        if texto:
            adjunto.description = XB_VOZ_MARK + texto
        return texto

    @api.model
    def _xb_sa_image_block(self, adjunto):
        """Imagen para Claude: lado mayor ≤ 1568 px y JPEG, para no pagar de más."""
        try:
            img = Image.open(io.BytesIO(adjunto.sudo().raw))
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((XB_VISION_SIDE, XB_VISION_SIDE))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
        except Exception:  # noqa: BLE001 - imagen dañada o formato raro: se describe como adjunto
            _logger.warning("xb_support_agent: no se pudo leer la imagen %s", adjunto.id)
            return None
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.b64encode(buf.getvalue()).decode()}}

    # ------------------------------------------------------------------
    # El ciclo con Claude
    # ------------------------------------------------------------------
    def _xb_sa_answer(self, job):
        self.ensure_one()
        acc = self.wa_account_id.sudo()
        ahora = fields.Datetime.now()
        if not acc.xb_sa_enabled:
            job.write({"state": "skipped", "reason": "El agente está apagado en este número"})
            return
        if self.xb_sa_paused_until and self.xb_sa_paused_until > ahora:
            self._xb_sa_on_hold(job)
            return
        historial = self._xb_sa_history()
        if not historial or historial[-1]["role"] != "user":
            job.write({"state": "skipped", "reason": "No hay nada nuevo que contestar"})
            return
        if not acc.xb_sa_api_key:
            raise ValueError("Falta la llave de API de Anthropic en la cuenta de WhatsApp")

        import anthropic  # perezoso: el módulo carga aunque falte la librería

        if self._xb_sa_identity_gate(job, acc):
            return
        if acc.xb_sa_profile == "tienda" and not self.xb_sa_project_id:
            tienda_p = self._xb_sa_contacts().project_id.filtered("xb_sa_store")[:1]
            if tienda_p:
                self.sudo().xb_sa_project_id = tienda_p
        contactos, contacto, proyecto = self._xb_sa_current()
        job.write({
            "contact_id": contacto.id,
            "project_id": proyecto.id,
            "mode": "support" if contactos else "prospect",
            "model_name": acc.xb_sa_model,
        })
        client = anthropic.Anthropic(api_key=acc.xb_sa_api_key, timeout=120, max_retries=2)
        system = [{"type": "text", "text": acc._xb_sa_system_prompt(),
                   "cache_control": {"type": "ephemeral"}}]
        tienda = acc.xb_sa_profile == "tienda"
        mensajes = historial + [{"role": "system",
                                 "content": (self._xb_sa_store_context(contactos, contacto, proyecto) if tienda
                                             else self._xb_sa_context_text(contactos, contacto, proyecto))}]
        texto = ""
        if tienda:
            herramientas = self._xb_sa_store_tools(contactos)
        else:
            herramientas = (XB_TOOLS + ([XB_WEB_SEARCH] if self._xb_sa_first_bni_contact() else [])
                            + (XB_TEAM_TOOLS if self._xb_sa_team_user() else []))
        for _ronda in range(XB_MAX_TOOL_ROUNDS):
            kwargs = dict(
                model=acc.xb_sa_model,
                max_tokens=16000,
                system=system,
                messages=mensajes,
                tools=herramientas,
                output_config={"effort": acc.xb_sa_effort},
            )
            if acc.xb_sa_model == "claude-haiku-5-5":
                resp = client.messages.create(**kwargs)
            else:
                # Si un filtro de seguridad rechaza la petición, Anthropic la
                # re-intenta en el modelo de respaldo que recomienda.
                resp = client.beta.messages.create(betas=[XB_FALLBACK_BETA], fallbacks="default", **kwargs)
            job._xb_add_usage(acc.xb_sa_model, resp.usage)

            if resp.stop_reason == "refusal":
                job._xb_log("El modelo se negó a contestar.")
                self._xb_sa_tool_pasar_a_humano(job, {
                    "motivo": "otro", "urgente": False,
                    "resumen": "El modelo de IA se negó a contestar este mensaje; revísalo tú."})
                texto = "Gracias por escribir. Le paso su mensaje a una persona del equipo para que le ayude."
                break

            if resp.stop_reason == "pause_turn":  # la búsqueda en internet pidió más tiempo
                mensajes.append({"role": "assistant", "content": resp.content})
                continue
            usos = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason == "tool_use" and usos:
                mensajes.append({"role": "assistant", "content": resp.content})
                resultados = []
                for uso in usos:
                    resultado, es_error = self._xb_sa_run_tool(job, uso.name, uso.input)
                    resultados.append({"type": "tool_result", "tool_use_id": uso.id,
                                       "content": resultado, "is_error": es_error})
                mensajes.append({"role": "user", "content": resultados})
                continue

            # Con búsqueda en internet puede haber texto antes de buscar: solo vale lo que viene después.
            bloques = list(resp.content)
            ultimo = max((i for i, b in enumerate(bloques)
                          if b.type in ("server_tool_use", "web_search_tool_result")), default=-1)
            texto = "\n\n".join(b.text for b in bloques[ultimo + 1:] if b.type == "text").strip()
            break
        else:
            job._xb_log("Se alcanzó el máximo de rondas de herramientas.")

        if not texto:
            job.write({"state": "skipped", "reason": "El agente no produjo respuesta"})
            return
        job.reply = texto
        if acc.xb_sa_shadow:
            self._xb_sa_post_draft(texto)
            job.state = "draft"
        else:
            self._xb_sa_send(texto)
            job.state = "done"

    def _xb_sa_identity_gate(self, job, acc):
        """Primera vez que un número se liga a un usuario: se confirma por WhatsApp
        (en código, sin modelo). Devuelve True si ya se contestó aquí."""
        self.ensure_one()
        pendientes = self._xb_sa_by_profile(self.env["xb.support.contact"]._xb_resolve(self.whatsapp_number)).filtered(
            lambda c: not c.confirmed)
        if not pendientes:
            return False
        Servicio = self.env["xb.support.service"]
        for c in pendientes:
            if c.challenge_dt and Servicio._xb_inbound_yes(self, c.challenge_dt):
                c.sudo().confirmed_user_id = c.remote_user_id
        pendientes = pendientes.filtered(lambda c: not c.confirmed)
        if not pendientes:
            return False
        c = pendientes[0]
        ahora = fields.Datetime.now()
        if c.challenge_dt and ahora - c.challenge_dt < timedelta(hours=24):
            texto = (f"Antes de ayudarte necesito confirmar que eres {c.name} de {c.project_id.name}. "
                     "Responde SÍ para continuar.")
        else:
            c.sudo().challenge_dt = ahora
            texto = (f"Hola, soy el asistente de {acc.xb_sa_company_name or 'XUBAX'}. Tu número está ligado al usuario de {c.name} en "
                     f"{c.project_id.name}. ¿Eres tú? Responde SÍ para confirmarlo y poder ayudarte con tu sistema.")
        job.reply = texto
        if acc.xb_sa_shadow:
            self._xb_sa_post_draft(texto)
            job.write({"state": "draft", "reason": "Confirmación de identidad"})
        else:
            self._xb_sa_send(texto)
            job.write({"state": "done", "reason": "Confirmación de identidad"})
        return True

    def _xb_sa_on_hold(self, job):
        """El cliente vuelve a escribir mientras espera a una persona.

        Cada XB_HOLD_HOURS: se le vuelve a avisar al equipo y, si fue el agente
        quien pasó la plática (y no una persona que ya está contestando), se le
        dice al cliente que ya se avisó. Así nadie se queda sin respuesta.
        """
        acc = self.wa_account_id.sudo()
        ahora = fields.Datetime.now()
        if self.xb_sa_hold_dt and self.xb_sa_hold_dt > ahora - timedelta(hours=XB_HOLD_HOURS):
            job.write({"state": "skipped", "reason": "En pausa; ya se avisó al equipo hace poco"})
            return
        texto = html2plaintext(job.message_id.body or "").strip() or "(mensaje sin texto)"
        lead = self.xb_sa_lead_id.sudo()
        users = acc.xb_sa_support_user_ids | lead.user_id
        self._xb_sa_notify(lead or job, users,
                           f"{self.whatsapp_number} volvió a escribir y espera a una persona: «{texto[:300]}»",
                           urgente=True)
        self.sudo().xb_sa_hold_dt = ahora
        if self.xb_sa_pause_reason == "human" or not acc.xb_sa_hold_message:
            job.write({"state": "skipped", "reason": "En pausa; se avisó al equipo"})
            return
        job.reply = acc.xb_sa_hold_message
        if acc.xb_sa_shadow:
            self._xb_sa_post_draft(acc.xb_sa_hold_message)
            job.write({"state": "draft", "reason": "En pausa; se avisó al equipo y al cliente"})
        else:
            self._xb_sa_send(acc.xb_sa_hold_message)
            job.write({"state": "done", "reason": "En pausa; se avisó al equipo y al cliente"})

    def _xb_sa_run_tool(self, job, nombre, entrada):
        metodo = getattr(self, f"_xb_sa_tool_{nombre}", None)
        if not metodo:
            return f"Herramienta desconocida: {nombre}", True
        try:
            with self.env.cr.savepoint():
                resultado = metodo(job, entrada or {})
            es_error = False
        except Exception as e:  # noqa: BLE001 - el error se le explica al modelo
            _logger.exception("xb_support_agent: falló la herramienta %s", nombre)
            resultado, es_error = f"Error: {e}", True
        if not isinstance(resultado, str):
            resultado = json.dumps(resultado, ensure_ascii=False, default=str)
        job._xb_log(f"▸ {nombre}({json.dumps(entrada, ensure_ascii=False)})\n  → {resultado[:1500]}")
        return resultado, es_error

    # ------------------------------------------------------------------
    # Salida
    # ------------------------------------------------------------------
    def _xb_sa_send(self, texto):
        """Mensaje libre dentro de la ventana de 24 h (sin plantilla, sin costo)."""
        self.ensure_one()
        self.sudo().message_post(
            body=Markup(tools.plaintext2html(texto or "")),
            message_type="whatsapp_message",
            author_id=self.env.ref("base.partner_root").id,
            subtype_xmlid="mail.mt_comment",
        )

    def _xb_sa_post_draft(self, texto):
        """Modo ensayo: nota interna que el cliente NO recibe."""
        self.ensure_one()
        self.sudo().message_post(
            body=Markup(XB_DRAFT_HTML) + Markup(tools.plaintext2html(texto)),
            message_type="comment",
            author_id=self.env.ref("base.partner_root").id,
            subtype_xmlid="mail.mt_note",
        )

    def _xb_sa_post_image(self, data, nombre, pie):
        """Imagen al cliente (o, en ensayo, como nota con la imagen)."""
        self.ensure_one()
        acc = self.wa_account_id.sudo()
        adjunto = self.env["ir.attachment"].sudo().create({
            "name": nombre.replace("/", "-"), "raw": data, "mimetype": "image/jpeg",
            "res_model": "discuss.channel", "res_id": self.id})
        cuerpo = Markup(tools.plaintext2html(pie)) if pie else ""
        if acc.xb_sa_shadow:
            self.sudo().message_post(
                body=Markup(XB_DRAFT_HTML) + (cuerpo or Markup("<p>(captura)</p>")), message_type="comment",
                author_id=self.env.ref("base.partner_root").id, subtype_xmlid="mail.mt_note",
                attachment_ids=adjunto.ids)
        else:
            self.sudo().message_post(
                body=cuerpo, message_type="whatsapp_message", author_id=self.env.ref("base.partner_root").id,
                subtype_xmlid="mail.mt_comment", attachment_ids=adjunto.ids)

    def _xb_sa_notify(self, record, users, resumen, urgente=False, bandeja=False):
        """Actividad para cada responsable; si es urgente (o se pide ``bandeja``), además aviso en su bandeja."""
        if not users:
            return
        for user in users:
            record.sudo().activity_schedule(
                "mail.mail_activity_data_todo",
                summary=("🚨 " if urgente else "") + resumen[:120],
                note=Markup(tools.plaintext2html(resumen)),
                user_id=user.id,
            )
        if urgente or bandeja:
            record.sudo().message_post(
                body=Markup(tools.plaintext2html(f"{'🚨 Urgente: ' if urgente else '🔔 '}{resumen}")),
                partner_ids=users.partner_id.ids,
                subtype_xmlid="mail.mt_comment",
            )

    def _xb_sa_alert_failure(self, job):
        acc = self.wa_account_id.sudo()
        self._xb_sa_notify(job, acc.xb_sa_support_user_ids,
                           f"El agente no pudo contestar a {self.whatsapp_number}: {job.reason}", urgente=True)

    # ------------------------------------------------------------------
    # Herramientas
    # ------------------------------------------------------------------
    def _xb_sa_tool_seleccionar_sistema(self, job, entrada):
        base = (entrada.get("base_de_datos") or "").strip()
        contactos = self._xb_sa_contacts()
        elegido = contactos.filtered(lambda c: base in (c.database_name, c.project_id.name))[:1]
        if not elegido:
            return {"ok": False, "motivo": "Ese número no está autorizado en ese sistema.",
                    "sistemas_permitidos": contactos.mapped("database_name")}
        self.sudo().xb_sa_project_id = elegido.project_id
        job.write({"project_id": elegido.project_id.id, "contact_id": elegido.id})
        return {"ok": True, "sistema": elegido.project_id.name}

    def _xb_sa_tool_revisar_sistema(self, job, entrada):
        _contactos, contacto, proyecto = self._xb_sa_current()
        if not (contacto and proyecto):
            return {"ok": False, "motivo": "No hay un sistema autorizado seleccionado para este número."}
        p = proyecto.sudo()
        datos = {
            "sistema": p.name,
            "base": p.database_name,
            "version_odoo": p.database_version,
            "servidor": p.despacho_server,
            "usuarios": p.despacho_user_count,
            "ultimo_respaldo": self._xb_sa_backup_status(p),
            "sitio": self._xb_sa_check_url(p.database_url),
        }
        if p.despacho_db_local and p.despacho_server == XB_LOCAL_SERVER and p.database_name:
            datos["por_dentro"] = self._xb_sa_inspect_db(p.database_name)
        else:
            datos["por_dentro"] = "No disponible: este sistema vive en otro servidor; solo se revisó el sitio."
        return datos

    @api.model
    def _xb_sa_backup_status(self, proyecto):
        """Último respaldo REAL (lo resume un cron de root cada hora en un JSON);
        si la base no está en este servidor, el dato del inventario de Despacho."""
        try:
            with open(XB_BACKUP_STATUS) as f:
                info = json.load(f)["bases"].get(proyecto.database_name)
        except (OSError, ValueError, KeyError):
            info = None
        if info:
            estado = "completo" if info.get("completo") else "INCOMPLETO"
            return f"{info.get('modificado')} ({estado}); además se guardan copias en 2 nubes por 30 días"
        if proyecto.despacho_last_backup:
            return f"Según el inventario: {proyecto.despacho_last_backup} (dato del último censo, puede no estar al día)"
        return "Sin información de respaldos"

    @api.model
    def _xb_sa_check_url(self, url):
        if not url:
            return "Sin dirección registrada"
        url = url.rstrip("/") + "/web/login"
        try:
            r = requests.get(url, timeout=12, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (XUBAX soporte)"})
            ms = int(r.elapsed.total_seconds() * 1000)
            if r.status_code == 200:
                return f"Responde bien ({ms} ms)"
            if r.status_code in (403, 429):
                return f"Respondió {r.status_code}: un filtro de seguridad bloqueó la revisión; no significa que esté caído"
            return f"Respondió con error {r.status_code} ({ms} ms)"
        except requests.RequestException as e:
            return f"NO responde: {type(e).__name__}"

    @api.model
    def _xb_sa_inspect_db(self, dbname):
        """Revisiones por dentro, de solo lectura, sobre la base del cliente."""
        consultas = {
            "correos_con_error_7_dias": """
                SELECT count(*) FROM mail_mail
                 WHERE state = 'exception' AND create_date > now() - interval '7 days'""",
            "correos_atorados_mas_de_1_hora": """
                SELECT count(*) FROM mail_mail
                 WHERE state = 'outgoing' AND create_date < now() - interval '1 hour'""",
            "motivos_de_error_de_correo": """
                SELECT left(failure_reason, 160), count(*) FROM mail_mail
                 WHERE state = 'exception' AND create_date > now() - interval '7 days'
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 3""",
            "tareas_automaticas_fallando": """
                SELECT cron_name, failure_count, first_failure_date FROM ir_cron
                 WHERE active AND failure_count > 0 ORDER BY failure_count DESC LIMIT 5""",
            "facturas_con_error_de_timbrado_7_dias": """
                SELECT state, count(*) FROM l10n_mx_edi_document
                 WHERE state LIKE '%%failed%%' AND create_date > now() - interval '7 days'
                 GROUP BY 1""",
            "cajas_abiertas_hace_mas_de_1_dia": """
                SELECT name, start_at FROM pos_session
                 WHERE state = 'opened' AND start_at < now() - interval '1 day'
                 ORDER BY start_at LIMIT 5""",
            "usuarios_activos_e_ultimo_acceso": """
                SELECT (SELECT count(*) FROM res_users WHERE active AND NOT share),
                       (SELECT max(create_date) FROM res_users_log)""",
        }
        resultado = {}
        with sql_db.db_connect(dbname).cursor() as cr:
            cr.execute("SET TRANSACTION READ ONLY")
            for clave, sql in consultas.items():
                cr.execute("SAVEPOINT xb")
                try:
                    cr.execute(sql)
                    filas = cr.fetchall()
                    resultado[clave] = filas[0][0] if len(filas) == 1 and len(filas[0]) == 1 else filas
                    cr.execute("RELEASE SAVEPOINT xb")
                except Exception:  # noqa: BLE001 - tabla o columna que no existe en esa base
                    cr.execute("ROLLBACK TO SAVEPOINT xb")
                    resultado[clave] = "no aplica en este sistema"
            cr.rollback()
        return resultado

    # --- Consultas libres de solo lectura (ver client_query.py) ---------
    def _xb_sa_client_query(self, fn, *args):
        _contactos, contacto, proyecto = self._xb_sa_current()
        if not (contacto and proyecto):
            return {"ok": False, "motivo": "No hay un sistema autorizado seleccionado para este número."}
        p = proyecto.sudo()
        local = p.despacho_db_local and p.despacho_server == XB_LOCAL_SERVER
        if not p.database_name or not (local or remote.configurado(self.env, p.despacho_server)):
            return {"ok": False, "motivo": "Este sistema vive en otro servidor: solo se puede revisar con revisar_sistema."}
        try:
            if not local:
                c = contacto.sudo()
                return remote.llamar(self.env, p.despacho_server, "consulta", db=p.database_name, fn=fn.__name__,
                                     args=list(args), contacto={"role": c.role, "can_billing": c.can_billing,
                                                                "remote_user_id": c.remote_user_id})
            with client_query.client_env(p.database_name, contacto.sudo()) as (env, rol):
                return fn(env, rol, *args)
        except remote.XbRemoteError as e:
            return {"ok": False, "motivo": f"No pude consultar ese sistema ahora ({e}). Pasa a una persona si hace falta."}
        except client_query.XbNoAgentUser:
            return {"ok": False, "motivo": "Este sistema todavía no tiene dado de alta el usuario de consulta del "
                                           "agente; no se pueden ver sus datos. Pásalo a una persona si hace falta."}

    def _xb_sa_tool_buscar_modelos(self, job, entrada):
        return self._xb_sa_client_query(client_query.buscar_modelos, entrada.get("texto"))

    def _xb_sa_tool_describir_modelo(self, job, entrada):
        return self._xb_sa_client_query(client_query.describir_modelo, entrada.get("modelo"), entrada.get("texto"))

    def _xb_sa_tool_consultar_registros(self, job, entrada):
        return self._xb_sa_client_query(
            client_query.consultar_registros, entrada.get("modelo"), entrada.get("filtro"),
            entrada.get("campos"), entrada.get("orden"), entrada.get("limite"))

    def _xb_sa_tool_resumir_registros(self, job, entrada):
        return self._xb_sa_client_query(
            client_query.resumir_registros, entrada.get("modelo"), entrada.get("filtro"),
            entrada.get("agrupar_por"), entrada.get("totales"), entrada.get("orden"), entrada.get("limite"))

    def _xb_sa_tool_historial_de_cambios(self, job, entrada):
        return self._xb_sa_client_query(
            client_query.historial_de_cambios, entrada.get("modelo"), entrada.get("registro_id"))

    def _xb_sa_tool_enviar_captura(self, job, entrada):
        _contactos, contacto, proyecto = self._xb_sa_current()
        p = proyecto.sudo()
        if not (contacto and p.despacho_db_local and p.despacho_server == XB_LOCAL_SERVER and p.database_name):
            return {"ok": False, "motivo": "No disponible para este sistema."}
        try:
            jpeg, titulo, resaltado = screenshots.tomar_captura(
                p.database_name, contacto.sudo(), entrada.get("menu"), entrada.get("registro_id"), entrada.get("resaltar"))
        except client_query.XbNoAgentUser:
            return {"ok": False, "motivo": "Este sistema no tiene el usuario de consulta del agente."}
        self._xb_sa_post_image(jpeg, f"{titulo}.jpg", entrada.get("pie") or "")
        return {"ok": True, "pantalla": titulo, "resaltado": bool(resaltado),
                "nota": "La imagen ya se le mandó. Si «resaltado» es false, el texto no estaba visible: dile dónde está."}

    # --- Servicio cobrado (ver client_write.py y support_service.py) ---
    def _xb_sa_tool_cotizar_servicio(self, job, entrada):
        _contactos, contacto, proyecto = self._xb_sa_current()
        p = proyecto.sudo()
        if not (contacto and p.database_name):
            return {"ok": False, "motivo": "No hay un sistema autorizado seleccionado."}
        aprobador = self.env["xb.support.contact"]
        if contacto.guest:
            # Invitado: puede pedirlo, pero el SÍ lo da el titular que lo invitó (desde su número).
            aprobador = self.env["xb.support.contact"].sudo().search([
                ("project_id", "=", p.id), ("guest", "=", False), ("active", "=", True), ("role", "=", "owner"),
                ("can_billing", "=", True), ("remote_user_id", "=", contacto.remote_user_id)], limit=1)
            if not aprobador:
                return {"ok": False, "motivo": "El titular que lo invitó ya no puede autorizar: pasa a una persona del equipo."}
        elif not (contacto.role == "owner" and contacto.can_billing):
            return {"ok": False, "motivo": "Solo quien autoriza servicios en su sistema puede pedirlos (tienen costo). "
                                           "Dile que se lo pida a esa persona, o explícale cómo hacerlo (eso es gratis)."}
        Servicio = self.env["xb.support.service"].sudo()
        local = p.despacho_db_local and p.despacho_server == XB_LOCAL_SERVER
        ejecutor, vista, plan = "team", "", []
        if (entrada.get("operaciones") or "").strip() and local:
            plan = client_write.parse_plan(entrada["operaciones"])
            try:
                vista = Servicio._xb_preview_text(client_write.ensayar(p.database_name, contacto.remote_user_id, plan))
                ejecutor = "ai"
            except client_write.XbServiceRefused as e:
                vista = str(e)
            except client_query.XbNoAgentUser:
                vista = "Tu usuario ya no está activo en el sistema: lo hace el equipo."
        maximo = support_service.XB_AI_MAX_MINUTES if ejecutor == "ai" else None
        minutos = Servicio._xb_round_minutes(entrada.get("minutos"), maximo=maximo)
        operaciones = json.dumps(plan, ensure_ascii=False) if plan else False
        previo = Servicio.search([("channel_id", "=", self.id), ("state", "=", "quoted"),
                                  ("operations", "=", operaciones)], limit=1)
        if previo and operaciones:
            return {"ok": True, "servicio_id": previo.id, "minutos": previo.minutes,
                    "precio": f"${previo.amount:,.2f} más IVA", "vista_previa": previo.preview,
                    "siguiente": "Esta cotización ya existía y sigue vigente. Si el cliente ya respondió SÍ, llama "
                                 "ejecutar_servicio; si no, pídele el SÍ."}
        Servicio.search([("channel_id", "=", self.id), ("state", "=", "quoted")]).write({"state": "cancelled"})
        servicio = Servicio.create({
            "name": entrada.get("descripcion") or "Servicio en el sistema",
            "executor": ejecutor, "channel_id": self.id, "project_id": p.id, "contact_id": contacto.id,
            "approver_id": aprobador.id or False, "whatsapp_number": self.whatsapp_number, "minutes": minutos,
            "operations": json.dumps(plan, ensure_ascii=False) if plan else False, "preview": vista,
        })
        if aprobador:
            avisado = servicio._xb_ask_approver()
            if not avisado:
                self._xb_sa_notify(servicio, self.wa_account_id.sudo().xb_sa_support_user_ids,
                                   f"{contacto.name} (invitado de {aprobador.name}) pide un servicio en {p.name}: "
                                   f"{servicio.name}. No se pudo pedir el SÍ por WhatsApp a {aprobador.name} "
                                   f"({aprobador.phone}): contáctalo.", bandeja=True)
            return {"ok": True, "servicio_id": servicio.id, "minutos": minutos,
                    "precio": f"${servicio.amount:,.2f} más IVA", "vista_previa": vista,
                    "lo_hace": "la IA, en cuanto el titular autorice" if ejecutor == "ai"
                    else "una persona del equipo, en horario de oficina",
                    "siguiente": f"Dile qué se va a hacer y el precio MÁS IVA, y que lo autoriza {aprobador.name} (quien le dio "
                                 "acceso): " + ("ya se le pidió por WhatsApp su SÍ. " if avisado else
                                 "no se le pudo escribir ahora; el equipo lo contactará. ") +
                                 "Tú NO puedes autorizarlo ni llamar ejecutar_servicio en esta plática; dile que le avisas "
                                 "cuando quede."}
        if p.xb_sa_store:
            return {"ok": True, "servicio_id": servicio.id, "precio": "SIN COSTO (es el sistema de la tienda)",
                    "lo_hace": "la IA, en cuanto autorices" if ejecutor == "ai" else "una persona del equipo",
                    "vista_previa": vista,
                    "siguiente": "Dile qué se va a cambiar, SIN hablar de precio (no cuesta), y pide que responda SÍ para hacerlo. "
                                 "NO llames ejecutar_servicio hasta que responda SÍ."}
        return {"ok": True, "servicio_id": servicio.id, "minutos": minutos,
                "precio": f"${servicio.amount:,.2f} más IVA",
                "lo_hace": "la IA, en cuanto autorice" if ejecutor == "ai"
                else "una persona del equipo, en horario de oficina", "vista_previa": vista,
                "siguiente": "Dile qué se va a hacer y el precio MÁS IVA (el tiempo se cobra como hora de servicio, "
                             "mínimo 15 min) y pide que responda SÍ para autorizar. NO llames ejecutar_servicio "
                             "hasta que el cliente responda SÍ."}

    def _xb_sa_tool_ejecutar_servicio(self, job, entrada):
        Servicio = self.env["xb.support.service"].sudo()
        mios = self._xb_sa_contacts()
        propios = [("channel_id", "=", self.id), ("state", "=", "quoted"), ("approver_id", "=", False)]
        de_invitados = [("approver_id", "in", mios.ids), ("state", "=", "quoted"),
                        ("quote_dt", ">", fields.Datetime.now() - timedelta(hours=24))]
        servicio = Servicio.browse(int(entrada.get("servicio_id") or 0)).exists()
        if not servicio or servicio.state != "quoted" or not (
                (servicio.channel_id == self and not servicio.approver_id) or servicio.approver_id in mios):
            servicio = Servicio.search(propios, order="id desc", limit=1) or Servicio.search(
                de_invitados, order="id desc", limit=1)
        if not servicio:
            return {"ok": False, "motivo": "No hay un servicio cotizado con ese número en esta plática "
                                           "(si lo pidió un invitado, solo lo autoriza el titular desde su número)."}
        si = servicio._xb_authorization(self)
        if not si:
            return {"ok": False, "motivo": "El cliente todavía no respondió SÍ después de la cotización (o pasaron "
                                           "más de 24 h). Pídele que lo confirme."}
        servicio.write({"authorized_dt": fields.Datetime.now(), "authorization_message_id": si.id})
        self._xb_sa_tell_guest(servicio, f"{servicio.approver_id.name} autorizó tu solicitud: «{servicio.name}». "
                                         + ("Ya lo estoy haciendo." if servicio.executor == "ai"
                                            else "Una persona del equipo lo hará en horario de oficina y te confirma."))
        acc = self.wa_account_id.sudo()
        usados = servicio._xb_month_minutes(servicio.project_id)
        if usados + servicio.minutes > servicio._xb_cap_minutes() and servicio.executor == "ai":
            servicio.write({"executor": "team", "preview": (servicio.preview or "") +
                            f"\n(Rebasa el tope mensual: ya van {usados} min este mes.)"})
            servicio.state = "team"
            self._xb_sa_notify(servicio, acc.xb_sa_support_user_ids,
                               f"Servicio autorizado que rebasa el tope mensual ({usados} min ya este mes) en "
                               f"{servicio.project_id.name}: {servicio.name}. Confírmalo antes de hacerlo.", urgente=True)
            servicio._xb_notify_authorizers()
            return {"ok": True, "nota": "Quedó autorizado, pero este mes ya se alcanzó el tope de servicios: una "
                                        "persona de XUBAX lo confirma y lo hace. Díselo con amabilidad."}
        if servicio.executor == "team":
            servicio.state = "team"
            self._xb_sa_notify(servicio, acc.xb_sa_support_user_ids,
                               f"Servicio autorizado ({servicio.amount:,.2f} + IVA) en {servicio.project_id.name}: "
                               f"{servicio.name}\n{servicio.preview or ''}")
            servicio._xb_notify_authorizers()
            return {"ok": True, "nota": "Quedó autorizado y en manos del equipo; avísale que lo hacen en horario de "
                                        "oficina y que le confirman por aquí."}
        try:
            hechos = client_write.ejecutar(servicio.project_id.database_name, servicio.contact_id.remote_user_id,
                                           json.loads(servicio.operations), servicio._xb_note())
        except Exception as e:  # noqa: BLE001 - si falla, lo toma el equipo
            servicio.write({"state": "team", "result": f"La IA no pudo hacerlo: {e}"})
            self._xb_sa_notify(servicio, acc.xb_sa_support_user_ids,
                               f"La IA no pudo hacer un servicio autorizado en {servicio.project_id.name}: "
                               f"{servicio.name}. Error: {e}", urgente=True)
            return {"ok": False, "motivo": "No se pudo hacer; ya lo tomó el equipo. Discúlpate y dile que le confirman."}
        servicio.write({"state": "done", "done_dt": fields.Datetime.now(),
                        "result": servicio._xb_preview_text(hechos)})
        servicio._xb_notify_authorizers()
        self._xb_sa_tell_guest(servicio, f"Listo: «{servicio.name}» ya quedó hecho.")
        if servicio.project_id.xb_sa_store:
            return {"ok": True, "hecho": hechos, "cobro": "sin cobro: es el sistema de la tienda"}
        return {"ok": True, "hecho": hechos, "cobro": f"${servicio.amount:,.2f} más IVA, se suma a su factura del mes"}

    def _xb_sa_tell_guest(self, servicio, texto):
        """Si lo pidió un invitado, se le avisa en SU plática (el titular autoriza desde la suya)."""
        canal = servicio.channel_id
        if not (servicio.approver_id and canal and canal != self):
            return
        try:
            canal._xb_sa_send(texto)
        except Exception:  # noqa: BLE001 - fuera de la ventana de 24 h no se puede; el equipo ya lo sabe
            _logger.warning("xb_support_agent: no se pudo avisar al invitado del servicio %s", servicio.id)

    def _xb_sa_tool_errores_del_servidor(self, job, entrada):
        _contactos, contacto, proyecto = self._xb_sa_current()
        p = proyecto.sudo()
        local = p.despacho_db_local and p.despacho_server == XB_LOCAL_SERVER
        if not (contacto and p.database_name and (local or remote.configurado(self.env, p.despacho_server))):
            return {"ok": False, "motivo": "No disponible para este sistema."}
        if not local:
            try:
                return remote.llamar(self.env, p.despacho_server, "errores_recientes", db=p.database_name,
                                     horas=entrada.get("horas"))
            except remote.XbRemoteError as e:
                return {"ok": False, "motivo": f"No pude revisar ese servidor ahora ({e})."}
        return client_query.errores_recientes(p.database_name, entrada.get("horas"))

    def _xb_sa_tool_proponer_arreglo(self, job, entrada):
        _contactos, contacto, proyecto = self._xb_sa_current()
        acc = self.wa_account_id.sudo()
        urgente = bool(entrada.get("urgente"))
        prop = self.env["xb.support.proposal"].sudo().with_company(acc._xb_sa_company()).create({
            "name": entrada.get("resumen") or "Arreglo propuesto",
            "kind": "fix",
            "urgency": "high" if urgente else "normal",
            "channel_id": self.id,
            "project_id": proyecto.id,
            "contact_id": contacto.id,
            "whatsapp_number": self.whatsapp_number,
            "problem": entrada.get("problema"),
            "suggestion": entrada.get("propuesta"),
        })
        self._xb_sa_notify(prop, acc.xb_sa_support_user_ids,
                           f"Propuesta de arreglo en {proyecto.name or 'sistema sin elegir'}: {prop.name}", urgente)
        return {"ok": True, "propuesta": prop.id, "nota": "Queda pendiente de que el equipo la apruebe."}

    def _xb_sa_tool_proponer_alta_numero(self, job, entrada):
        from . import support_contact
        _contactos, contacto, proyecto = self._xb_sa_current()
        if not (contacto and contacto.role == "owner" and contacto.can_billing and not contacto.guest):
            return {"ok": False, "motivo": "Solo quien autoriza servicios en el sistema puede dar acceso a otra persona."}
        clave = xb_phone_key(entrada.get("celular"))
        if not clave:
            return {"ok": False, "motivo": "El celular debe tener 10 dígitos."}
        Contacto = self.env["xb.support.contact"].sudo().with_context(active_test=False)
        previo = Contacto.search([("phone_key", "=", clave), ("project_id", "=", proyecto.id)], limit=1)
        acc = self.wa_account_id.sudo()
        if entrada.get("quitar"):
            if not (previo and previo.guest):
                return {"ok": False, "motivo": "Ese número no es un invitado de este sistema."}
            previo.active = False
            support_contact._XB_RESOLVE_CACHE.clear()
            self._xb_sa_notify(proyecto, acc.xb_sa_support_user_ids,
                               f"{contacto.name} quitó el acceso de invitado de {previo.name} en {proyecto.name}")
            return {"ok": True, "nota": f"Listo: {previo.name} ya no puede consultar."}
        if previo and not previo.guest and previo.active:
            return {"ok": False, "motivo": "Esa persona ya tiene acceso como usuario del sistema."}
        nombre = (entrada.get("nombre") or "").strip()
        if not nombre:
            return {"ok": False, "motivo": "Falta el nombre de la persona."}
        vals = {"name": nombre, "phone": entrada.get("celular"), "project_id": proyecto.id, "guest": True,
                "guest_by": contacto.name, "auto": False, "active": True, "role": "employee", "can_billing": False,
                "remote_user_id": contacto.remote_user_id, "remote_login": f"invitado de {contacto.name}",
                "note": f"Invitado por {contacto.name} desde WhatsApp ({fields.Date.today()})."}
        if previo:
            previo.write(vals)
        else:
            Contacto.create(vals)
        support_contact._XB_RESOLVE_CACHE.clear()
        self._xb_sa_notify(proyecto, acc.xb_sa_support_user_ids,
                           f"{contacto.name} dio acceso de consulta a {nombre} ({entrada.get('celular')}) en {proyecto.name}")
        return {"ok": True, "nota": f"Listo: {nombre} ya puede escribir a este número y consultar {proyecto.name} "
                                    "(consulta sin dinero, capturas; si pide un cambio con costo, lo autorizas tú con un SÍ). Avísale tú que ya puede "
                                    "escribir; si quieres quitarle el acceso, dímelo."}

    def _xb_sa_tool_pasar_a_humano(self, job, entrada):
        acc = self.wa_account_id.sudo()
        _contactos, contacto, proyecto = self._xb_sa_current()
        urgente = bool(entrada.get("urgente")) or entrada.get("motivo") == "caida_grave"
        motivos = {"no_sabe": "El agente no supo resolver", "dinero": "Tema de dinero",
                   "pide_humano": "El cliente pidió una persona", "caida_grave": "CAÍDA GRAVE",
                   "otro": "Revisión"}
        titulo = f"{motivos.get(entrada.get('motivo'), 'Revisión')} · {contacto.name or self.whatsapp_number}"
        cuerpo = (f"{entrada.get('resumen') or ''}\n\nWhatsApp: {self.whatsapp_number}"
                  f"\nSistema: {proyecto.name or '—'}")
        registro, users = job, acc.xb_sa_support_user_ids
        lead = self.xb_sa_lead_id.sudo()
        if not _contactos and lead:
            # Prospecto: lo atiende ventas, en su oportunidad del CRM.
            registro, users = lead, lead.user_id or acc.xb_sa_sales_user_ids or users
        elif acc.xb_sa_helpdesk_team_id:
            registro = self.env["helpdesk.ticket"].sudo().create({
                "name": titulo,
                "team_id": acc.xb_sa_helpdesk_team_id.id,
                "description": Markup(tools.plaintext2html(cuerpo)),
                "partner_id": contacto.partner_id.id or False,
                "priority": "3" if urgente else "1",
            })
        if not _contactos:
            # Prospecto o miembro de BNI: también le toca a ventas (Josette), no solo a soporte.
            users = users | acc.xb_sa_sales_user_ids | lead.user_id
        self._xb_sa_notify(registro, users, f"{titulo}\n{cuerpo}", urgente, bandeja=True)
        # El agente NO se calla: sigue contestando lo demás. Solo se recuerda que ya se avisó.
        if entrada.get("motivo") != "caida_grave":
            self.sudo().write({"xb_sa_pause_reason": "handoff", "xb_sa_hold_dt": fields.Datetime.now()})
        return {"ok": True, "nota": "El equipo ya fue avisado. Díselo al cliente con amabilidad."}

    def _xb_sa_lead_vals(self, acc):
        user = acc._xb_sa_next_sales_user()
        return {
            "user_id": user.id or False,
            "team_id": acc.xb_sa_sales_team_id.id or False,
            "company_id": acc._xb_sa_company().id,
            "phone": self.whatsapp_number,
            # Mismo medio que los demás prospectos de WhatsApp: filtro «Desde WhatsApp» del CRM.
            "medium_id": self.env["utm.medium"].sudo().search([("name", "=", "WhatsApp")], limit=1).id or False,
        }

    def _xb_sa_tool_registrar_prospecto(self, job, entrada):
        acc = self.wa_account_id.sudo()
        descripcion = "\n".join(f"{k.capitalize()}: {v}" for k, v in entrada.items() if v)
        vals = {
            "contact_name": entrada.get("nombre") or False,
            "partner_name": entrada.get("empresa") or False,
            "email_from": entrada.get("correo") or False,
            "city": entrada.get("ciudad") or False,
            "description": Markup(tools.plaintext2html(descripcion + "\n\n(Registrado por el agente de WhatsApp)")),
        }
        lead = self.xb_sa_lead_id.sudo()
        if lead:
            lead.write({k: v for k, v in vals.items() if v})
            return {"ok": True, "nota": "Prospecto actualizado."}
        vals.update(self._xb_sa_lead_vals(acc))
        # Si el CRM no usa «Iniciativas», un registro tipo lead no se ve en el embudo.
        usa_iniciativas = self.env.ref("crm.group_use_lead").sudo().all_user_ids.filtered(lambda u: not u.share)
        vals.update({"name": f"WhatsApp: {entrada.get('empresa') or entrada.get('nombre') or self.whatsapp_number}",
                     "type": "lead" if usa_iniciativas else "opportunity"})
        lead = self.env["crm.lead"].sudo().with_company(acc._xb_sa_company()).create(vals)
        self.sudo().xb_sa_lead_id = lead
        job.mode = "prospect"
        self._xb_sa_notify(lead, lead.user_id or acc.xb_sa_sales_user_ids, f"Prospecto nuevo por WhatsApp: {lead.name}")
        return {"ok": True, "nota": "Prospecto registrado."}

    def _xb_sa_tool_registrar_interes_compra(self, job, entrada):
        acc = self.wa_account_id.sudo()
        _contactos, contacto, proyecto = self._xb_sa_current()
        if not contacto:
            return {"ok": False, "motivo": "Este número no es de un cliente; usa registrar_prospecto."}
        vals = self._xb_sa_lead_vals(acc)
        vals.update({
            "name": f"{proyecto.name}: {entrada.get('resumen')}",
            "type": "opportunity",
            "contact_name": contacto.name,
            "partner_id": contacto.partner_id.id or False,
            "description": Markup(tools.plaintext2html(
                f"{entrada.get('detalle') or ''}\n\nCliente: {contacto.name} ({proyecto.name})\n(Registrado por el agente de WhatsApp)")),
        })
        lead = self.env["crm.lead"].sudo().with_company(acc._xb_sa_company()).create(vals)
        self.sudo().xb_sa_lead_id = lead
        job.mode = "sales"
        self._xb_sa_notify(lead, lead.user_id or acc.xb_sa_sales_user_ids, f"Oportunidad de cliente actual: {lead.name}")
        return {"ok": True, "nota": "Oportunidad registrada; un asesor preparará la cotización."}

    @api.model
    def _xb_sa_attach_label(self, adjunto):
        m = adjunto.mimetype or ""
        if m == "application/pdf":
            return "documento PDF"
        if "presentation" in m or "powerpoint" in m:
            return "presentación de PowerPoint (no la puedes leer; si es una HORLI, guárdala y pide también el PDF)"
        return {"image": "imagen", "audio": "audio", "video": "video"}.get(m.split("/")[0], "archivo")

    def _xb_sa_post_file(self, datos, nombre, pie):
        """Archivo (video, PDF, presentación…) al cliente; en ensayo, como nota con el archivo."""
        self.ensure_one()
        acc = self.wa_account_id.sudo()
        tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        adjunto = self.env["ir.attachment"].sudo().create({
            "name": nombre.replace("/", "-"), "raw": datos, "mimetype": tipo,
            "res_model": "discuss.channel", "res_id": self.id})
        cuerpo = Markup(tools.plaintext2html(pie)) if pie else ""
        if acc.xb_sa_shadow:
            self.sudo().message_post(
                body=Markup(XB_DRAFT_HTML) + (cuerpo or Markup("<p>(archivo)</p>")), message_type="comment",
                author_id=self.env.ref("base.partner_root").id, subtype_xmlid="mail.mt_note",
                attachment_ids=adjunto.ids)
        else:
            self.sudo().message_post(
                body=cuerpo, message_type="whatsapp_message", author_id=self.env.ref("base.partner_root").id,
                subtype_xmlid="mail.mt_comment", attachment_ids=adjunto.ids)

    def _xb_sa_team_user(self):
        """Usuario interno de XUBAX dueño de este teléfono, si está en la lista del equipo (parámetro
        xb_support_agent.team_user_ids = ids separados por coma). Vacío si no."""
        self.ensure_one()
        llave = xb_phone_key(self.whatsapp_number)
        ids = [int(x) for x in re.findall(r"\d+", self.env["ir.config_parameter"].sudo().get_param(
            "xb_support_agent.team_user_ids") or "")]
        if not (llave and ids):
            return self.env["res.users"]
        return self.env["res.users"].sudo().browse(ids).filtered(
            lambda u: u.active and not u.share and xb_phone_key(u.partner_id.phone) == llave)[:1]

    def _xb_sa_team_events(self, cita_id=None):
        tipo = self.wa_account_id.sudo().xb_sa_bni_appointment_type_id
        dom = [("appointment_type_id", "=", tipo.id), ("start", ">", fields.Datetime.now())]
        if cita_id:
            dom.append(("id", "=", int(cita_id)))
        return self.env["calendar.event"].sudo().search(dom, order="start", limit=30)

    def _xb_sa_local(self, dt):
        return pytz.utc.localize(dt).astimezone(pytz.timezone(XB_TZ))

    def _xb_sa_tool_ver_citas_bni(self, job, entrada):
        if not self._xb_sa_team_user():
            return {"ok": False, "motivo": "Solo el equipo de XUBAX puede usar esto."}
        return {"ok": True, "citas": [
            {"cita_id": e.id, "miembro": ", ".join((e.partner_ids - e.user_id.partner_id).mapped("name")),
             "cuando": f"{XB_DIAS[self._xb_sa_local(e.start).weekday()]} {self._xb_sa_local(e.start):%d/%m/%Y %H:%M}"}
            for e in self._xb_sa_team_events()]}

    def _xb_sa_tell_member(self, evento, texto):
        """Avisa al miembro en su plática si escribió hace menos de 24 h (ventana libre de WhatsApp). Devuelve si lo avisó."""
        socio = (evento.partner_ids - evento.user_id.partner_id)[:1]
        canal = self.env["discuss.channel"].sudo().search([
            ("whatsapp_partner_id", "=", socio.id), ("wa_account_id", "=", self.wa_account_id.id)], limit=1)
        if not canal:
            return False
        ultimo = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", canal.id), ("message_type", "=", "whatsapp_message"),
            ("date", ">", fields.Datetime.now() - timedelta(hours=23))], order="id desc", limit=10)
        if not any(m.wa_message_ids.filtered(lambda w: w.message_type == "inbound") for m in ultimo):
            return False
        canal._xb_sa_send(texto)
        return True

    def _xb_sa_tool_mover_cita_bni(self, job, entrada):
        if not self._xb_sa_team_user():
            return {"ok": False, "motivo": "Solo el equipo de XUBAX puede usar esto."}
        evento = self._xb_sa_team_events(entrada.get("cita_id"))[:1]
        if not evento:
            return {"ok": False, "motivo": "No encuentro ese 1 a 1 de BNI próximo; usa ver_citas_bni."}
        try:
            local = pytz.timezone(XB_TZ).localize(datetime.strptime((entrada.get("inicio") or "").strip(), "%Y-%m-%d %H:%M"))
        except ValueError:
            return {"ok": False, "motivo": "La fecha debe ir como AAAA-MM-DD HH:MM."}
        inicio = local.astimezone(pytz.utc).replace(tzinfo=None)
        if inicio <= fields.Datetime.now():
            return {"ok": False, "motivo": "Esa hora ya pasó."}
        fin = inicio + (evento.stop - evento.start)
        choque = self.env["calendar.event"].sudo().search([
            ("user_id", "=", evento.user_id.id), ("id", "!=", evento.id), ("start", "<", fin), ("stop", ">", inicio)], limit=1)
        if choque:
            return {"ok": False, "motivo": f"A esa hora Josette ya tiene «{choque.name}»; escoge otra o pídele que la libere."}
        evento.write({"start": inicio, "stop": fin})
        miembro = ", ".join((evento.partner_ids - evento.user_id.partner_id).mapped("name"))
        cuando = f"{XB_DIAS[local.weekday()]} {local:%d/%m/%Y a las %H:%M}"
        avisado = self._xb_sa_tell_member(evento, f"Hola, te aviso que tu 1 a 1 con Josette cambió: ahora es el {cuando}. "
                                                  "Si no te acomoda, dime y lo vemos.")
        return {"ok": True, "miembro": miembro, "nuevo_horario": cuando, "miembro_avisado_por_whatsapp": avisado,
                "nota": "" if avisado else "No se le pudo avisar por WhatsApp (no ha escrito en 24 h): dile a la persona del equipo que le avise."}

    def _xb_sa_tool_cancelar_cita_bni(self, job, entrada):
        if not self._xb_sa_team_user():
            return {"ok": False, "motivo": "Solo el equipo de XUBAX puede usar esto."}
        evento = self._xb_sa_team_events(entrada.get("cita_id"))[:1]
        if not evento:
            return {"ok": False, "motivo": "No encuentro ese 1 a 1 de BNI próximo; usa ver_citas_bni."}
        miembro = ", ".join((evento.partner_ids - evento.user_id.partner_id).mapped("name"))
        cuando = f"{XB_DIAS[self._xb_sa_local(evento.start).weekday()]} {self._xb_sa_local(evento.start):%d/%m/%Y %H:%M}"
        avisado = self._xb_sa_tell_member(evento, f"Hola, te aviso que se canceló tu 1 a 1 con Josette del {cuando}. "
                                                  "Si quieres, te busco otro horario.")
        evento.unlink()
        return {"ok": True, "miembro": miembro, "cancelada": cuando, "miembro_avisado_por_whatsapp": avisado}

    def _xb_sa_fix_event(self, evento, tipo, nombre):
        """La cita del 1 a 1 de BNI sale con su nombre (no el del tipo de cita copiado)."""
        evento = evento.sudo().with_context(dont_notify=True)
        if tipo == self.wa_account_id.sudo().xb_sa_bni_appointment_type_id:
            evento.name = f"1a1 con Josette - {nombre}"
        return evento

    def _xb_sa_bni_event(self):
        """La próxima cita de 1 a 1 de este miembro."""
        partner = self.whatsapp_partner_id.sudo()
        tipo = self.wa_account_id.sudo().xb_sa_bni_appointment_type_id
        if not (partner and tipo):
            return self.env["calendar.event"]
        return self.env["calendar.event"].sudo().search([
            ("appointment_type_id", "=", tipo.id), ("partner_ids", "in", partner.id),
            ("start", ">", fields.Datetime.now())], order="start", limit=1)

    def _xb_sa_bni_sync_event(self, adjuntos=None):
        """Pone en la cita de Josette lo que se sabe del miembro y sus archivos."""
        evento = self._xb_sa_bni_event()
        if not evento:
            return evento
        texto = f"Agendada por el agente de WhatsApp.\nWhatsApp: {self.whatsapp_number}\n\n{self.xb_sa_bni_notes or ''}"
        evento.description = Markup(tools.plaintext2html(texto))
        for a in adjuntos or []:
            if not self.env["ir.attachment"].sudo().search_count([
                    ("res_model", "=", "calendar.event"), ("res_id", "=", evento.id), ("checksum", "=", a.checksum)]):
                a.sudo().copy({"res_model": "calendar.event", "res_id": evento.id})
        return evento

    def _xb_sa_tool_enviar_horli_xubax(self, job, entrada):
        acc = self.wa_account_id.sudo()
        if not acc.xb_sa_bni_horli:
            return {"ok": False, "motivo": "La HORLI de XUBAX todavía no está cargada: dile que Josette se la comparte "
                                           "en el 1 a 1, y pídele la suya."}
        self._xb_sa_post_file(base64.b64decode(acc.xb_sa_bni_horli), acc.xb_sa_bni_horli_name or "HORLI XUBAX.pdf",
                              "Esta es nuestra HORLI, para que llegues sabiendo con quién vas a hablar 🙂")
        return {"ok": True, "nota": "Ya se la mandaste. Pídele la suya (PDF, PowerPoint o imagen)."}

    def _xb_sa_tool_guardar_horli_miembro(self, job, entrada):
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return {"ok": False, "motivo": "No se encontró el contacto de esta plática."}
        mensajes = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("message_type", "=", "whatsapp_message"),
        ], order="id desc", limit=15)
        archivo = self.env["ir.attachment"]
        for m in mensajes:
            if not m.wa_message_ids.filtered(lambda w: w.message_type == "inbound"):
                continue
            archivo = m.attachment_ids.filtered(lambda a: a.mimetype in XB_HORLI_TYPES)[:1]
            if archivo:
                break
        if not archivo:
            return {"ok": False, "motivo": "No encuentro un archivo reciente (PDF, PowerPoint o imagen) de esta persona."}
        archivo = archivo.sudo()
        if not self.env["ir.attachment"].sudo().search_count([
                ("res_model", "=", "res.partner"), ("res_id", "=", partner.id), ("checksum", "=", archivo.checksum)]):
            copia = archivo.copy({"res_model": "res.partner", "res_id": partner.id})
            partner.message_post(body=Markup(tools.plaintext2html(
                f"HORLI recibida por WhatsApp.\n{entrada.get('resumen') or ''}")), message_type="comment",
                subtype_xmlid="mail.mt_note", attachment_ids=copia.ids)
        self.sudo().xb_sa_bni_notes = (self.xb_sa_bni_notes or "") + f"\nSu HORLI dice: {entrada.get('resumen') or '(sin resumen)'}"
        evento = self._xb_sa_bni_sync_event([archivo])
        return {"ok": True, "en_la_cita": bool(evento),
                "nota": "Guardada en su contacto" + (" y en la cita de Josette." if evento else ". Aún no tiene 1 a 1 agendado.")}

    def _xb_sa_tool_registrar_referido_ideal(self, job, entrada):
        acc = self.wa_account_id.sudo()
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return {"ok": False, "motivo": "No se encontró el contacto de esta plática."}
        referido = (entrada.get("referido") or "").strip()
        self.sudo().xb_sa_bni_notes = (self.xb_sa_bni_notes or "") + f"\nSu referido ideal: {referido}"
        evento = self._xb_sa_bni_sync_event()
        limite = evento.start.date() if evento else fields.Date.today() + timedelta(days=3)
        if acc.xb_sa_bni_user_id:
            partner.activity_schedule(
                "mail.mail_activity_data_todo", date_deadline=limite,
                summary=f"Buscar un referido para {partner.name}", user_id=acc.xb_sa_bni_user_id.id,
                note=Markup(tools.plaintext2html(f"Perfil: {referido}" + (" Tenerlo presente en su 1 a 1." if evento else ""))))
        partner.message_post(body=Markup(tools.plaintext2html(f"Su referido ideal: {referido}")),
                             message_type="comment", subtype_xmlid="mail.mt_note")
        return {"ok": True, "nota": "Josette lo tendrá presente."}

    def _xb_sa_tool_enviar_tarjeta_bni(self, job, entrada):
        datos = bni_card.tomar_tarjeta(entrada.get("persona"), entrada.get("negocio"),
                                       entrada.get("cosa1"), entrada.get("cosa2"), entrada.get("cosa3"))
        self._xb_sa_post_image(datos, "tarjeta-xubax.jpg", "Te dejo esto: compártelo si le sirve a alguien más 🙂")
        return {"ok": True, "nota": "La tarjeta ya se mandó."}

    def _xb_sa_first_bni_contact(self):
        """¿Primer mensaje de alguien de BNI? Solo entonces el agente puede buscar su NEGOCIO en internet."""
        self.ensure_one()
        bot = self.env.ref("base.partner_root")
        if self.env["mail.message"].sudo().search_count([
                ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("author_id", "=", bot.id),
                ("message_type", "=", "whatsapp_message")]):
            return False
        ultimo = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id),
            ("message_type", "=", "whatsapp_message")], order="id desc", limit=1)
        texto = html2plaintext(ultimo.body or "").lower()
        return self._xb_sa_is_bni() or "bni" in texto

    def _xb_sa_bni_lista(self):
        """Lo que la lista del capítulo (contacto) ya dice del miembro: negocio y giro."""
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return ""
        negocio = partner.company_name or (partner.parent_id.name if partner.parent_id else "")
        giro = html2plaintext(partner.comment or "").strip()[:600]
        if not (negocio or giro):
            return ""
        return (" LISTA DEL CAPÍTULO (ya lo sabemos, NO se lo preguntes): "
                + (f"negocio «{negocio}»" if negocio else "") + ("; " if negocio and giro else "")
                + (f"giro: {giro}" if giro else "")
                + ". Úsalo en tu primer saludo y haz la búsqueda de su negocio en internet. Si ahí viene su lema o su frase típica, úsala UNA sola vez en el primer saludo, con gracia y cariño, sin burlarte ni repetirla.")

    def _xb_sa_is_ex_bni(self):
        """Exmiembro: etiqueta «Ex-BNI» en su contacto o su oportunidad (la pone Josette o el equipo a mano)."""
        self.ensure_one()
        etiquetas = self.whatsapp_partner_id.sudo().category_id.mapped("name") + \
            self.xb_sa_lead_id.sudo().tag_ids.mapped("name")
        return any(re.sub(r"[^A-Z]", "", (n or "").upper()) in ("EXBNI", "EXMIEMBROBNI", "EXMIEMBRODEBNI") for n in etiquetas)

    def _xb_sa_tool_avisar_salida_bni(self, job, entrada):
        acc = self.wa_account_id.sudo()
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return {"ok": False, "motivo": "No se encontró el contacto de esta plática."}
        self._xb_sa_notify(partner, acc.xb_sa_bni_user_id,
                           f"Dice que ya no es de BNI: {partner.name}. Confirma y, si es cierto, ponle la etiqueta «Ex-BNI». "
                           f"Dijo: {(entrada.get('comentario') or '')[:200]}")
        return {"ok": True, "nota": "Ya se le avisó a Josette. Mientras ella lo confirma, atiéndelo con amabilidad sin ofrecerle el 1 a 1."}

    def _xb_sa_is_bni(self):
        """¿Es miembro de BNI? Marcado por el agente o por la etiqueta «BNI» en su contacto o su oportunidad."""
        self.ensure_one()
        if self._xb_sa_is_ex_bni():
            return False
        if self.xb_sa_bni:
            return True
        etiquetas = self.whatsapp_partner_id.sudo().category_id.mapped("name") + \
            self.xb_sa_lead_id.sudo().tag_ids.mapped("name")
        return any((n or "").strip().upper() == "BNI" for n in etiquetas)

    def _xb_sa_appt_type(self):
        acc = self.wa_account_id.sudo()
        if self._xb_sa_is_bni() and acc.xb_sa_bni_appointment_type_id:
            return acc.xb_sa_bni_appointment_type_id
        return acc.xb_sa_appointment_type_id

    def _xb_sa_tool_marcar_miembro_bni(self, job, entrada):
        """Miembro de BNI: etiqueta en su contacto y aviso a la titular. NO crea oportunidad
        en el CRM (no es una venta); lo que cuenta se queda en el contacto y en la cita."""
        acc = self.wa_account_id.sudo()
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return {"ok": False, "motivo": "No se encontró el contacto de esta plática."}
        if self._xb_sa_is_ex_bni():
            return {"ok": False, "motivo": "Esta persona figura como EXMIEMBRO de BNI: no la marques ni le ofrezcas 1 a 1 con Josette. "
                                           "Atiéndela como a cualquier persona (prospecto o cliente)."}
        etiqueta = self.env["res.partner.category"].sudo().search([("name", "=", "BNI")], limit=1) or \
            self.env["res.partner.category"].sudo().create({"name": "BNI"})
        partner.category_id = [(4, etiqueta.id)]
        detalle = ("Miembro de BNI (registrado por el agente de WhatsApp)\n"
                   f"Nombre: {entrada.get('nombre') or '-'}\nNegocio: {entrada.get('negocio') or '-'}\n"
                   f"A qué se dedica: {entrada.get('giro') or '-'}\nQué busca: {entrada.get('busca') or '-'}\n"
                   f"Su referido ideal: {entrada.get('referido_ideal') or '-'}\n"
                   f"Formato del 1 a 1: {entrada.get('formato') or 'por definir'}")
        if (entrada.get("ficha_publica") or "").strip():
            detalle += f"\nLo público de su negocio (en el primer saludo solo el nombre y un dato curioso; lo demás si lo pregunta): {entrada['ficha_publica'].strip()}"
        self.sudo().write({"xb_sa_bni": True, "xb_sa_bni_notes": detalle})
        partner.message_post(body=Markup(tools.plaintext2html(detalle)), message_type="comment",
                             subtype_xmlid="mail.mt_note")
        job.mode = "prospect"
        if acc.xb_sa_bni_video and not self.xb_sa_bni_welcomed:
            self._xb_sa_post_file(base64.b64decode(acc.xb_sa_bni_video), acc.xb_sa_bni_video_name or "bienvenida.mp4",
                                  "Un saludo de Josette para ti 🙂")
            self.sudo().xb_sa_bni_welcomed = True
        self._xb_sa_notify(partner, acc.xb_sa_bni_user_id,
                           f"Miembro de BNI por WhatsApp: {entrada.get('nombre') or self.whatsapp_number}")
        return {"ok": True, "nota": "Registrado como miembro de BNI" +
                (" y ya recibió el video de Josette." if self.xb_sa_bni_welcomed else ".") +
                " Sigue: ofrécele su 1 a 1 con ver_horarios_demo."}

    def _xb_sa_demo_slots(self, desde=None):
        """Horarios libres de la cita nativa (app Citas): [(inicio UTC, usuario)].

        Pocos y repartidos: mañana, mediodía y tarde de cada día; 8 en total.
        """
        tipo = self._xb_sa_appt_type()
        if not tipo:
            return []
        tz = pytz.timezone(XB_TZ)
        referencia = datetime.utcnow()
        if desde and desde > referencia:
            referencia = desde
        meses = tipo._get_appointment_slots(XB_TZ, reference_date=referencia)
        por_dia = {}
        for mes in meses:
            for semana in mes["weeks"]:
                for dia in semana:
                    for hueco in dia.get("slots", []):
                        if not hueco.get("staff_user_id"):
                            continue
                        local = tz.localize(datetime.strptime(hueco["datetime"], "%Y-%m-%d %H:%M:%S"))
                        usuario = self.env["res.users"].browse(hueco["staff_user_id"])
                        por_dia.setdefault(local.date(), []).append((local.astimezone(pytz.utc), usuario))
        elegidos = []
        for dia in sorted(por_dia):
            del_dia = sorted(por_dia[dia], key=lambda x: x[0])
            elegidos += [del_dia[i] for i in sorted({0, len(del_dia) // 2, len(del_dia) - 1})]
        return elegidos[:8]

    def _xb_sa_appointment_url(self):
        tipo = self._xb_sa_appt_type()
        base = tipo.website_id.domain or tipo.get_base_url()
        return f"{base.rstrip('/')}/appointment/{tipo.id}"

    def _xb_sa_tool_ver_horarios_demo(self, job, entrada):
        tipo = self._xb_sa_appt_type()
        if not tipo:
            return {"ok": False, "motivo": "No hay una cita configurada para demos; registra el prospecto y pasa a humano."}
        desde = None
        if entrada.get("desde"):
            try:
                desde = pytz.timezone(XB_TZ).localize(datetime.strptime(entrada["desde"][:10], "%Y-%m-%d")) \
                    .astimezone(pytz.utc).replace(tzinfo=None)
            except ValueError:
                return {"ok": False, "motivo": "La fecha debe ir como AAAA-MM-DD."}
        tz = pytz.timezone(XB_TZ)
        libres = self._xb_sa_demo_slots(desde)
        return {"horarios": [f"{t.astimezone(tz):%Y-%m-%d %H:%M} ({XB_DIAS[t.astimezone(tz).weekday()]})" for t, _u in libres],
                "duracion_minutos": round(tipo.appointment_duration * 60),
                "se_puede_agendar_hasta_dias": tipo.max_schedule_days,
                # La cita de BNI no es pública: sin liga, el agente agenda por aquí.
                **({"liga_para_escoger_otro_horario": self._xb_sa_appointment_url()} if tipo.is_published else {})}

    def _xb_sa_tool_agendar_demo(self, job, entrada):
        acc = self.wa_account_id.sudo()
        tipo = self._xb_sa_appt_type()
        if not tipo:
            return {"ok": False, "motivo": "No hay una cita configurada para demos."}
        tz = pytz.timezone(XB_TZ)
        pedido = (entrada.get("inicio") or "")[:16]
        try:
            dia = tz.localize(datetime.strptime(pedido[:10], "%Y-%m-%d")).astimezone(pytz.utc).replace(tzinfo=None)
        except ValueError:
            return {"ok": False, "motivo": "El horario debe ir como AAAA-MM-DD HH:MM."}
        libres = self._xb_sa_demo_slots(dia)
        if not any(t.astimezone(tz).strftime("%Y-%m-%d %H:%M") == pedido for t, _u in libres):
            # Los 8 mostrados son una muestra: busca en todo el día pedido.
            libres = [x for x in self._xb_sa_day_slots(tipo, dia) if x[0].astimezone(tz).strftime("%Y-%m-%d %H:%M") == pedido]
        elegido = [(t, u) for t, u in libres if t.astimezone(tz).strftime("%Y-%m-%d %H:%M") == pedido]
        if not elegido:
            return {"ok": False, "motivo": "Ese horario ya no está libre; vuelve a consultar ver_horarios_demo."}
        inicio, usuario = elegido[0]
        ocupado = self.env["calendar.event"].sudo().search([
            ("user_id", "=", usuario.id), ("start", "<", inicio.replace(tzinfo=None) + timedelta(hours=tipo.appointment_duration)),
            ("stop", ">", inicio.replace(tzinfo=None))], limit=1)
        if ocupado:
            return {"ok": False, "motivo": "Ese horario ya no está libre; vuelve a consultar ver_horarios_demo."}
        nombre = entrada.get("nombre") or self.whatsapp_number
        cliente = self.whatsapp_partner_id.sudo()
        if not cliente:
            return {"ok": False, "motivo": "No se encontró el contacto de esta plática."}
        if entrada.get("correo") and not cliente.email:
            cliente.email = entrada["correo"]
        fin = inicio + timedelta(hours=tipo.appointment_duration)
        # La reserva debe llevar su línea de capacidad: sin ella, la app Citas no ve el horario como ocupado y lo vuelve a ofrecer.
        vals = tipo._prepare_calendar_event_values(
            1, [{"capacity_reserved": 1, "capacity_used": 1}], Markup(tools.plaintext2html(f"Agendada por el agente de WhatsApp.\nWhatsApp: {self.whatsapp_number}"
            + (f"\n\n{self.xb_sa_bni_notes}" if self.xb_sa_bni_notes else ""))),
            tipo.appointment_duration, False, self.env["appointment.invite"], None, nombre, cliente, usuario,
            inicio.replace(tzinfo=None), fin.replace(tzinfo=None))
        if self.xb_sa_lead_id:
            # Ya hay oportunidad: la cita se liga a ella en vez de crear otra.
            vals.update({"opportunity_id": self.xb_sa_lead_id.id,
                         "res_model_id": self.env["ir.model"]._get_id("crm.lead"),
                         "res_id": self.xb_sa_lead_id.id})
        evento = self.env["calendar.event"].with_context(
            mail_notify_author=True, mail_create_nolog=True, mail_create_nosubscribe=True,
            allowed_company_ids=usuario.company_ids.ids,
        ).sudo().create(vals)
        if not self.xb_sa_lead_id and evento.opportunity_id:
            self.sudo().xb_sa_lead_id = evento.opportunity_id
        self._xb_sa_fix_event(evento, tipo, nombre)
        if not evento.opportunity_id:  # con oportunidad, la app Citas ya le deja la actividad a quien da la demo
            self._xb_sa_notify(job, usuario, f"Demo agendada por WhatsApp: {pedido} con {nombre}")
        return {"ok": True, "cuando": pedido, "con": usuario.name, "duracion_minutos": round(tipo.appointment_duration * 60),
                "liga_videollamada": evento.videocall_location or "El equipo se la manda antes de la cita."}

    def _xb_sa_day_slots(self, tipo, dia):
        """Todos los huecos libres del día pedido (sin recortar a 8)."""
        tz = pytz.timezone(XB_TZ)
        salida = []
        for mes in tipo._get_appointment_slots(XB_TZ, reference_date=max(dia, datetime.utcnow())):
            for semana in mes["weeks"]:
                for d in semana:
                    for hueco in d.get("slots", []):
                        if hueco.get("staff_user_id"):
                            local = tz.localize(datetime.strptime(hueco["datetime"], "%Y-%m-%d %H:%M:%S"))
                            salida.append((local.astimezone(pytz.utc), self.env["res.users"].browse(hueco["staff_user_id"])))
        return salida
