# -*- coding: utf-8 -*-
"""Capturas reales del sistema del cliente para mandarlas por WhatsApp.

El agente NO navega libremente: dice qué menú quiere ver (y, si acaso, un
registro y un texto a resaltar). Aquí se valida que ese menú abra una VISTA
(``ir.actions.act_window``; nunca acciones de servidor ni pantallas que hagan
algo al abrirse, como la caja) y luego un navegador sin pantalla entra con el
magic-link de ``despacho_autologin`` de ESA base, toma la foto y cierra sesión.
Para cualquier persona autorizada y confirmada del sistema (el titular ve todo; empleados e invitados, sin pantallas de dinero); la captura se toma con la sesión del titular.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import resource
import subprocess
import tempfile
import time
import uuid

from PIL import Image

from . import client_query

XB_PW_DIR = "/opt/xb_playwright"
XB_CHROME = f"{XB_PW_DIR}/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell"
XB_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "captura.js")
XB_BASE = "http://127.0.0.1:8069"
XB_TIMEOUT = 90


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _token(secret, uid):
    payload = _b64(json.dumps({"exp": int(time.time()) + 120, "nonce": uuid.uuid4().hex, "uid": uid}).encode())
    firma = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{firma}"


def _sin_tope_de_memoria():
    """El worker de Odoo limita su memoria virtual (limit_memory_hard) y el hijo
    lo hereda: Node y Chromium reservan mucha memoria virtual y truenan."""
    _suave, duro = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (duro, duro))


def _resolver(env, menu, registro_id, sin_dinero=False):
    """(url, título) de la vista pedida, o error. Solo vistas (act_window)."""
    Menus = env["ir.ui.menu"]
    partes = [p.strip() for p in (menu or "").replace(">", "/").split("/") if p.strip()]
    if not partes:
        raise ValueError("Indica el menú, p. ej. «Punto de venta» o «Punto de venta / Pedidos / Sesiones».")
    candidatos = Menus.search([("name", "ilike", partes[-1])], limit=40)
    if len(partes) > 1:
        candidatos = candidatos.filtered(
            lambda m: all(p.lower() in (m.complete_name or "").lower() for p in partes))
    if not candidatos:
        app = Menus.search([("parent_id", "=", False), ("name", "ilike", partes[0])], limit=1)
        opciones = Menus.search([("id", "child_of", app.ids), ("action", "!=", False)], limit=40) if app else Menus
        raise ValueError(f"No encontré el menú «{menu}». Menús que sí hay: "
                         + ("; ".join(opciones.mapped("complete_name")) or "ninguno con ese inicio"))
    for m in candidatos.sorted(lambda m: len(m.complete_name or "")):
        pila = m
        while pila:
            for x in pila:
                accion = x.action
                if accion and accion._name == "ir.actions.act_window":
                    if sin_dinero and accion.res_model.startswith(client_query.XB_MONEY_MODELS):
                        raise ValueError("Esa pantalla es de dinero (contabilidad, nómina); no se le manda a un invitado.")
                    url = f"/odoo/action-{accion.id}"
                    if registro_id:
                        registro = env[accion.res_model].browse(int(registro_id)).exists()
                        if not registro:
                            raise ValueError(f"No existe el registro {registro_id} en «{x.complete_name}».")
                        url += f"/{registro.id}"
                    return url, x.complete_name
            pila = pila.child_id.sorted("sequence")
    raise ValueError(f"El menú «{menu}» no abre una pantalla que se pueda fotografiar.")


def tomar_captura(dbname, contacto, menu, registro_id, resaltar):
    """Devuelve (jpeg_bytes, título, resaltado)."""
    with client_query.client_env(dbname, contacto) as (env, _rol):
        url, titulo = _resolver(env, menu, registro_id, sin_dinero=client_query._rol(contacto) != "owner")
        env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'despacho_autologin.secret'")
        fila = env.cr.fetchone()
    if not fila or not fila[0]:
        raise ValueError("Este sistema no tiene el acceso de capturas configurado.")
    with tempfile.TemporaryDirectory(prefix="xb_cap_") as tmp:
        salida = os.path.join(tmp, "captura.png")
        datos = json.dumps({"base": XB_BASE, "db": dbname, "token": _token(fila[0], contacto.remote_user_id), "url": url,
                            "resaltar": (resaltar or "").strip()[:80], "out": salida})
        proc = subprocess.run(
            ["node", XB_SCRIPT], input=datos.encode(), capture_output=True, timeout=XB_TIMEOUT,
            env=dict(os.environ, NODE_PATH=f"{XB_PW_DIR}/node_modules", CHROME_PATH=XB_CHROME),
            preexec_fn=_sin_tope_de_memoria)
        try:
            res = json.loads(proc.stdout)
        except ValueError:
            res = {"error": (proc.stderr or proc.stdout or b"sin respuesta")[-300:].decode("utf-8", "replace")}
        if not res.get("ok"):
            raise ValueError(f"No se pudo tomar la captura: {res.get('error')}")
        img = Image.open(salida).convert("RGB")
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85, optimize=True)
    return buf.getvalue(), titulo, res.get("resaltado")
