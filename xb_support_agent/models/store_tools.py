# -*- coding: utf-8 -*-
"""Perfil «tienda» del agente (Anello): atiende a clientes de una joyería.

Catálogo público, cotizaciones con su ticket, pedidos y estado de pedidos. El equipo
(personas de la cuenta reconocidas por su teléfono) además puede generar pedidos.
"""
import base64
import io
import re
import unicodedata
from datetime import datetime, timedelta

import pytz
from markupsafe import Markup
from PIL import Image

from odoo import api, fields, models, tools

from .discuss_channel import XB_DIAS, XB_TOOLS, XB_TZ, _tool
from .support_contact import xb_phone_key

XB_STORE_STATES = {
    "draft": "cotización en borrador",
    "sent": "cotización enviada",
    "sale": "pedido confirmado",
    "cancel": "cancelado",
}

# Herramientas de XB_TOOLS que sí sirven en la tienda (el resto es de soporte de XUBAX).
XB_STORE_KEEP = {"pasar_a_humano", "registrar_prospecto", "ver_horarios_demo", "agendar_demo"}
# Solo si quien escribe es del equipo y tiene un sistema ligado (consulta de Odoo de solo lectura).
XB_STORE_TEAM_KEEP = {"seleccionar_sistema", "buscar_modelos", "describir_modelo", "consultar_registros",
                      "resumir_registros", "historial_de_cambios", "enviar_captura"}

XB_STORE_TOOLS = [
    _tool("buscar_productos",
          "Busca joyas en el catálogo PÚBLICO de la tienda (las publicadas en el sitio) por palabras del nombre, categoría y ETIQUETAS "
          "(estilo: Promesa, Solitario, Vintage, Pavé, Halo, Eternity, Catedral, Tensión…; forma de piedra; una o varias piedras). "
          "Si el cliente pide un estilo, busca por su etiqueta antes de decir que no hay. Devuelve nombre, categoría, "
          "precio «desde» de referencia y la liga a su ficha. Los anillos se fabrican a la medida: el precio final "
          "depende del metal, ancho y medida y se confirma en la cotización.",
          {"texto": {"type": "string", "description": "Palabras del nombre o referencia, p. ej. «solitario», «argolla mate»; vacío = no filtrar por nombre."},
           "categoria": {"type": "string", "description": "Palabra de la categoría (anillo, arete, dije, pulsera, argolla…); vacío = todas."},
           "etiquetas": {"type": "array", "items": {"type": "string"},
                         "description": "Etiquetas del catálogo (estilo, forma de piedra, piedras), p. ej. [\"Promesa\"], [\"Solitario\",\"Redondo\"]; "
                                        "deben cumplirse todas. Lista vacía = sin filtrar. Las disponibles vienen en cada respuesta."},
           "precio_max": {"type": "number", "description": "Precio máximo CON IVA de referencia; 0 = sin tope."},
           "limite": {"type": "integer", "description": "Cuántos mostrar (máx. 8)."}}),
    _tool("ver_producto",
          "Ficha de una joya: descripción, opciones disponibles (metal, ancho, medida, piedra…) con sus nombres exactos, "
          "precio «desde» y liga. Úsala antes de cotizar para conocer las opciones.",
          {"producto_id": {"type": "integer"}}),
    _tool("crear_cotizacion",
          "Crea una COTIZACIÓN (borrador, no es un pedido) con una o más joyas y su ticket queda listo para enviarse con "
          "enviar_ticket. Cada línea lleva el id del producto, la cantidad y las opciones elegidas con el nombre EXACTO "
          "que devolvió ver_producto (metal, ancho, medida…). Si falta alguna opción, no la inventes: pregúntasela al cliente. "
          "Para clientes: se cotiza a su propio nombre. El equipo puede cotizar a nombre de otra persona con su celular.",
          {"lineas": {"type": "array", "items": {"type": "object", "properties": {
              "producto_id": {"type": "integer"},
              "cantidad": {"type": "number"},
              "opciones": {"type": "array", "items": {"type": "string"},
                           "description": "Nombres exactos de las opciones elegidas, p. ej. [\"Oro amarillo 14kt\",\"4mm\",\"7.5\"]."},
              "nota": {"type": "string", "description": "Grabado, mensaje o indicación especial; vacío si no hay."}},
              "required": ["producto_id", "cantidad", "opciones", "nota"]}},
           "cliente_nombre": {"type": "string", "description": "Solo equipo: nombre de a quién se cotiza; vacío = quien escribe."},
           "cliente_celular": {"type": "string", "description": "Solo equipo: celular de 10 dígitos; vacío = quien escribe."}}),
    _tool("enviar_foto_producto",
          "Manda por WhatsApp la FOTO de una joya del catálogo (va antes de tu texto). Úsala al recomendar piezas: máximo "
          "3 fotos por respuesta, las que más le interesen.",
          {"producto_id": {"type": "integer"},
           "pie": {"type": "string", "description": "Una línea con el nombre y el precio «desde»; vacío = solo el nombre."}}),
    _tool("ver_pedidos",
          "Pedidos y cotizaciones. A un cliente le muestra los SUYOS (estado, total, saldo pendiente, fecha de entrega, "
          "si ya está listo). El equipo puede buscar por número (S00123), nombre o celular de cualquiera.",
          {"buscar": {"type": "string", "description": "Solo equipo: número, nombre o celular; vacío = los de quien escribe."}}),
    _tool("enviar_ticket",
          "Manda por WhatsApp el TICKET (imagen) de una cotización o pedido, con su QR para revisarlo o pagarlo en línea. "
          "Va antes de tu texto. Un cliente solo puede pedir los suyos.",
          {"pedido": {"type": "string", "description": "Número, p. ej. S00369."}}),
    _tool("generar_pedido",
          "Confirma una cotización y la vuelve PEDIDO. Solo el equipo de la tienda puede hacerlo, y solo después de que la "
          "persona del equipo lo pida de forma explícita. Si lo pide un cliente, avisa a la tienda para que lo confirme "
          "(queda en espera, no se confirma solo).",
          {"pedido": {"type": "string", "description": "Número de la cotización."}}),
]
for _t in XB_STORE_TOOLS:
    _t.pop("strict", None)


def _plano(texto):
    """Minúsculas sin acentos, para comparar nombres de opciones."""
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    # ------------------------------------------------------------------
    # Perfil y contexto
    # ------------------------------------------------------------------
    def _xb_sa_store_team(self):
        """Persona del equipo de la tienda dueña de este teléfono (usuarios de la cuenta o del equipo de XUBAX)."""
        self.ensure_one()
        acc = self.wa_account_id.sudo()
        llave = xb_phone_key(self.whatsapp_number)
        if not llave:
            return self.env["res.users"]
        usuarios = acc.xb_sa_support_user_ids | acc.xb_sa_sales_user_ids | acc.xb_sa_demo_user_ids
        usuarios |= self.env["res.users"].sudo().browse(
            [int(x) for x in re.findall(r"\d+", self.env["ir.config_parameter"].sudo().get_param(
                "xb_support_agent.team_user_ids") or "")])
        return usuarios.filtered(
            lambda u: u.active and not u.share and xb_phone_key(u.partner_id.phone) == llave)[:1]

    def _xb_sa_store_tools(self, contactos):
        herramientas = [t for t in XB_TOOLS if t["name"] in XB_STORE_KEEP] + XB_STORE_TOOLS
        if contactos and self._xb_sa_store_team():
            herramientas += [t for t in XB_TOOLS if t["name"] in XB_STORE_TEAM_KEEP]
        return herramientas

    def _xb_sa_store_context(self, contactos, contacto, proyecto):
        acc = self.wa_account_id.sudo()
        ahora = datetime.now(pytz.timezone(XB_TZ))
        lineas = [f"Contexto (lo escribe el sistema, no el cliente). Fecha y hora en Ciudad de México: "
                  f"{XB_DIAS[ahora.weekday()]} {ahora:%d/%m/%Y %H:%M}."]
        equipo = self._xb_sa_store_team()
        partner = self.whatsapp_partner_id.sudo()
        if equipo:
            lineas.append(
                f"Quien escribe es del EQUIPO de la tienda: {equipo.name} (reconocida por su teléfono). Trátala de tú, directo. "
                "Puede pedirte buscar piezas, crear cotizaciones a nombre de un cliente (con su celular), mandar el ticket, "
                "ver pedidos de cualquiera y generar pedidos (generar_pedido, solo cuando lo pida de forma explícita). "
                "Si pide datos de Odoo (ventas, existencias, clientes), usa las herramientas de consulta.")
            if contactos:
                for c in contactos:
                    lineas.append(f"- Sistema {c.project_id.name} (base {c.database_name}), "
                                  f"{'ve dinero' if c.can_billing else 'sin temas de dinero'}.")
                if proyecto:
                    lineas.append(f"Sistema de esta plática: «{proyecto.name}».")
        else:
            lineas.append("Quien escribe es un CLIENTE o prospecto de la tienda (no del equipo). No le des datos de otras personas "
                          "ni información interna. Solo ve sus propios pedidos.")
        if partner:
            lineas.append(f"En nuestra base figura como «{partner.name}»: salúdale por su nombre.")
            pedidos = self.env["sale.order"].sudo().search([
                ("partner_id", "child_of", partner.commercial_partner_id.id),
                ("company_id", "=", acc._xb_sa_company().id), ("state", "!=", "cancel")], order="id desc", limit=5)
            if pedidos:
                lineas.append("Sus últimos pedidos/cotizaciones: " + "; ".join(
                    f"{p.name} ({XB_STORE_STATES.get(p.state, p.state)}, ${p.amount_total:,.2f})" for p in pedidos) + ".")
        if self.xb_sa_lead_id:
            lineas.append(f"Ya hay un registro en el CRM para esta plática: «{self.xb_sa_lead_id.name}».")
        if (self.xb_sa_pause_reason == "handoff" and not self.xb_sa_paused_until and self.xb_sa_hold_dt
                and self.xb_sa_hold_dt > fields.Datetime.now() - timedelta(hours=48)):
            lineas.append("YA SE AVISÓ a una persona de la tienda sobre esta plática y ella contestará lo pendiente. NO te quedes "
                          "callado: sigue contestando todo lo demás. No repitas «ya le avisé» ni uses pasar_a_humano por el mismo tema.")
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
                lineas.append("No tiene citas agendadas vigentes (si en la plática se habló de una, ya no está en la agenda).")
        return "\n".join(lineas)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _xb_sa_store_website(self):
        company = self.wa_account_id.sudo()._xb_sa_company()
        return self.env["website"].sudo().search([("company_id", "=", company.id)], limit=1)

    def _xb_sa_store_tax(self, company):
        return company.account_sale_tax_id

    def _xb_sa_store_product_domain(self):
        company = self.wa_account_id.sudo()._xb_sa_company()
        website = self._xb_sa_store_website()
        dominio = [("is_published", "=", True), ("sale_ok", "=", True), ("company_id", "in", [False, company.id])]
        if website:
            dominio.append(("website_id", "in", [False, website.id]))
        return dominio

    def _xb_sa_store_price_ref(self, tmpl, company):
        """(sin IVA, con IVA) de referencia: el precio de lista de la plantilla."""
        sin = tmpl.list_price
        impuesto = self._xb_sa_store_tax(company)
        con = impuesto.compute_all(sin, quantity=1.0)["total_included"] if impuesto else sin
        return sin, con

    def _xb_sa_store_url(self, tmpl):
        website = self._xb_sa_store_website()
        base = (website.domain or "").rstrip("/")
        return f"{base}{tmpl.website_url}" if tmpl.website_url else base

    def _xb_sa_store_find_partner(self, celular, nombre, crear):
        Partner = self.env["res.partner"].sudo()
        llave = xb_phone_key(celular)
        partner = Partner
        if llave:
            self.env.cr.execute(
                "SELECT id FROM res_partner WHERE active AND right(regexp_replace(coalesce(phone,''),'\\D','','g'),10)=%s "
                "ORDER BY id LIMIT 1", [llave])
            fila = self.env.cr.fetchone()
            partner = Partner.browse(fila[0]) if fila else Partner
        if not partner and crear and (nombre or "").strip():
            partner = Partner.create({"name": nombre.strip(), "phone": celular or False,
                                      "company_type": "person", "company_id": False})
        return partner

    def _xb_sa_store_order(self, ref, equipo):
        """Pedido por número. Un cliente solo alcanza los suyos."""
        company = self.wa_account_id.sudo()._xb_sa_company()
        orden = self.env["sale.order"].sudo().search([
            ("name", "=ilike", (ref or "").strip()), ("company_id", "=", company.id)], limit=1)
        if not orden:
            return orden
        if not equipo:
            partner = self.whatsapp_partner_id.sudo()
            if not partner or orden.partner_id.commercial_partner_id != partner.commercial_partner_id:
                return self.env["sale.order"]
        return orden

    # ------------------------------------------------------------------
    # Herramientas
    # ------------------------------------------------------------------
    _XB_STOP = {"de", "del", "la", "el", "los", "las", "para", "con", "y", "en", "un", "una", "que", "algo", "algunos", "diseno", "disenos"}

    def _xb_sa_store_tags(self):
        """{grupo: [etiquetas]} de las que están en piezas publicadas."""
        company = self.wa_account_id.sudo()._xb_sa_company()
        piezas = self.env["product.template"].sudo().with_company(company).search(self._xb_sa_store_product_domain())
        grupos = {}
        for tag in piezas.product_tag_ids.sorted(lambda t: (t.filter_group_id.sequence, t.sequence, t.name)):
            grupos.setdefault(tag.filter_group_id.name or "Otras", []).append(tag.name)
        return grupos

    def _xb_sa_tool_buscar_productos(self, job, entrada):
        company = self.wa_account_id.sudo()._xb_sa_company()
        dominio = self._xb_sa_store_product_domain()
        for palabra in (entrada.get("texto") or "").split():
            plano = _plano(palabra)
            if plano in self._XB_STOP or len(plano) < 3:
                continue
            raiz = plano[:-1] if len(plano) > 4 and plano.endswith("s") else plano  # anillos → anillo
            dominio += ["|", "|", "|", ("name", "ilike", raiz), ("default_code", "ilike", raiz),
                        ("product_tag_ids.name", "ilike", raiz), ("categ_id.complete_name", "ilike", raiz)]
        if (entrada.get("categoria") or "").strip():
            dominio.append(("categ_id.complete_name", "ilike", entrada["categoria"].strip()))
        for etiqueta in entrada.get("etiquetas") or []:
            if (etiqueta or "").strip():
                dominio.append(("product_tag_ids.name", "ilike", etiqueta.strip()))
        productos = self.env["product.template"].sudo().with_company(company).search(dominio, limit=60, order="name")
        tope = float(entrada.get("precio_max") or 0)
        salida = []
        for t in productos:
            sin, con = self._xb_sa_store_price_ref(t, company)
            if tope and con > tope:
                continue
            salida.append({"id": t.id, "nombre": t.name, "categoria": t.categ_id.complete_name,
                           "etiquetas": t.product_tag_ids.mapped("name"),
                           "metales": [v.name for l in t.attribute_line_ids if l.attribute_id.name == "Metal"
                                       for v in l.product_template_value_ids.filtered(lambda x: x.ptav_active)][:8],
                           "desde_con_iva": round(con, 2), "liga": self._xb_sa_store_url(t)})
            if len(salida) >= min(int(entrada.get("limite") or 6), 8):
                break
        res = {"ok": True, "resultados": salida, "etiquetas_disponibles": self._xb_sa_store_tags(),
               "nota": "Precios de referencia con IVA; el definitivo depende del metal, ancho y medida y va en la cotización."}
        if not salida:
            res["nota"] = ("Sin coincidencias. Prueba con otra etiqueta de etiquetas_disponibles (p. ej. Promesa, Solitario) o con "
                           "menos palabras antes de decir que no hay.")
        return res

    def _xb_sa_tool_ver_producto(self, job, entrada):
        company = self.wa_account_id.sudo()._xb_sa_company()
        t = self.env["product.template"].sudo().with_company(company).search(
            self._xb_sa_store_product_domain() + [("id", "=", int(entrada.get("producto_id") or 0))], limit=1)
        if not t:
            return {"ok": False, "motivo": "Ese producto no está en el catálogo publicado."}
        opciones = {}
        for linea in t.attribute_line_ids:
            valores = linea.product_template_value_ids.filtered(lambda v: v.ptav_active)
            opciones[linea.attribute_id.name] = [v.name for v in valores]
        sin, con = self._xb_sa_store_price_ref(t, company)
        return {"ok": True, "id": t.id, "nombre": t.name, "categoria": t.categ_id.complete_name,
                "descripcion": (tools.html2plaintext(t.description_sale or "") or "")[:600],
                "etiquetas": t.product_tag_ids.mapped("name"), "opciones": opciones, "desde_con_iva": round(con, 2), "liga": self._xb_sa_store_url(t),
                "nota": "Para cotizar, cada atributo con varias opciones debe tener una elegida por el cliente."}

    def _xb_sa_store_variant(self, tmpl, opciones):
        """Variante de la plantilla con las opciones dadas. (variante, error)."""
        Ptav = self.env["product.template.attribute.value"]
        elegidas = Ptav
        faltan = {}
        por_nombre = [(_plano(o), o) for o in opciones or []]
        for linea in tmpl.attribute_line_ids:
            valores = linea.product_template_value_ids.filtered(lambda v: v.ptav_active)
            if not valores:
                continue
            if len(valores) == 1:
                elegidas |= valores
                continue
            hallado = Ptav
            for plano, _orig in por_nombre:
                coinciden = valores.filtered(lambda v: _plano(v.name) == plano)
                if coinciden:
                    hallado = coinciden[:1]
                    break
            if hallado:
                elegidas |= hallado
            else:
                faltan[linea.attribute_id.name] = [v.name for v in valores]
        if faltan:
            return None, ("Falta elegir: " + "; ".join(f"{a} (opciones: {', '.join(v[:30])})" for a, v in faltan.items()))
        variante = tmpl._get_variant_for_combination(elegidas) or tmpl._create_product_variant(elegidas)
        if not variante:
            return None, "No se pudo armar esa combinación de opciones."
        return variante, None

    def _xb_sa_store_line_price(self, variante, pricelist):
        """Precio unitario SIN IVA de la variante: lo que dé la lista de precios; si da 0 (variante nueva sin regla), su precio de lista."""
        ptavs = variante.product_template_attribute_value_ids
        precio = 0.0
        if pricelist:
            precio = pricelist._get_product_price(variante.with_context(xb_combinacion=tuple(ptavs.ids)), 1.0)
        return precio or variante.lst_price

    def _xb_sa_tool_crear_cotizacion(self, job, entrada):
        acc = self.wa_account_id.sudo()
        company = acc._xb_sa_company()
        equipo = self._xb_sa_store_team()
        if equipo and (entrada.get("cliente_celular") or entrada.get("cliente_nombre")):
            partner = self._xb_sa_store_find_partner(entrada.get("cliente_celular"), entrada.get("cliente_nombre"), crear=True)
            if not partner:
                return {"ok": False, "motivo": "Con el celular no encontré a esa persona; dame su nombre y celular para crearla."}
        else:
            partner = self.whatsapp_partner_id.sudo()
            if not partner:
                return {"ok": False, "motivo": "No tengo a quien cotizar: pídele su nombre y vuelve a intentar."}
        lineas = entrada.get("lineas") or []
        if not lineas:
            return {"ok": False, "motivo": "Faltan las joyas a cotizar."}
        website = self._xb_sa_store_website()
        pricelist = website.pricelist_id if website and "pricelist_id" in website._fields else self.env["product.pricelist"]
        pricelist = pricelist or self.env["product.pricelist"].sudo().search([("website_id", "=", website.id)], limit=1) or \
            self.env["product.pricelist"].sudo().search([("company_id", "=", company.id)], limit=1)
        impuesto = self._xb_sa_store_tax(company)
        valores_lineas = []
        for ln in lineas:
            t = self.env["product.template"].sudo().with_company(company).search(
                self._xb_sa_store_product_domain() + [("id", "=", int(ln.get("producto_id") or 0))], limit=1)
            if not t:
                return {"ok": False, "motivo": f"El producto {ln.get('producto_id')} no está en el catálogo publicado."}
            variante, error = self._xb_sa_store_variant(t, ln.get("opciones"))
            if error:
                return {"ok": False, "motivo": f"{t.name}: {error}"}
            cantidad = float(ln.get("cantidad") or 1)
            vals = {"product_id": variante.id, "product_uom_qty": cantidad,
                    "price_unit": self._xb_sa_store_line_price(variante, pricelist),
                    "tax_ids": [(6, 0, impuesto.ids)] if impuesto else [(5,)]}
            nota = (ln.get("nota") or "").strip()
            if nota:
                vals["name"] = f"{variante.display_name}\n{nota}"
            valores_lineas.append((0, 0, vals))
        orden = self.env["sale.order"].sudo().with_company(company).create({
            "partner_id": partner.id, "company_id": company.id,
            "pricelist_id": pricelist.id or False,
            "user_id": (equipo or acc.xb_sa_sales_user_ids[:1]).id or False,
            "origin": "Agente de WhatsApp", "order_line": valores_lineas})
        orden.message_post(body=Markup("Cotización creada por el agente de WhatsApp%s.") %
                           (f" a petición de {equipo.name}" if equipo else ""), message_type="comment",
                           subtype_xmlid="mail.mt_note")
        if not equipo:
            self._xb_sa_notify(orden, acc.xb_sa_sales_user_ids,
                               f"Cotización {orden.name} creada por el agente para {partner.name}: ${orden.amount_total:,.2f}")
        job.mode = "sales"
        return {"ok": True, "pedido": orden.name, "total_con_iva": round(orden.amount_total, 2),
                "lineas": [f"{l.product_uom_qty:g} × {l.product_id.display_name}: ${l.price_total:,.2f}"
                           for l in orden.order_line],
                "nota": "Es una cotización (borrador). Mándale el ticket con enviar_ticket y dile que el precio incluye IVA."}

    def _xb_sa_tool_enviar_foto_producto(self, job, entrada):
        company = self.wa_account_id.sudo()._xb_sa_company()
        t = self.env["product.template"].sudo().with_company(company).search(
            self._xb_sa_store_product_domain() + [("id", "=", int(entrada.get("producto_id") or 0))], limit=1)
        if not t:
            return {"ok": False, "motivo": "Ese producto no está en el catálogo publicado."}
        if not t.image_1920:
            return {"ok": False, "motivo": "Esa pieza todavía no tiene foto en el sitio."}
        imagen = Image.open(io.BytesIO(base64.b64decode(t.image_1920))).convert("RGB")
        imagen.thumbnail((1280, 1280))
        salida = io.BytesIO()
        imagen.save(salida, "JPEG", quality=88)
        self._xb_sa_post_image(salida.getvalue(), f"{t.id}.jpg", (entrada.get("pie") or t.name).strip())
        return {"ok": True, "nota": f"Foto de «{t.name}» enviada."}

    def _xb_sa_tool_ver_pedidos(self, job, entrada):
        acc = self.wa_account_id.sudo()
        company = acc._xb_sa_company()
        equipo = self._xb_sa_store_team()
        dominio = [("company_id", "=", company.id)]
        buscar = (entrada.get("buscar") or "").strip()
        if equipo and buscar:
            llave = xb_phone_key(buscar)
            if re.match(r"^s\d+", buscar, re.I):
                dominio.append(("name", "=ilike", buscar))
            elif llave:
                partner = self._xb_sa_store_find_partner(buscar, "", crear=False)
                if not partner:
                    return {"ok": True, "pedidos": [], "nota": "No hay una persona con ese celular."}
                dominio.append(("partner_id", "child_of", partner.commercial_partner_id.id))
            else:
                dominio.append(("partner_id.name", "ilike", buscar))
        else:
            partner = self.whatsapp_partner_id.sudo()
            if not partner:
                return {"ok": True, "pedidos": [], "nota": "No encuentro pedidos ligados a este número."}
            dominio.append(("partner_id", "child_of", partner.commercial_partner_id.id))
        pedidos = self.env["sale.order"].sudo().search(dominio, order="id desc", limit=8)
        tz = pytz.timezone(XB_TZ)
        salida = []
        for p in pedidos:
            entrega = (pytz.utc.localize(p.commitment_date).astimezone(tz).strftime("%d/%m/%Y")
                       if p.commitment_date else "sin fecha")
            salida.append({
                "pedido": p.name, "cliente": p.partner_id.name if equipo else "",
                "estado": XB_STORE_STATES.get(p.state, p.state),
                "fecha": p.date_order.strftime("%d/%m/%Y") if p.date_order else "",
                "total": round(p.amount_total, 2),
                "saldo_pendiente": round(getattr(p, "amount_unpaid", 0.0) or 0.0, 2) if p.state == "sale" else None,
                "entrega_prometida": entrega,
                "listo_para_recoger": bool(p.xb_ready_notified_date) if "xb_ready_notified_date" in p._fields else None,
                "piezas": [f"{l.product_uom_qty:g} × {l.product_id.display_name or l.name}" for l in p.order_line
                           if not l.display_type][:6]})
        return {"ok": True, "pedidos": salida}

    def _xb_sa_tool_enviar_ticket(self, job, entrada):
        equipo = self._xb_sa_store_team()
        orden = self._xb_sa_store_order(entrada.get("pedido"), equipo)
        if not orden:
            return {"ok": False, "motivo": "No encuentro ese pedido entre los de esta persona."}
        png = orden._xb_quotation_image()
        imagen = Image.open(io.BytesIO(png)).convert("RGB")
        salida = io.BytesIO()
        imagen.save(salida, "JPEG", quality=90)
        self._xb_sa_post_image(salida.getvalue(), f"{orden.name}.jpg",
                               f"{'Pedido' if orden.state == 'sale' else 'Cotización'} {orden.name}")
        return {"ok": True, "nota": f"Ticket de {orden.name} enviado (total ${orden.amount_total:,.2f} con IVA)."}

    def _xb_sa_tool_generar_pedido(self, job, entrada):
        acc = self.wa_account_id.sudo()
        equipo = self._xb_sa_store_team()
        orden = self._xb_sa_store_order(entrada.get("pedido"), equipo)
        if not orden:
            return {"ok": False, "motivo": "No encuentro esa cotización."}
        if orden.state == "sale":
            return {"ok": True, "nota": f"{orden.name} ya es un pedido confirmado."}
        if orden.state == "cancel":
            return {"ok": False, "motivo": f"{orden.name} está cancelada."}
        if not equipo:
            self._xb_sa_notify(orden, acc.xb_sa_sales_user_ids | acc.xb_sa_support_user_ids,
                               f"El cliente pide confirmar el pedido {orden.name} (${orden.amount_total:,.2f}): revísalo y confírmalo.",
                               urgente=True, bandeja=True)
            job.mode = "sales"
            return {"ok": True, "confirmado": False,
                    "nota": "El pedido lo confirma la tienda. Ya se le avisó a una persona del equipo; dile al cliente que "
                            "le confirmarán su pedido y los detalles del anticipo. No digas que ya quedó confirmado."}
        orden.sudo().action_confirm()
        orden.message_post(body=Markup("Pedido confirmado por el agente de WhatsApp a petición de %s.") % equipo.name,
                           message_type="comment", subtype_xmlid="mail.mt_note")
        return {"ok": True, "confirmado": True, "nota": f"{orden.name} confirmado como pedido (${orden.amount_total:,.2f} con IVA)."}
