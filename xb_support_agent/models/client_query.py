# -*- coding: utf-8 -*-
"""Consultas libres, de solo lectura, al sistema (base de Odoo) de un cliente.

El agente entra al sistema del cliente como un usuario de Odoo hecho para eso
(«Agente IA XUBAX»), ARCHIVADO para que nadie pueda iniciar sesión con él ni
cuente como usuario. Así los límites los pone el propio Odoo: grupos, reglas de
registro y multiempresa. Ese usuario lo da de alta una PERSONA del equipo
(script ``xbsa_alta_usuario_agente.py``); este código nunca crea usuarios ni
da permisos.

Candados que no dependen del modelo de IA:
* la transacción es ``READ ONLY`` en Postgres y tiene tiempo máximo;
* solo se exponen funciones de lectura (search_read, formatted_read_group,
  fields_get, historial del chatter);
* solo la base del contacto autorizado, y solo si vive en este servidor;
* modelos y campos sensibles (llaves, contraseñas, binarios) nunca se devuelven;
* a un empleado sin permiso de dinero se le quitan modelos contables y montos.
"""
import json
import logging
import re
from contextlib import contextmanager
from datetime import datetime, timedelta

from odoo import api
from odoo.modules.registry import Registry
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)

XB_AUTH_GROUP = "Autoriza servicios XUBAX"  # grupo que crea a mano el cliente o XUBAX en Ajustes › Usuarios › Grupos
XB_TIMEOUT_MS = 10000
XB_MAX_ROWS = 50
XB_MAX_CHARS = 14000
XB_TEXT_CHARS = 300
XB_LOG = "/var/log/odoo/odoo-server.log"
# Nunca, ni para el titular.
XB_DENY_MODELS = ("ir.config_parameter", "res.users.apikeys", "res.users.identitycheck", "auth_totp",
                  "ir.mail_server", "fetchmail.server", "payment.provider", "res.users.settings",
                  "iap.account", "ir.actions.server", "base.automation", "ir.ui.view")
XB_DENY_FIELDS = re.compile(r"(password|passwd|token|secret|api_?key|signature|totp|private_key|_key$)", re.I)
# Empleado sin permiso de dinero.
XB_MONEY_MODELS = ("account.", "hr.payslip", "hr.contract", "hr.expense", "hr.salary")
XB_MONEY_FIELDS = re.compile(
    r"(price|amount|cost|total|margin|balance|debit|credit|salary|wage|tax|discount|residual|cash|payment|paid)", re.I)


class XbNoAgentUser(Exception):
    """El usuario ligado al número ya no existe, está archivado o no es interno."""


def _rol(contacto):
    return "owner" if contacto.role == "owner" and contacto.can_billing else "employee"


def usuarios_por_telefono(dbname, key):
    """Usuarios internos y activos del sistema cuyo teléfono termina en ``key``
    (10 dígitos). Solo lectura. ``autoriza`` = está en el grupo «Autoriza servicios XUBAX»."""
    from .support_contact import xb_phone_key
    with Registry(dbname).cursor() as cr:
        cr.execute("SET TRANSACTION READ ONLY")
        cr.execute("SET LOCAL statement_timeout = %s", (XB_TIMEOUT_MS,))
        env = api.Environment(cr, 1, {})
        grupo = env["res.groups"].search([("name", "=", XB_AUTH_GROUP)], limit=1)
        salida = []
        for u in env["res.users"].search([("share", "=", False), ("active", "=", True)]):
            if xb_phone_key(u.partner_id.phone) == key:
                salida.append({"id": u.id, "login": u.login, "name": u.name,
                               "autoriza": bool(grupo and grupo in u.group_ids)})
        cr.rollback()
        return salida


def autorizadores(dbname):
    """[(nombre, correo)] de quienes autorizan servicios en ese sistema."""
    with Registry(dbname).cursor() as cr:
        cr.execute("SET TRANSACTION READ ONLY")
        env = api.Environment(cr, 1, {})
        grupo = env["res.groups"].search([("name", "=", XB_AUTH_GROUP)], limit=1)
        gente = [(u.name, u.email or u.login) for u in (grupo.user_ids if grupo else [])
                 if u.active and not u.share]
        cr.rollback()
        return gente


def usuario_vigente(cr, uid):
    cr.execute("SELECT 1 FROM res_users WHERE id = %s AND active AND NOT share", (uid,))
    if not cr.fetchone():
        raise XbNoAgentUser(cr.dbname)


@contextmanager
def client_env(dbname, contacto):
    """Ambiente de Odoo en la base del cliente COMO LA PERSONA que escribe, en solo lectura:
    ve lo mismo que ella (grupos, reglas de registro y multiempresa del propio Odoo)."""
    rol = _rol(contacto)
    uid = contacto.remote_user_id
    registry = Registry(dbname)
    with registry.cursor() as cr:
        cr.execute("SET TRANSACTION READ ONLY")
        cr.execute("SET LOCAL statement_timeout = %s", (XB_TIMEOUT_MS,))
        usuario_vigente(cr, uid)
        env = api.Environment(cr, uid, {"lang": "es_MX", "tz": "America/Mexico_City"})
        env = env(context=dict(env.context, allowed_company_ids=env.user.company_ids.ids))
        try:
            yield env, rol
        finally:
            cr.rollback()


def _check_model(env, rol, modelo):
    if modelo not in env:
        raise ValueError(f"No existe el modelo {modelo!r} en este sistema. Usa buscar_modelos.")
    if modelo.startswith(XB_DENY_MODELS) or env[modelo]._abstract:
        raise ValueError(f"El modelo {modelo} no se puede consultar.")
    if rol == "employee" and modelo.startswith(XB_MONEY_MODELS):
        raise ValueError("Este contacto no tiene permiso de ver información de dinero.")
    return env[modelo]


def _allowed_field(model, nombre, rol):
    campo = model._fields.get(nombre)
    if not campo or XB_DENY_FIELDS.search(nombre) or campo.type == "binary":
        return False
    if rol == "employee" and (campo.type == "monetary" or (campo.type == "float" and XB_MONEY_FIELDS.search(nombre))):
        return False
    return True


def _clean(model, valores):
    salida = {}
    for k, v in valores.items():
        campo = model._fields.get(k)
        if campo is not None and campo.type == "html" and v:
            v = html2plaintext(v)
        if isinstance(v, str) and len(v) > XB_TEXT_CHARS:
            v = v[:XB_TEXT_CHARS] + "…"
        elif isinstance(v, (list, tuple)) and campo is not None and campo.type == "many2one" and v:
            v = f"{v[1]} (id {v[0]})"
        elif isinstance(v, list) and len(v) > 10:
            v = v[:10] + [f"… y {len(v) - 10} más"]
        salida[k] = v
    return salida


def _dump(datos):
    texto = json.dumps(datos, ensure_ascii=False, default=str)
    if len(texto) > XB_MAX_CHARS:
        texto = texto[:XB_MAX_CHARS] + " …[recortado: pide menos campos o un filtro más estrecho]"
    return texto


def _domain(texto):
    texto = (texto or "").strip()
    if not texto:
        return []
    try:
        dominio = json.loads(texto)
    except ValueError:
        raise ValueError('El filtro debe ser JSON, por ejemplo [["state", "=", "sale"]]')
    if not isinstance(dominio, list):
        raise ValueError("El filtro debe ser una lista.")
    return dominio


def buscar_modelos(env, rol, texto):
    texto = (texto or "").strip()
    dominio = ["|", ("model", "ilike", texto), ("name", "ilike", texto)] if texto else []
    # sudo: solo nombres de modelos (metadatos), no datos.
    modelos = env["ir.model"].sudo().search(dominio + [("transient", "=", False)], limit=25, order="model")
    return _dump([{"modelo": m.model, "nombre": m.name} for m in modelos
                  if m.model in env and not m.model.startswith(XB_DENY_MODELS)
                  and not (rol == "employee" and m.model.startswith(XB_MONEY_MODELS))])


def describir_modelo(env, rol, modelo, texto):
    model = _check_model(env, rol, modelo)
    model.check_access("read")
    texto = (texto or "").lower()
    campos = model.fields_get(attributes=["string", "type", "relation", "store", "selection"])
    salida = []
    for nombre, info in sorted(campos.items()):
        if not _allowed_field(model, nombre, rol):
            continue
        if texto and texto not in nombre.lower() and texto not in (info.get("string") or "").lower():
            continue
        d = {"campo": nombre, "etiqueta": info.get("string"), "tipo": info.get("type")}
        if info.get("relation"):
            d["relacion"] = info["relation"]
        if info.get("selection"):
            d["opciones"] = [s[0] for s in info["selection"]][:12]
        if not info.get("store"):
            d["no_guardado"] = True
        salida.append(d)
    return _dump(salida[:120])


def consultar_registros(env, rol, modelo, dominio, campos, orden, limite):
    model = _check_model(env, rol, modelo)
    campos = [c for c in (campos or []) if _allowed_field(model, c, rol)] or ["display_name"]
    limite = max(1, min(int(limite or 20), XB_MAX_ROWS))
    filtro = _domain(dominio)
    filas = model.search_read(filtro, campos, order=orden or None, limit=limite)
    return _dump({"total_que_cumplen": model.search_count(filtro), "mostrando": len(filas),
                  "registros": [_clean(model, f) for f in filas]})


def resumir_registros(env, rol, modelo, dominio, agrupar_por, totales, orden, limite):
    model = _check_model(env, rol, modelo)
    agrupar_por = [g for g in (agrupar_por or []) if _allowed_field(model, g.split(":")[0], rol)]
    totales = [t for t in (totales or []) if _allowed_field(model, t.split(":")[0], rol)]
    grupos = model.formatted_read_group(
        _domain(dominio), groupby=agrupar_por, aggregates=["__count", *totales],
        order=orden or None, limit=max(1, min(int(limite or 30), 100)))
    salida = []
    for g in grupos:
        fila = {}
        for k, v in g.items():
            if k.startswith("__") and k != "__count":
                continue
            if isinstance(v, (list, tuple)) and len(v) == 2:
                v = v[1]
            fila["registros" if k == "__count" else k] = v
        salida.append(fila)
    return _dump(salida)


def historial_de_cambios(env, rol, modelo, registro_id):
    model = _check_model(env, rol, modelo)
    registro = model.browse(int(registro_id)).exists()
    if not registro:
        return "No existe ese registro (o este contacto no puede verlo)."
    registro.check_access("read")
    mensajes = env["mail.message"].search(
        [("model", "=", modelo), ("res_id", "=", registro.id)], order="id desc", limit=25)
    salida = []
    for m in mensajes:
        d = {"fecha": str(m.date), "autor": m.author_id.name or "", "tipo": m.message_type}
        cuerpo = html2plaintext(m.body or "").strip()
        if cuerpo:
            d["texto"] = cuerpo[:XB_TEXT_CHARS]
        cambios = []
        # sudo: los valores de seguimiento de un registro que ya se comprobó que puede leer.
        for t in m.sudo().tracking_value_ids:
            if t.field_id.name and not _allowed_field(model, t.field_id.name, rol):
                continue
            cambios.append(f"{t.field_id.field_description}: {t._format_display_value(t.field_id.ttype, new=False)}"
                           f" → {t._format_display_value(t.field_id.ttype, new=True)}")
        if cambios:
            d["cambios"] = cambios
        salida.append(d)
    return _dump({"registro": registro.display_name, "creado": str(registro.create_date),
                  "creado_por": registro.create_uid.name, "historial": salida})


def errores_recientes(dbname, horas):
    """Errores del servidor de esa base (bitácora de Odoo), los más recientes."""
    horas = max(1, min(int(horas or 24), 168))
    desde = (datetime.utcnow() - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
    marca = f" {dbname} "
    errores, actual = [], None
    try:
        with open(XB_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 40 * 1024 * 1024))
            for crudo in f:
                linea = crudo.decode("utf-8", "replace").rstrip()
                if re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", linea):
                    actual = None
                    if linea[:19] >= desde and marca in linea and (" ERROR " in linea or " CRITICAL " in linea):
                        actual = [linea[:400]]
                        errores.append(actual)
                elif actual is not None and len(actual) < 14:
                    actual.append(linea[:300])
    except OSError as e:
        return f"No se pudo leer la bitácora: {e}"
    if not errores:
        return f"Sin errores de servidor en esa base en las últimas {horas} horas."
    return _dump({"errores": len(errores), "ultimos": ["\n".join(e) for e in errores[-8:]]})
