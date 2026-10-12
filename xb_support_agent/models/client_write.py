# -*- coding: utf-8 -*-
"""Cambios en el sistema del cliente que él PAGA y AUTORIZA (servicio de escritura).

Consultar y explicar es gratis; hacer el cambio por el cliente se cobra como
tiempo de servicio. El agente arma un plan de operaciones, aquí se valida y se
ensaya (en una transacción que se deshace) para enseñarle al cliente el
resultado y el precio; solo con su «SÍ» se aplica de verdad.

Candados en código:
* solo modelos y operaciones de la lista blanca (lo sencillo); lo demás lo hace
  una persona del equipo;
* nunca borrar, nunca contabilidad, nunca precios de producto ni estados;
* entra como la PERSONA que autorizó (su usuario real de Odoo, ligado por su
  teléfono): hereda SUS permisos y todo cambio queda a su nombre.
"""
import json
import logging
import re

from odoo import api
from odoo.modules.registry import Registry

from .client_query import XB_DENY_FIELDS, XbNoAgentUser, usuario_vigente

_logger = logging.getLogger(__name__)

# modelo → campos que NO se tocan aunque el modelo esté permitido
XB_SAFE_MODELS = {
    "res.partner": {"company_id", "user_ids", "active"},
    "sale.order": {"state", "company_id", "locked", "invoice_status", "amount_total"},
    "sale.order.line": {"company_id", "state", "invoice_status", "qty_invoiced"},
    "crm.lead": {"company_id", "active"},
    "project.task": {"company_id", "active"},
    "calendar.event": {"active"},
}
# Además, en cualquier modelo: nada de contabilidad ni campos de sistema.
XB_DENY_ANY = {"id", "create_uid", "create_date", "write_uid", "write_date", "message_ids",
               "message_follower_ids", "activity_ids", "access_token"}
XB_REF = re.compile(r"^\$(\d+)$")


class XbServiceRefused(Exception):
    """El plan pide algo que la IA no hace sola: lo hace el equipo."""


def _check_vals(model, vals, prohibidos, ruta, creando=False):
    if not isinstance(vals, dict):
        raise XbServiceRefused(f"{ruta}: los valores deben ser un objeto JSON.")
    for campo, valor in vals.items():
        f = model._fields.get(campo)
        if not f:
            raise ValueError(f"{ruta}: el modelo {model._name} no tiene el campo {campo!r}.")
        if (creando and campo == "company_id" and valor in model.env.user.company_ids.ids):
            continue  # al CREAR se puede elegir una de las empresas del propio usuario
        if (campo in prohibidos or campo in XB_DENY_ANY or XB_DENY_FIELDS.search(campo)
                or (f.compute and not f.inverse and f.readonly)):
            raise XbServiceRefused(f"{ruta}: el campo {campo} no lo cambia la IA.")
        if f.type in ("one2many", "many2many") and isinstance(valor, list):
            sub = model.env[f.comodel_name]
            for cmd in valor:
                if isinstance(cmd, (list, tuple)) and cmd and cmd[0] in (2, 3, 5):
                    raise XbServiceRefused(f"{ruta}: la IA no quita ni borra registros relacionados.")
                if isinstance(cmd, (list, tuple)) and len(cmd) == 3 and cmd[0] in (0, 1):
                    if f.comodel_name not in XB_SAFE_MODELS:
                        raise XbServiceRefused(f"{ruta}: {f.comodel_name} lo hace el equipo.")
                    _check_vals(sub, cmd[2], XB_SAFE_MODELS[f.comodel_name], f"{ruta}.{campo}")


def _resolve(valor, creados):
    """Sustituye «$1», «$2»… por el id del registro creado en esa operación."""
    if isinstance(valor, str) and XB_REF.match(valor):
        n = int(XB_REF.match(valor).group(1))
        if n not in creados:
            raise ValueError(f"La referencia {valor} apunta a una operación que no crea nada.")
        return creados[n]
    if isinstance(valor, list):
        return [_resolve(v, creados) for v in valor]
    if isinstance(valor, tuple):
        return tuple(_resolve(v, creados) for v in valor)
    if isinstance(valor, dict):
        return {k: _resolve(v, creados) for k, v in valor.items()}
    return valor


def parse_plan(texto):
    try:
        plan = json.loads(texto or "[]")
    except ValueError:
        raise ValueError("Las operaciones deben ser una lista JSON.")
    if not isinstance(plan, list) or not plan:
        raise ValueError("Indica al menos una operación.")
    if len(plan) > 10:
        raise XbServiceRefused("Son demasiadas operaciones para la IA: lo hace el equipo.")
    return plan


def _apply(env, plan):
    """Aplica el plan en ``env``. Devuelve el resumen de lo hecho."""
    creados, hechos = {}, []
    for n, op in enumerate(plan, 1):
        accion, modelo = op.get("accion"), op.get("modelo")
        if accion not in ("crear", "modificar"):
            raise XbServiceRefused(f"Operación {n}: la IA solo crea o modifica; «{accion}» lo hace el equipo.")
        if modelo not in XB_SAFE_MODELS or modelo not in env:
            raise XbServiceRefused(f"Operación {n}: {modelo} lo hace el equipo.")
        model = env[modelo]
        vals = _resolve(op.get("valores") or {}, creados)
        _check_vals(model, vals, XB_SAFE_MODELS[modelo], f"Operación {n}", creando=accion == "crear")
        if accion == "crear":
            if vals.get("company_id"):
                model = model.with_company(vals["company_id"])
            rec = model.create(vals)
            creados[n] = rec.id
        else:
            rec = model.browse(int(_resolve(op.get("registro_id"), creados) or 0)).exists()
            if not rec:
                raise ValueError(f"Operación {n}: no existe el registro {op.get('registro_id')} de {modelo}.")
            if modelo == "sale.order" and rec.state not in ("draft", "sent"):
                raise XbServiceRefused(f"Operación {n}: {rec.name} ya está confirmada; cambiarla lo hace el equipo.")
            rec.write(vals)
        env.flush_all()
        d = {"operacion": n, "accion": accion, "modelo": modelo, "id": rec.id, "nombre": rec.display_name}
        if "amount_total" in rec._fields:
            d["total"] = rec.amount_total
        hechos.append(d)
    return hechos


def _service_env(cr, uid):
    usuario_vigente(cr, uid)
    env = api.Environment(cr, uid, {"lang": "es_MX", "tz": "America/Mexico_City", "tracking_disable": False})
    return env(context=dict(env.context, allowed_company_ids=env.user.company_ids.ids))


def ensayar(dbname, uid, plan):
    """Aplica el plan y lo DESHACE: sirve para validar y enseñar el resultado."""
    with Registry(dbname).cursor() as cr:
        try:
            cr.execute("SET LOCAL statement_timeout = 15000")
            return _apply(_service_env(cr, uid), plan)
        finally:
            cr.rollback()


def ejecutar(dbname, uid, plan, nota):
    """Aplica el plan de verdad (con el usuario que lo autorizó) y deja una nota en cada registro."""
    with Registry(dbname).cursor() as cr:
        cr.execute("SET LOCAL statement_timeout = 30000")
        env = _service_env(cr, uid)
        hechos = _apply(env, plan)
        for h in hechos:
            rec = env[h["modelo"]].browse(h["id"])
            if hasattr(rec, "message_post"):
                rec.message_post(body=nota, message_type="comment", subtype_xmlid="mail.mt_note")
        cr.commit()
        return hechos
