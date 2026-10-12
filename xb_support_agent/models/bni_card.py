# -*- coding: utf-8 -*-
"""Tarjeta personalizada para un miembro de BNI: «3 cosas que XUBAX automatizaría en tu negocio».

Una imagen 1080×1350 hecha con un navegador sin pantalla a partir de una plantilla fija:
el agente solo aporta textos cortos (se escapan), nunca HTML.
"""
import io
import json
import os
import subprocess
import tempfile
from html import escape

from PIL import Image

from .screenshots import XB_CHROME, XB_PW_DIR, _sin_tope_de_memoria

XB_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "tarjeta.js")
XB_MAX_TEXT = 110

_PLANTILLA = """<!doctype html><meta charset="utf-8"><style>
*{{box-sizing:border-box}}
body{{margin:0;width:1080px;height:1350px;background:#1c1b1a;color:#f6f4f1;
font-family:"DejaVu Sans","Liberation Sans",Arial,sans-serif;padding:96px 88px 72px;display:flex;flex-direction:column}}
.k{{font-size:26px;letter-spacing:.16em;text-transform:uppercase;color:#ef6a55;font-weight:700}}
h1{{font-size:72px;line-height:1.08;margin:28px 0 60px;font-weight:700}}
ol{{list-style:none;margin:0;padding:0;display:grid;gap:56px;flex:1;align-content:center}}
li{{display:flex;gap:34px;font-size:48px;line-height:1.25}}
li i{{font-style:normal;color:#ef6a55;font-weight:700;font-size:84px;line-height:1;flex:none;width:60px}}
footer{{margin-top:auto;border-top:2px solid #3a3835;padding-top:28px;display:flex;justify-content:space-between;
font-size:28px;color:#a29b92}}
</style>
<div class="k">Para {persona} · {negocio}</div>
<h1>3 cosas que XUBAX automatizaría en tu negocio</h1>
<ol><li><i>1</i><span>{p1}</span></li><li><i>2</i><span>{p2}</span></li><li><i>3</i><span>{p3}</span></li></ol>
<footer><span>XUBAX</span><span>con Josette Salinas</span></footer>"""


def _t(texto, limite=XB_MAX_TEXT):
    texto = " ".join((texto or "").split())
    return escape(texto[:limite])


def tomar_tarjeta(persona, negocio, p1, p2, p3):
    """Devuelve los bytes JPEG de la tarjeta."""
    html = _PLANTILLA.format(persona=_t(persona, 40), negocio=_t(negocio, 50), p1=_t(p1), p2=_t(p2), p3=_t(p3))
    with tempfile.TemporaryDirectory(prefix="xb_tj_") as tmp:
        salida = os.path.join(tmp, "tarjeta.png")
        proc = subprocess.run(
            ["node", XB_SCRIPT], input=json.dumps({"html": html, "out": salida}).encode(),
            capture_output=True, timeout=60,
            env=dict(os.environ, NODE_PATH=f"{XB_PW_DIR}/node_modules", CHROME_PATH=XB_CHROME),
            preexec_fn=_sin_tope_de_memoria)
        try:
            res = json.loads(proc.stdout)
        except ValueError:
            res = {"error": (proc.stderr or proc.stdout or b"sin respuesta")[-300:].decode("utf-8", "replace")}
        if not res.get("ok"):
            raise ValueError(f"No se pudo dibujar la tarjeta: {res.get('error')}")
        buf = io.BytesIO()
        Image.open(salida).convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()
