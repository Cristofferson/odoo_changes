# -*- coding: utf-8 -*-
"""Puerta del agente de soporte de XUBAX en los servidores donde viven otras bases.

Se carga como módulo de servidor (``server_wide_modules``), así que NO hay que instalarlo en ninguna base.
Solo contesta a peticiones firmadas con HMAC-SHA256 (llave en /etc/xb_support_reader.key) y recientes; el
servidor de XUBAX llega aquí por un túnel SSH, no por internet. Las consultas son las de
``client_query`` (solo lectura, con los permisos de la persona que escribe).
"""
import hashlib
import hmac
import json
import logging
import re
import time
from types import SimpleNamespace

from odoo import http
from odoo.http import request
from odoo.service import db as db_service

from .. import client_query

_logger = logging.getLogger(__name__)

KEY_FILE = "/etc/xb_support_reader.key"
MAX_SKEW = 90          # segundos de diferencia de reloj tolerados
CONSULTAS = {"buscar_modelos", "describir_modelo", "consultar_registros", "resumir_registros",
             "historial_de_cambios"}


def _llave():
    with open(KEY_FILE, "rb") as f:
        return f.read().strip()


def _firma_ok(cuerpo, ts, firma):
    try:
        if abs(time.time() - int(ts)) > MAX_SKEW:
            return False
        esperado = hmac.new(_llave(), ts.encode() + b"." + hashlib.sha256(cuerpo).hexdigest().encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperado, firma or "")
    except Exception:  # noqa: BLE001 - cualquier falla = no autorizado
        return False


def _responder(datos, status=200):
    return request.make_response(json.dumps(datos, ensure_ascii=False, default=str),
                                 headers=[("Content-Type", "application/json")], status=status)


class XbSupportReader(http.Controller):

    @http.route("/xb_support_reader/call", type="http", auth="none", methods=["POST"], csrf=False,
                save_session=False)
    def call(self, **_kw):
        cuerpo = request.httprequest.get_data()
        if not _firma_ok(cuerpo, request.httprequest.headers.get("X-XB-Ts", ""),
                         request.httprequest.headers.get("X-XB-Sig", "")):
            return _responder({"ok": False, "error": "no autorizado"}, 403)
        try:
            datos = json.loads(cuerpo)
            op, dbname = datos.get("op"), datos.get("db")
            if op == "ping":
                return _responder({"ok": True, "result": {"bases": sorted(db_service.list_dbs(True))}})
            if not (isinstance(dbname, str) and re.fullmatch(r"[A-Za-z0-9_.\-]{1,63}", dbname)
                    and dbname in db_service.list_dbs(True)):
                return _responder({"ok": False, "error": "base desconocida"}, 404)
            if op == "usuarios_por_telefono":
                res = client_query.usuarios_por_telefono(dbname, datos["key"])
            elif op == "autorizadores":
                res = client_query.autorizadores(dbname)
            elif op == "errores_recientes":
                res = client_query.errores_recientes(dbname, datos.get("horas"))
            elif op == "consulta" and datos.get("fn") in CONSULTAS:
                c = datos["contacto"]
                contacto = SimpleNamespace(role=c["role"], can_billing=bool(c["can_billing"]),
                                           remote_user_id=int(c["remote_user_id"]))
                with client_query.client_env(dbname, contacto) as (env, rol):
                    res = getattr(client_query, datos["fn"])(env, rol, *datos.get("args", []))
            else:
                return _responder({"ok": False, "error": "operación desconocida"}, 400)
            return _responder({"ok": True, "result": res})
        except client_query.XbNoAgentUser:
            return _responder({"ok": False, "kind": "XbNoAgentUser", "error": "usuario no vigente"})
        except Exception as e:  # noqa: BLE001 - el error se le explica al agente
            _logger.warning("xb_support_reader: %s falló: %s", datos.get("op") if isinstance(datos, dict) else "?", e)
            return _responder({"ok": False, "kind": type(e).__name__, "error": str(e)[:500]})
