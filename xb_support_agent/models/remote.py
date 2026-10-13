# -*- coding: utf-8 -*-
"""Consultas al sistema de un cliente que vive en OTRO servidor (Odoo 18 u OVH 4).

El servidor remoto corre el módulo ``xb_support_reader`` (módulo de servidor, sin instalar en ninguna base) que
contesta peticiones firmadas con HMAC. Se llega a él por un túnel SSH a localhost. La dirección y la llave de
cada servidor están en el parámetro del sistema ``xb_support_agent.remote.<servidor>`` con el formato
``http://127.0.0.1:PUERTO|LLAVE``.
"""
import hashlib
import hmac
import json
import logging
import time

import requests

_logger = logging.getLogger(__name__)
XB_REMOTE_TIMEOUT = 25


class XbRemoteError(Exception):
    pass


def _cfg(env, servidor):
    valor = env["ir.config_parameter"].sudo().get_param(f"xb_support_agent.remote.{servidor}") or ""
    if "|" not in valor:
        return None
    url, llave = valor.split("|", 1)
    return url.strip().rstrip("/"), llave.strip().encode()


def configurado(env, servidor):
    return bool(_cfg(env, servidor))


def llamar(env, servidor, op, **datos):
    """Devuelve el ``result`` del servidor remoto. Lanza XbRemoteError o, si el usuario ya no está vigente,
    client_query.XbNoAgentUser."""
    from . import client_query
    cfg = _cfg(env, servidor)
    if not cfg:
        raise XbRemoteError(f"El servidor {servidor} no está configurado para el agente.")
    url, llave = cfg
    cuerpo = json.dumps(dict(datos, op=op), ensure_ascii=False, default=str).encode()
    ts = str(int(time.time()))
    firma = hmac.new(llave, ts.encode() + b"." + hashlib.sha256(cuerpo).hexdigest().encode(), hashlib.sha256).hexdigest()
    try:
        r = requests.post(f"{url}/xb_support_reader/call", data=cuerpo, timeout=XB_REMOTE_TIMEOUT,
                          headers={"Content-Type": "application/json", "X-XB-Ts": ts, "X-XB-Sig": firma})
        resp = r.json()
    except (requests.RequestException, ValueError) as e:
        raise XbRemoteError(f"No se pudo hablar con el servidor {servidor}: {e}") from e
    if resp.get("ok"):
        return resp["result"]
    if resp.get("kind") == "XbNoAgentUser":
        raise client_query.XbNoAgentUser(datos.get("db"))
    if resp.get("kind") == "ValueError":
        raise ValueError(resp.get("error"))
    raise XbRemoteError(resp.get("error") or "error desconocido")
