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
# Solo si quien escribe es del equipo y está ligada a un usuario del Odoo de la tienda: consulta, capturas y cambios
# (sin costo) por el mismo camino y con los mismos límites que el agente de soporte.
XB_STORE_TEAM_KEEP = {"buscar_modelos", "describir_modelo", "consultar_registros", "resumir_registros",
                      "historial_de_cambios", "enviar_captura", "cotizar_servicio", "ejecutar_servicio"}

XB_STORE_TOOLS = [
    _tool("buscar_productos",
          "Busca joyas en el catálogo PÚBLICO de la tienda (las publicadas en el sitio) por palabras del nombre, categoría y ETIQUETAS "
          "(estilo: Promesa, Solitario, Vintage, Pavé, Halo, Eternity, Catedral, Tensión…; forma de piedra; una o varias piedras). "
          "Si el cliente pide un estilo, busca por su etiqueta antes de decir que no hay. OJO: las «Argolla» son argollas de MATRIMONIO "
          "(bandas lisas): NO son anillos de compromiso ni de promesa; solo ofrécelas si piden argollas o alianzas de boda. "
          "Los anillos de compromiso y promesa son las «Montadura» con etiqueta de estilo. Devuelve nombre, categoría, "
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
          "precio «desde» y liga. Úsala antes de cotizar para conocer las opciones. Si ya sabes la combinación (metal, "
          "medida…), pásala en «opciones» y te da su precio exacto con IVA, sin necesidad de cotizar ni de pedir el nombre.",
          {"producto_id": {"type": "integer"},
           "opciones": {"type": "array", "items": {"type": "string"},
                        "description": "Opcional: valores elegidos con su nombre exacto (p. ej. «Oro amarillo 10kt», «6.5»)."}}),
    _tool("crear_cotizacion",
          "Crea una COTIZACIÓN (borrador, no es un pedido) con una o más joyas y su ticket queda listo para enviarse con "
          "enviar_ticket. Cada línea lleva el id del producto, la cantidad y las opciones elegidas con el nombre EXACTO "
          "que devolvió ver_producto (metal, ancho, medida…). Si falta alguna opción, no la inventes: pregúntasela al cliente. "
          "Para clientes: se cotiza a su propio nombre y es OBLIGATORIO pasar nombre_completo (nombre y apellido que él te dio; "
          "si en WhatsApp solo tiene un apodo o usuario, pregúntaselo antes de cotizar). El equipo puede cotizar a nombre de otra persona con su celular.",
          {"lineas": {"type": "array", "items": {"type": "object", "properties": {
              "producto_id": {"type": "integer"},
              "cantidad": {"type": "number"},
              "opciones": {"type": "array", "items": {"type": "string"},
                           "description": "Nombres exactos de las opciones elegidas, p. ej. [\"Oro amarillo 14kt\",\"4mm\",\"7.5\"]."},
              "nota": {"type": "string", "description": "Grabado, mensaje o indicación especial; vacío si no hay."}},
              "required": ["producto_id", "cantidad", "opciones", "nota"]}},
           "nombre_completo": {"type": "string", "description": "Clientes: nombre y apellido reales de quien escribe, tal como te los dijo; vacío solo si es del equipo."},
           "cliente_nombre": {"type": "string", "description": "Solo equipo: nombre de a quién se cotiza; vacío = quien escribe."},
           "cliente_celular": {"type": "string", "description": "Solo equipo: celular de 10 dígitos; vacío = quien escribe."}}),
    _tool("enviar_foto_producto",
          "Manda por WhatsApp la FOTO de una joya del catálogo (va antes de tu texto). Úsala al recomendar piezas: máximo "
          "3 fotos por respuesta, las que más le interesen.",
          {"producto_id": {"type": "integer"},
           "pie": {"type": "string", "description": "Una línea con el nombre y el precio «desde»; vacío = solo el nombre."}}),
    _tool("ver_pedidos",
          "Pedidos y cotizaciones. A un cliente le muestra los SUYOS (estado, total, saldo pendiente, si ya está listo). "
          "Al equipo además le da la fecha de entrega. El equipo puede buscar por número (S00123), nombre o celular de cualquiera.",
          {"buscar": {"type": "string", "description": "Solo equipo: número, nombre o celular; vacío = los de quien escribe."}}),
    _tool("enviar_ticket",
          "Manda por WhatsApp el TICKET (imagen) de una cotización o pedido, con su QR para revisarlo o pagarlo en línea. "
          "Va antes de tu texto. Un cliente solo puede pedir los suyos.",
          {"pedido": {"type": "string", "description": "Número, p. ej. S00369."}}),
    _tool("revisar_certificado",
          "Revisa si el certificado ICERT (la tarjeta que se acerca al celular) de una pieza ya está dado de alta y activo. "
          "Pide el número de la tarjeta: viene impreso en la tarjeta y aparece en la pantalla que sale al acercarla "
          "(si manda captura, léelo de ahí). Sin número revisa las piezas que estén a nombre de quien escribe.",
          {"numero": {"type": "string", "description": "Número de la tarjeta o de la pieza; cadena vacía si no lo tiene."}}),
    _tool("generar_pedido",
          "Confirma una cotización y la vuelve PEDIDO. Solo el equipo de la tienda puede hacerlo, y solo después de que la "
          "persona del equipo lo pida de forma explícita. Si lo pide un cliente, avisa a la tienda para que lo confirme "
          "(queda en espera, no se confirma solo).",
          {"pedido": {"type": "string", "description": "Número de la cotización."}}),
]
# Joyería que fabrica (Anello): lo que no está en el catálogo se cotiza a la medida y lo autoriza el equipo.
XB_CUSTOM_TOOLS = [
    _tool("cotizacion_a_la_medida",
          "Para una pieza que NO está en el catálogo (diseño propio, nombre o letras, una imagen religiosa, copiar una foto…). "
          "Úsala cuando ya tengas TODOS los datos: qué pieza, metal y kilataje, piedras, medidas o largo, texto, para cuándo "
          "la necesita y si recoge o se le envía, y su nombre completo. Deja la cotización en borrador con esos datos y las "
          "fotos que mandó, y se la pasa al equipo, que le pone el precio y la autoriza; al autorizarla, al cliente le llega "
          "sola por aquí. Si pidió varias opciones (p. ej. con zirconia y con diamante), ponlas en «opciones». "
          "Un modelo del catálogo con otra forma de piedra en ZIRCONIA (oval, pera…) NO es a la medida: cotízalo con "
          "crear_cotizacion y pon la forma en la nota.",
          {"pieza": {"type": "string", "description": "Una línea, p. ej. «Collar con el nombre Daniela en oro blanco»."},
           "detalle": {"type": "string", "description": "Todo lo que pidió, con medidas, texto, fecha y entrega."},
           "opciones": {"type": "array", "items": {"type": "string"},
                        "description": "Una por versión a cotizar, p. ej. [\"Oro blanco 10k con zirconias\", \"Oro blanco 14k con diamantes de laboratorio\"]; vacía si es una sola."},
           "nombre_completo": {"type": "string", "description": "Nombre y apellido reales del cliente."}}),
]
# Catálogo por lista de precios (DIAMANE: diamantes sueltos para joyeros). Reemplazan a las de joyería.
XB_STONE_TOOLS = {
    "buscar_productos": _tool(
        "buscar_productos",
        "Busca DIAMANTES sueltos del inventario (los que tienen precio en la lista de la empresa). Filtra por palabras del "
        "nombre (forma abreviada BR redondo, PR princesa, OV oval, EM esmeralda, PS pera, MQ marquesa, CU cojín, AC asscher, "
        "RA radiant, HS corazón, BG baguette, TR trillón; color D–Z; pureza IF, VVS1, VS2, SI1…; laboratorio GIA, IGI…), "
        "por rango de quilates, por origen y por precio. Devuelve los datos de cada piedra y su precio sin IVA y con IVA.",
        {"texto": {"type": "string", "description": "Palabras del nombre, p. ej. «BR VS1», «OV G», «GIA»; vacío = no filtrar por nombre."},
         "origen": {"type": "string", "enum": ["", "natural", "laboratorio"], "description": "Vacío = los dos."},
         "quilates_min": {"type": "number", "description": "0 = sin mínimo."},
         "quilates_max": {"type": "number", "description": "0 = sin máximo."},
         "precio_max": {"type": "number", "description": "Precio máximo CON IVA; 0 = sin tope."},
         "limite": {"type": "integer", "description": "Cuántos mostrar (máx. 8)."}}),
    "ver_producto": _tool(
        "ver_producto",
        "Ficha completa de un diamante: forma, quilates, color, pureza, corte, pulido, simetría, fluorescencia, medidas, "
        "origen, certificados y su precio sin IVA y con IVA.",
        {"producto_id": {"type": "integer"}}),
}
# Tienda que vende sola (DIAMANE): el cliente cierra con su comprobante y el equipo solo verifica.
XB_SALE_TOOLS = {
    "generar_pedido": _tool(
        "generar_pedido",
        "Confirma una cotización y la vuelve PEDIDO (con eso queda apartada la piedra). Con un CLIENTE úsala solo cuando ya te "
        "mandó en esta plática el COMPROBANTE de su transferencia o depósito: léelo y pasa el monto que se ve en él; el comprobante "
        "se guarda en el pedido y el equipo verifica el depósito. Si pagó en línea con la liga, el pedido se confirma solo (no la "
        "uses). Con el EQUIPO, solo cuando lo pida de forma explícita (monto 0).",
        {"pedido": {"type": "string", "description": "Número de la cotización."},
         "monto_comprobante": {"type": "number", "description": "Monto pagado que se ve en el comprobante, en pesos; 0 si es el equipo."}}),
}
XB_SALE_EXTRA = [
    _tool("avisar_a_la_tienda",
          "Avisa al equipo de algo que tiene que hacer, SIN pasarle la plática: tú sigues atendiendo. Para el costo de un envío, "
          "los datos para una factura, una visita para pagar en efectivo o recoger, o una entrega en persona.",
          {"asunto": {"type": "string", "enum": ["envio", "factura", "pago_en_oficina", "entrega", "otro"]},
           "pedido": {"type": "string", "description": "Número del pedido o cotización; vacío si no hay."},
           "detalle": {"type": "string", "description": "Todo lo que el equipo necesita: dirección y CP, datos fiscales, día y hora, etc."}}),
]
# Tienda solo para negocios: antes de ver precios, el cliente manda su constancia y el dueño lo aprueba.
XB_B2B_TOOLS = [
    _tool("verificar_joyero",
          "Pide la aprobación del dueño para que este cliente pueda ver precios y comprar. Úsala cuando ya te mandó en esta "
          "plática su CONSTANCIA DE SITUACIÓN FISCAL (foto o PDF): léela y pasa sus datos tal cual aparecen. Marca "
          "«actividad_de_joyeria» solo si alguna de sus actividades económicas es de joyería, orfebrería, relojería, "
          "piedras preciosas o metales preciosos.",
          {"razon_social": {"type": "string", "description": "Nombre o razón social como viene en la constancia."},
           "rfc": {"type": "string"},
           "actividades": {"type": "string", "description": "Sus actividades económicas como vienen en la constancia."},
           "codigo_postal": {"type": "string"},
           "joyeria": {"type": "string", "description": "Nombre comercial de su joyería o taller, como te lo dijo."},
           "ciudad": {"type": "string"},
           "actividad_de_joyeria": {"type": "boolean"},
           "observaciones": {"type": "string", "description": "Algo que no cuadre (constancia vieja, nombre distinto, ilegible…); vacío si nada."}}),
]
XB_B2B_PRICE_KEYS = {"precio_sin_iva", "precio_con_iva", "desde_con_iva", "precio_de_la_combinacion_con_iva"}
XB_B2B_NOTE = ("Todavía NO está verificado como negocio: no le des precios ni cotices. Pídele su Constancia de Situación "
               "Fiscal (foto o PDF) para verificar su joyería y, cuando la mande, usa verificar_joyero.")
for _t in XB_STORE_TOOLS + XB_CUSTOM_TOOLS + list(XB_STONE_TOOLS.values()) + list(XB_SALE_TOOLS.values()) + XB_SALE_EXTRA + XB_B2B_TOOLS:
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
        tienda = XB_STORE_TOOLS
        if self.wa_account_id.sudo().xb_sa_store_pricelist_id:
            tienda = [XB_STONE_TOOLS.get(t["name"], t) for t in XB_STORE_TOOLS]
        if self.wa_account_id.sudo().xb_sa_store_autonomous:
            tienda = [XB_SALE_TOOLS.get(t["name"], t) for t in tienda] + XB_SALE_EXTRA
        if self.wa_account_id.sudo().xb_sa_store_b2b_category_id:
            tienda = tienda + XB_B2B_TOOLS
        if self.wa_account_id.sudo().xb_sa_quote_approver_ids:
            tienda = tienda + XB_CUSTOM_TOOLS
        herramientas = [t for t in XB_TOOLS if t["name"] in XB_STORE_KEEP] + tienda
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
                "Si pide datos de Odoo (ventas, existencias, clientes), usa las herramientas de consulta; si no encuentra dónde picar o pide "
                "una imagen, usa enviar_captura (la captura REAL de su pantalla, con el botón marcado en rojo). Si pide que corrijas o cambies algo "
                "en Odoo, usa cotizar_servicio (para la tienda NO tiene costo: no menciones precio) y, cuando responda SÍ, ejecutar_servicio.")
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
        revision = self.env["xb.support.proposal"].sudo().search([
            ("kind", "=", "quote"), ("channel_id", "=", self.id), ("state", "=", "pending")], limit=3)
        if revision:
            lineas.append("Cotización(es) a la medida EN REVISIÓN del equipo: " + "; ".join(
                f"{r.sale_order_id.name or ''} {r.name}" for r in revision) + ". Ya tienen sus datos: si pregunta, dile que la "
                "están terminando y le llega por aquí; no la vuelvas a pedir ni des precio. Si agrega o cambia algo, vuelve a "
                "usar cotizacion_a_la_medida con todo actualizado.")
        if acc.xb_sa_store_b2b_category_id and not equipo:
            pendiente = self.env["xb.support.proposal"].sudo().search_count([
                ("kind", "=", "b2b"), ("channel_id", "=", self.id), ("state", "=", "pending")])
            lineas.append("Este cliente YA ESTÁ VERIFICADO como negocio: puede ver precios y comprar." if not self._xb_sa_store_b2b_pending()
                          else "Su verificación ya se mandó a aprobar: espera la respuesta; no le des precios todavía." if pendiente
                          else XB_B2B_NOTE)
        if (self.xb_sa_pause_reason == "handoff" and not self.xb_sa_paused_until and self.xb_sa_hold_dt
                and self.xb_sa_hold_dt > fields.Datetime.now() - timedelta(hours=48)):
            lineas.append("YA SE AVISÓ a una persona de la tienda sobre esta plática y ella contestará lo pendiente. NO te quedes "
                          "callado: sigue contestando todo lo demás. No repitas «ya le avisé» ni uses pasar_a_humano por el mismo tema.")
        lineas += self._xb_sa_common_rules()
        lineas.append("Si preguntan si su certificado ICERT (la tarjeta) ya está registrado o activo, usa revisar_certificado "
                      "con el número de la tarjeta antes de contestar.")
        if self.whatsapp_partner_id:
            tz = pytz.timezone(XB_TZ)
            citas = self.env["calendar.event"].sudo().search([
                ("appointment_type_id", "!=", False), ("stop", ">", fields.Datetime.now()),
                ("partner_ids", "in", self.whatsapp_partner_id.ids)], order="start", limit=3)
            if citas:
                lineas.append("Citas agendadas vigentes: " + "; ".join(
                    f"{XB_DIAS[pytz.utc.localize(c.start).astimezone(tz).weekday()]} "
                    f"{pytz.utc.localize(c.start).astimezone(tz):%d/%m/%Y %H:%M}" + (f" con {c.user_id.name}" if equipo else "") for c in citas) + ".")
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
        acc = self.wa_account_id.sudo()
        company = acc._xb_sa_company()
        if acc.xb_sa_store_pricelist_id:
            # Catálogo = lo que tiene precio propio en la lista (p. ej. diamantes de DIAMANE), publicado o no.
            items = acc.xb_sa_store_pricelist_id.item_ids.filtered(lambda i: i.applied_on == "1_product")
            return [("id", "in", items.product_tmpl_id.ids), ("sale_ok", "=", True), ("company_id", "in", [False, company.id])]
        website = self._xb_sa_store_website()
        dominio = [("is_published", "=", True), ("sale_ok", "=", True), ("company_id", "in", [False, company.id])]
        if website:
            dominio.append(("website_id", "in", [False, website.id]))
        return dominio

    def _xb_sa_store_price_ref(self, tmpl, company):
        """(sin IVA, con IVA) de referencia: el precio de lista de la plantilla, o el de la lista de la cuenta.
        Joyas con precio por metal: el de su combinación más barata (ver _xb_sa_store_from_by_metal)."""
        lista = self.wa_account_id.sudo().xb_sa_store_pricelist_id
        sin = lista._get_product_price(tmpl.product_variant_id, 1.0) if lista and tmpl.product_variant_id else tmpl.list_price
        if not lista:
            por_metal = self._xb_sa_store_from_by_metal(tmpl, company)
            if por_metal:
                sin = min(por_metal.values())
        return sin, self._xb_sa_store_with_tax(sin, company)

    def _xb_sa_store_with_tax(self, sin, company):
        impuesto = self._xb_sa_store_tax(company)
        return impuesto.compute_all(sin, quantity=1.0)["total_included"] if impuesto else sin

    def _xb_sa_store_from_by_metal(self, tmpl, company):
        """{metal: precio SIN IVA} de la combinación base de la tienda («Desde») en cada metal que ofrece la joya.
        El precio de lista de estas joyas es 0: lo pone el peso por metal, así que hay que calcularlo por combinación."""
        if not ("xb_precio_por_metal" in tmpl._fields and tmpl.xb_precio_por_metal):
            return {}
        pricelist = self._xb_sa_store_pricelist(company)
        if not pricelist:
            return {}
        try:
            base = tmpl._xb_combinacion_desde() if hasattr(tmpl, "_xb_combinacion_desde") else tmpl._get_first_possible_combination()
            linea = tmpl.valid_product_template_attribute_line_ids.filtered(lambda l: l.attribute_id.name == "Metal")
            metales = linea.product_template_value_ids._only_active() if linea else base.browse()
            salida = {}
            for metal in metales or [None]:
                comb = (base - base.filtered(lambda v: v.attribute_line_id == linea)) | metal if metal else base
                precio = pricelist._get_product_price(tmpl.with_context(xb_combinacion=tuple(comb.ids)), 1.0)
                if precio:
                    salida[metal.name if metal else ""] = precio
            return salida
        except Exception:  # noqa: BLE001 - una joya mal capturada no debe tumbar la búsqueda
            return {}

    def _xb_sa_store_from_text(self, tmpl, company):
        """«desde_por_metal»: el precio con IVA de la versión más sencilla en cada metal (medida y piedra base)."""
        por_metal = self._xb_sa_store_from_by_metal(tmpl, company)
        if len(por_metal) < 2:
            return {}
        return {"desde_por_metal_con_iva": {m: round(self._xb_sa_store_with_tax(p, company), 2)
                                            for m, p in sorted(por_metal.items(), key=lambda x: x[1])}}

    def _xb_sa_store_url(self, tmpl):
        website = self._xb_sa_store_website()
        if self.wa_account_id.sudo().xb_sa_store_pricelist_id and (
                not tmpl.is_published or (tmpl.website_id and tmpl.website_id != website)):
            return ""  # su ficha está en otro sitio (p. ej. la de Anello) o no está publicada
        base = (website.domain or "").rstrip("/")
        return f"{base}{tmpl.website_url}" if tmpl.website_url else base

    def _xb_sa_store_share_url(self, orden):
        website = self._xb_sa_store_website()
        base = (website.domain or orden.get_base_url()).rstrip("/")
        return base + orden._get_share_url(redirect=True)

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

    _XB_GEMA = [("forma", "x_studio_talla_o_forma"), ("quilates", "x_studio_quilataje_c"), ("color", "x_studio_color_real"),
                ("pureza", "x_studio_pureza_real"), ("corte", "x_studio_corte"), ("pulido", "x_studio_pulido"),
                ("simetria", "x_studio_simetria_calificacion_c"), ("fluorescencia", "x_studio_fluorescencia_intensidad"),
                ("medidas_mm", "x_studio_medidas_totales"), ("origen", "x_studio_origen_c"), ("certificados", "x_studio_certificados")]

    def _xb_sa_store_gem(self, t):
        """Datos de la piedra (campos de la ficha de gema) que tengan valor."""
        datos = {}
        for clave, campo in self._XB_GEMA:
            if campo not in t._fields or not t[campo]:
                continue
            valor = t[campo]
            if t._fields[campo].type in ("many2one", "many2many"):
                valor = ", ".join(valor.mapped("display_name"))
            elif t._fields[campo].type == "selection":
                valor = dict(t._fields[campo]._description_selection(t.env)).get(valor, valor)
            if isinstance(valor, str) and not re.search(r"\w", valor):
                continue  # p. ej. medidas vacías « -  x »
            datos[clave] = valor
        return datos

    def _xb_sa_store_stones(self, entrada):
        company = self.wa_account_id.sudo()._xb_sa_company()
        dominio = self._xb_sa_store_product_domain()
        for palabra in (entrada.get("texto") or "").split():
            dominio.append(("name", "ilike", palabra))
        origen = (entrada.get("origen") or "").strip().lower()
        if origen and "x_studio_origen_c" in self.env["product.template"]._fields:
            dominio.append(("x_studio_origen_c", "ilike", "laboratorio" if origen.startswith("lab") else "Natural"))
        if float(entrada.get("quilates_min") or 0):
            dominio.append(("x_studio_quilataje_c", ">=", float(entrada["quilates_min"])))
        if float(entrada.get("quilates_max") or 0):
            dominio.append(("x_studio_quilataje_c", "<=", float(entrada["quilates_max"])))
        piedras = self.env["product.template"].sudo().with_company(company).search(dominio, order="x_studio_quilataje_c, id")
        tope = float(entrada.get("precio_max") or 0)
        salida = []
        for t in piedras:
            sin, con = self._xb_sa_store_price_ref(t, company)
            if tope and con > tope:
                continue
            salida.append({"id": t.id, "nombre": t.name, **self._xb_sa_store_gem(t),
                           "precio_sin_iva": round(sin, 2), "precio_con_iva": round(con, 2)})
            if len(salida) >= min(int(entrada.get("limite") or 6), 8):
                break
        return {"ok": True, "resultados": salida, "total_que_coinciden": len(piedras),
                "nota": "Precios para joyería (mayoreo), de esta lista. Si no hay lo que busca, ofrece lo más parecido "
                        "(forma, quilates, color o pureza cercanos) o pasa la plática a una persona."}

    def _xb_sa_tool_buscar_productos(self, job, entrada):
        if self.wa_account_id.sudo().xb_sa_store_pricelist_id:
            if self._xb_sa_store_b2b_pending():
                return dict(self._xb_sa_store_hide_prices(self._xb_sa_store_stones(entrada)), nota=XB_B2B_NOTE)
            return self._xb_sa_store_stones(entrada)
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
                           "tipo": ("ARGOLLA DE MATRIMONIO (no es de compromiso ni de promesa)"
                                    if "argolla" in (t.categ_id.complete_name or "").lower() else
                                    "montadura / anillo con piedra" if "montadura" in (t.categ_id.complete_name or "").lower() else ""),
                           "etiquetas": t.product_tag_ids.mapped("name"),
                           "metales": [v.name for l in t.attribute_line_ids if l.attribute_id.name == "Metal"
                                       for v in l.product_template_value_ids.filtered(lambda x: x.ptav_active)][:8],
                           "desde_con_iva": round(con, 2), **self._xb_sa_store_from_text(t, company),
                           "liga": self._xb_sa_store_url(t)})
            if len(salida) >= min(int(entrada.get("limite") or 6), 8):
                break
        res = {"ok": True, "resultados": salida, "etiquetas_disponibles": self._xb_sa_store_tags(),
               "nota": "«desde_con_iva» es la versión más barata (normalmente plata con zirconia); «desde_por_metal_con_iva» da el "
                       "«desde» en cada metal. Úsalos para filtrar por presupuesto; el precio exacto de una combinación lo da "
                       "ver_producto con «opciones» y el definitivo va en la cotización."}
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
        if self.wa_account_id.sudo().xb_sa_store_pricelist_id:
            sin, con = self._xb_sa_store_price_ref(t, company)
            if self._xb_sa_store_b2b_pending():
                return {"ok": True, "id": t.id, "nombre": t.name, **self._xb_sa_store_gem(t), "nota": XB_B2B_NOTE}
            return {"ok": True, "id": t.id, "nombre": t.name, **self._xb_sa_store_gem(t),
                    "precio_sin_iva": round(sin, 2), "precio_con_iva": round(con, 2),
                    "tiene_video": bool("x_studio_video" in t._fields and t.x_studio_video),
                    "nota": "Pieza única del inventario: el precio es el de la lista para joyería. Para apartarla o comprarla, "
                            "cotízala con crear_cotizacion (opciones vacías)."}
        opciones = {}
        for linea in t.attribute_line_ids:
            valores = linea.product_template_value_ids.filtered(lambda v: v.ptav_active)
            opciones[linea.attribute_id.name] = [v.name for v in valores]
        sin, con = self._xb_sa_store_price_ref(t, company)
        combinacion = {}
        if entrada.get("opciones"):
            variante, error = self._xb_sa_store_variant(t, entrada.get("opciones"))
            if error:
                combinacion = {"precio_de_la_combinacion": None, "motivo": error}
            else:
                impuesto = self._xb_sa_store_tax(company)
                unitario = self._xb_sa_store_line_price(variante, self._xb_sa_store_pricelist(company))
                total = impuesto.compute_all(unitario, quantity=1.0)["total_included"] if impuesto else unitario
                combinacion = {"combinacion": variante.display_name, "precio_de_la_combinacion_con_iva": round(total, 2)}
        return {"ok": True, **combinacion, "id": t.id, "nombre": t.name, "categoria": t.categ_id.complete_name,
                "descripcion": (tools.html2plaintext(t.description_sale or "") or "")[:600],
                "etiquetas": t.product_tag_ids.mapped("name"), "opciones": opciones, "desde_con_iva": round(con, 2),
                **self._xb_sa_store_from_text(t, company), "liga": self._xb_sa_store_url(t),
                "dias_de_fabricacion": int(t.sale_delay or 0),
                "nota": "Si trae «precio_de_la_combinacion_con_iva», dáselo de inmediato como el precio de esa pieza con IVA; el nombre "
                        "completo solo hace falta para formalizar la cotización. Para cotizar, cada atributo con varias opciones debe tener una elegida por el cliente. "
                        "TIEMPO DE ENTREGA (solo ANTES de comprar; con un pedido ya confirmado no des fechas ni plazos): si preguntan, usa «dias_de_fabricacion» de ESTE modelo: di que tarda unos N días en fabricarse "
                        "contados desde que confirma y paga su pedido, da la fecha probable (hoy + N días) y aclara que la tienda "
                        "confirma la fecha exacta al levantar el pedido. Si «dias_de_fabricacion» es 0, no des plazo: di que la tienda se la confirma."}

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

    def _xb_sa_store_pricelist(self, company):
        """La lista de precios del sitio de la tienda (la misma con la que se cotiza)."""
        if self.wa_account_id.sudo().xb_sa_store_pricelist_id:
            return self.wa_account_id.sudo().xb_sa_store_pricelist_id
        website = self._xb_sa_store_website()
        pricelist = website.pricelist_id if website and "pricelist_id" in website._fields else self.env["product.pricelist"]
        return pricelist or self.env["product.pricelist"].sudo().search([("website_id", "=", website.id)], limit=1) or \
            self.env["product.pricelist"].sudo().search([("company_id", "=", company.id)], limit=1)

    def _xb_sa_store_line_price(self, variante, pricelist):
        """Precio unitario SIN IVA de la variante: lo que dé la lista de precios; si da 0 (variante nueva sin regla), su precio de lista."""
        ptavs = variante.product_template_attribute_value_ids
        precio = 0.0
        if pricelist:
            precio = pricelist._get_product_price(variante.with_context(xb_combinacion=tuple(ptavs.ids)), 1.0)
        return precio or variante.lst_price

    def _xb_sa_tool_crear_cotizacion(self, job, entrada):
        if self._xb_sa_store_b2b_pending():
            return {"ok": False, "motivo": XB_B2B_NOTE}
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
            if not equipo:
                nombre = " ".join((entrada.get("nombre_completo") or "").split())
                if len(nombre.split()) < 2:
                    return {"ok": False, "motivo": "Falta su nombre completo (nombre y apellido). Pídeselo con naturalidad, "
                                                   "dile que es para poner la cotización a su nombre, y vuelve a intentar."}
                if nombre.lower() != (partner.name or "").strip().lower():
                    partner.name = nombre
        lineas = entrada.get("lineas") or []
        if not lineas:
            return {"ok": False, "motivo": "Faltan las joyas a cotizar."}
        if not partner.lang or partner.lang.startswith("en"):
            partner.lang = "es_MX"
        pricelist = self._xb_sa_store_pricelist(company)
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
                vals["name"] = f"{variante.with_context(lang=partner.lang).display_name}\n{nota}"
            valores_lineas.append((0, 0, vals))
        orden = self.env["sale.order"].sudo().with_company(company).with_context(lang=partner.lang).create({
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
        res = {"ok": True, "pedido": orden.name, "total_con_iva": round(orden.amount_total, 2),
               "liga_cotizacion": self._xb_sa_store_share_url(orden),
               "lineas": [f"{l.product_uom_qty:g} × {l.product_id.display_name}: ${l.price_total:,.2f}"
                          for l in orden.order_line],
               "nota": "Es una cotización (borrador). Mándale el ticket con enviar_ticket y dile que el precio incluye IVA."}
        if acc.xb_sa_store_autonomous:
            # Se paga en línea con la liga (todo o el anticipo); al pagar, Odoo confirma el pedido solo.
            orden.write({"require_payment": True, "prepayment_percent": acc.xb_sa_store_prepayment or 1.0})
            tasa = self._xb_sa_store_usd_rate(company)
            res.update({"anticipo_para_apartar": round(orden.amount_total * (acc.xb_sa_store_prepayment or 1.0), 2),
                        "total_en_dolares": round(orden.amount_total / tasa, 2) if tasa else None,
                        "tipo_de_cambio_hoy": round(tasa, 4) if tasa else None,
                        "nota": "Es una cotización (borrador): todavía no aparta la piedra. Mándale el ticket con enviar_ticket. "
                                "Con la liga (o el QR del ticket) puede pagar en línea con tarjeta el total o el anticipo, y con eso "
                                "su pedido se confirma solo."})
        return res

    def _xb_sa_tool_cotizacion_a_la_medida(self, job, entrada):
        acc = self.wa_account_id.sudo()
        company = acc._xb_sa_company()
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return {"ok": False, "motivo": "No tengo a quien cotizar: pídele su nombre y vuelve a intentar."}
        nombre = " ".join((entrada.get("nombre_completo") or "").split())
        if not self._xb_sa_store_team():
            if len(nombre.split()) < 2:
                return {"ok": False, "motivo": "Falta su nombre completo (nombre y apellido) para poner la cotización a su nombre."}
            if nombre.lower() != (partner.name or "").strip().lower():
                partner.name = nombre
        pieza = (entrada.get("pieza") or "").strip()
        detalle = (entrada.get("detalle") or "").strip()
        if not (pieza and detalle):
            return {"ok": False, "motivo": "Faltan la pieza y el detalle de lo que pidió."}
        Propuesta = self.env["xb.support.proposal"].sudo()
        anterior = Propuesta.search([("kind", "=", "quote"), ("channel_id", "=", self.id), ("state", "=", "pending")], limit=1)
        opciones = [o.strip() for o in entrada.get("opciones") or [] if (o or "").strip()]
        renglones = [(0, 0, {"display_type": "line_note", "name": f"{pieza}\n{detalle}"})]
        for i, opcion in enumerate(opciones, 1):
            renglones.append((0, 0, {"display_type": "line_section", "name": f"Opción {i}: {opcion}"}))
        orden = anterior.sale_order_id.sudo() if anterior and anterior.sale_order_id.state == "draft" else self.env["sale.order"]
        if orden:
            orden.order_line.filtered(lambda l: l.display_type).unlink()
            orden.order_line = renglones
        else:
            orden = self.env["sale.order"].sudo().with_company(company).create({
                "partner_id": partner.id, "company_id": company.id,
                "pricelist_id": self._xb_sa_store_pricelist(company).id or False,
                "user_id": acc.xb_sa_sales_user_ids[:1].id or False, "origin": "Agente de WhatsApp (a la medida)",
                "order_line": renglones})
        fotos = self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("message_type", "=", "whatsapp_message"),
            ("create_date", ">=", fields.Datetime.now() - timedelta(days=7)), ("attachment_ids", "!=", False),
        ], order="id desc", limit=20).filtered(
            lambda m: m.wa_message_ids.filtered(lambda w: w.message_type == "inbound")).attachment_ids.filtered(
            lambda a: (a.mimetype or "").startswith("image/"))[:6]
        ya = set(self.env["ir.attachment"].sudo().search([("res_model", "=", "sale.order"), ("res_id", "=", orden.id)]).mapped("checksum"))
        copias = self.env["ir.attachment"]
        for foto in fotos.filtered(lambda a: a.checksum not in ya):
            copias |= foto.copy({"res_model": "sale.order", "res_id": orden.id})
        orden.message_post(body=Markup(tools.plaintext2html(f"Cotización a la medida pedida por WhatsApp:\n{pieza}\n{detalle}" +
                                                            (("\nOpciones: " + "; ".join(opciones)) if opciones else ""))),
                           attachment_ids=copias.ids, message_type="comment", subtype_xmlid="mail.mt_note")
        resumen = "\n".join(filter(None, [
            f"{partner.name} ({self.whatsapp_number})", detalle,
            ("Opciones: " + "; ".join(opciones)) if opciones else "",
            f"Fotos del cliente: {len(fotos)} (quedaron en la cotización)" if fotos else ""]))
        if anterior:
            anterior.write({"name": f"Cotización a la medida: {pieza}"[:120], "problem": resumen, "sale_order_id": orden.id})
            anterior._xb_ask_owner()
        else:
            Propuesta.create({"name": f"Cotización a la medida: {pieza}"[:120], "kind": "quote", "channel_id": self.id,
                              "partner_id": partner.id, "sale_order_id": orden.id,
                              "whatsapp_number": self.whatsapp_number, "problem": resumen})
        job.mode = "sales"
        return {"ok": True, "cotizacion": orden.name,
                "nota": "Quedó en manos del equipo: le ponen el precio y, en cuanto la autoricen, al cliente le llega sola por "
                        "aquí con su ticket y su liga para pagar. Díselo así, sin dar plazos ni precios. No uses pasar_a_humano "
                        "por esto."}

    def _xb_sa_store_b2b_pending(self):
        """Cliente sin verificar de una tienda solo para negocios: no ve precios ni compra."""
        categoria = self.wa_account_id.sudo().xb_sa_store_b2b_category_id
        if not categoria or self._xb_sa_store_team():
            return False
        partner = self.whatsapp_partner_id.sudo()
        return not (partner and categoria & (partner.category_id | partner.commercial_partner_id.category_id))

    def _xb_sa_store_hide_prices(self, res):
        """Quita los precios de una respuesta (cliente sin verificar)."""
        if isinstance(res, dict):
            return {k: self._xb_sa_store_hide_prices(v) for k, v in res.items() if k not in XB_B2B_PRICE_KEYS}
        if isinstance(res, list):
            return [self._xb_sa_store_hide_prices(v) for v in res]
        return res

    def _xb_sa_last_inbound_file(self, dias=2):
        """La última imagen o PDF que mandó el cliente en esta plática."""
        return self.env["mail.message"].sudo().search([
            ("model", "=", "discuss.channel"), ("res_id", "=", self.id), ("message_type", "=", "whatsapp_message"),
            ("create_date", ">=", fields.Datetime.now() - timedelta(days=dias)), ("attachment_ids", "!=", False),
        ], order="id desc", limit=10).filtered(
            lambda m: m.wa_message_ids.filtered(lambda w: w.message_type == "inbound")).attachment_ids.filtered(
            lambda a: (a.mimetype or "").startswith("image/") or a.mimetype == "application/pdf")[:1]

    def _xb_sa_tool_verificar_joyero(self, job, entrada):
        acc = self.wa_account_id.sudo()
        if not self._xb_sa_store_b2b_pending():
            return {"ok": True, "nota": "Ya está verificado: puedes darle precios."}
        Propuesta = self.env["xb.support.proposal"].sudo()
        if Propuesta.search_count([("kind", "=", "b2b"), ("channel_id", "=", self.id), ("state", "=", "pending")]):
            return {"ok": True, "nota": "Su verificación ya está en espera de aprobación; dile que en cuanto quede le avisas."}
        constancia = self._xb_sa_last_inbound_file(dias=7)
        if not constancia:
            return {"ok": False, "motivo": "No veo su constancia en la plática: pídele que la mande en foto o PDF."}
        partner = self.whatsapp_partner_id.sudo()
        if not partner:
            return {"ok": False, "motivo": "No tengo su contacto: pídele su nombre y vuelve a intentar."}
        copia = constancia.copy({"res_model": "res.partner", "res_id": partner.id,
                                 "name": f"Constancia fiscal {entrada.get('rfc') or ''} {constancia.name or ''}".strip()})
        resumen = "\n".join(filter(None, [
            f"{partner.name} ({self.whatsapp_number})",
            f"Joyería: {entrada.get('joyeria') or '—'} · {entrada.get('ciudad') or '—'}",
            f"Constancia: {entrada.get('razon_social') or '—'} · RFC {entrada.get('rfc') or '—'} · CP {entrada.get('codigo_postal') or '—'}",
            f"Actividades: {entrada.get('actividades') or '—'}",
            "✅ Actividad de joyería" if entrada.get("actividad_de_joyeria") else "⚠️ La actividad NO parece de joyería",
            f"Ojo: {entrada['observaciones']}" if (entrada.get("observaciones") or "").strip() else ""]))
        partner.message_post(body=Markup(tools.plaintext2html("Constancia de situación fiscal recibida por WhatsApp.\n" + resumen)),
                             attachment_ids=copia.ids, message_type="comment", subtype_xmlid="mail.mt_note")
        Propuesta.create({
            "name": f"Verificar joyería {entrada.get('joyeria') or partner.name}"[:120],
            "kind": "b2b", "channel_id": self.id, "partner_id": partner.id,
            "whatsapp_number": self.whatsapp_number, "problem": resumen,
        })
        job.mode = "sales"
        return {"ok": True, "nota": "Se mandó a aprobar. Dile que ya recibimos su constancia, que estamos verificando su negocio "
                                    "y que en cuanto quede le avisamos por aquí para pasarle precios. Mientras, puedes seguir "
                                    "platicando qué busca, sin precios."}

    def _xb_sa_store_usd_rate(self, company):
        """Pesos por dólar de hoy (de la compañía que lleva las tasas de USD)."""
        usd, mxn = self.env.ref("base.USD"), self.env.ref("base.MXN")
        tasa = self.env["res.currency.rate"].sudo().search([("currency_id", "=", usd.id)], order="name desc", limit=1)
        if not tasa:
            return 0.0
        return usd._convert(1.0, mxn, tasa.company_id or company, fields.Date.context_today(self), round=False)

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
            socios = partner.commercial_partner_id
            llave = xb_phone_key(self.whatsapp_number)
            if llave:  # el mismo celular capturado en otro contacto (p. ej. con espacios) también cuenta
                otros = self.env["res.partner"].sudo().search([("phone", "like", llave[-4:])]).filtered(
                    lambda r: xb_phone_key(r.phone) == llave)
                socios |= otros.mapped("commercial_partner_id")
            dominio.append(("partner_id", "child_of", socios.ids))
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
                "listo_para_recoger": bool(p.xb_ready_notified_date) if "xb_ready_notified_date" in p._fields else None,
                "renglones": self._xb_sa_store_order_lines(p)})
            if equipo:
                salida[-1]["entrega_prometida"] = entrega
        return {"ok": True, "pedidos": salida,
                "nota": "PRECIOS: cada renglón ya trae su precio con IVA y «total» es la suma de todos. Si la cotización trae varias "
                        "opciones (p. ej. zirconia y diamante), el total las suma juntas: di cuánto sale cada opción sumando sus "
                        "renglones y aclara que se escoge solo una. FECHAS: a un cliente con pedido confirmado NUNCA le des fecha de entrega ni "
                        "plazos (ni «aprox.», ni «unos días», ni «la próxima semana», ni contando los días de fabricación del modelo): "
                        "di que su pieza está en el taller y que la tienda le avisa por aquí en cuanto esté lista. Si pide una fecha o "
                        "la necesita para un día en especial, avisa con pasar_a_humano para que la tienda se la confirme. "
                        "Tampoco digas «no tiene fecha asignada» ni «no está registrada en el sistema» (suena a que nadie lo está "
                        "haciendo). Si «listo_para_recoger» es false, di que «todavía está en el taller», no que «no aparece»."}

    def _xb_sa_store_order_lines(self, orden):
        """Renglones con su precio CON IVA; las secciones (p. ej. «Opción 1») van como título."""
        salida = []
        for l in orden.order_line[:15]:
            texto = (l.name or "").split("\n")[0].strip() or l.product_id.display_name
            if l.display_type == "line_section":
                salida.append(f"— {texto} —")
            elif not l.display_type:
                salida.append(f"{l.product_uom_qty:g} × {texto}: ${l.price_total:,.2f} con IVA")
        return salida

    def _xb_sa_tool_enviar_ticket(self, job, entrada):
        if self._xb_sa_store_b2b_pending():
            return {"ok": False, "motivo": XB_B2B_NOTE}
        equipo = self._xb_sa_store_team()
        orden = self._xb_sa_store_order(entrada.get("pedido"), equipo)
        if not orden:
            return {"ok": False, "motivo": "No encuentro ese pedido entre los de esta persona."}
        png = orden.with_context(lang=orden.partner_id.lang or "es_MX")._xb_quotation_image()
        imagen = Image.open(io.BytesIO(png)).convert("RGB")
        salida = io.BytesIO()
        imagen.save(salida, "JPEG", quality=90)
        self._xb_sa_post_image(salida.getvalue(), f"{orden.name}.jpg",
                               f"{'Pedido' if orden.state == 'sale' else 'Cotización'} {orden.name}")
        return {"ok": True, "liga_cotizacion": self._xb_sa_store_share_url(orden),
                "nota": f"Ticket de {orden.name} enviado (total ${orden.amount_total:,.2f} con IVA). La liga abre la cotización en línea."}

    def _xb_sa_tool_revisar_certificado(self, job, entrada):
        Lote = self.env["stock.lot"].sudo()
        if "x_studio_url_stij" not in Lote._fields:
            return {"ok": False, "motivo": "Este sistema no tiene certificados ICERT."}
        numero = re.sub(r"\s", "", entrada.get("numero") or "")
        if numero:
            lotes = Lote.search(["|", ("x_studio_url_stij", "=", numero), ("name", "=", numero)], limit=3)
            if not lotes:
                return {"ok": True, "registrado": False,
                        "nota": "Ese número todavía no está dado de alta: la tienda tiene que activarlo. No lo des por un "
                                "error de la tarjeta; avisa con pasar_a_humano para que lo activen y dile que le avisamos."}
        else:
            partner = self.whatsapp_partner_id.sudo()
            if not partner:
                return {"ok": False, "motivo": "Pídele el número de la tarjeta."}
            campos = [c for c in ("x_studio_beneficiario", "dmn_claim_partner_id") if c in Lote._fields]
            dominio = ["|"] * (len(campos) - 1) + [(c, "child_of", partner.commercial_partner_id.id) for c in campos]
            lotes = Lote.search(dominio, limit=5) if campos else Lote
            if not lotes:
                return {"ok": True, "registrado": None,
                        "nota": "No hay piezas a su nombre con certificado; eso no significa que no exista. Pídele el número "
                                "de la tarjeta (impreso o en la pantalla que sale al acercarla) y revisa con él."}
        return {"ok": True, "piezas": [{
            "registrado": True,
            "activo": bool(l.x_studio_visor_activo) and (l.x_studio_estatus or "") == "Activo",
            "estatus": l.x_studio_estatus or "",
            "pieza": l.product_id.display_name,
        } for l in lotes],
            "nota": "Si «activo» es true, ya puede acercar la tarjeta a su celular y verá su pieza. Si es false, la tienda "
                    "tiene que activarla: avisa con pasar_a_humano. No des datos del dueño de la pieza."}

    def _xb_sa_tool_generar_pedido(self, job, entrada):
        if self._xb_sa_store_b2b_pending():
            return {"ok": False, "motivo": XB_B2B_NOTE}
        acc = self.wa_account_id.sudo()
        equipo = self._xb_sa_store_team()
        orden = self._xb_sa_store_order(entrada.get("pedido"), equipo)
        if not orden:
            return {"ok": False, "motivo": "No encuentro esa cotización."}
        if orden.state == "sale":
            return {"ok": True, "nota": f"{orden.name} ya es un pedido confirmado."}
        if orden.state == "cancel":
            return {"ok": False, "motivo": f"{orden.name} está cancelada."}
        if not equipo and acc.xb_sa_store_autonomous:
            return self._xb_sa_store_confirm_paid(job, orden, entrada.get("monto_comprobante"))
        if not equipo:
            self._xb_sa_notify(orden, acc.xb_sa_sales_user_ids | acc.xb_sa_support_user_ids,
                               f"El cliente pide confirmar el pedido {orden.name} (${orden.amount_total:,.2f}): revísalo y confírmalo.",
                               urgente=True, bandeja=True)
            job.mode = "sales"
            return {"ok": True, "confirmado": False,
                    "nota": "El pedido lo confirma la tienda. Ya se le avisó a una persona del equipo; dile al cliente que "
                            "le confirmarán su pedido y los datos para pagarlo. No digas que ya quedó confirmado."}
        orden.sudo().action_confirm()
        orden.message_post(body=Markup("Pedido confirmado por el agente de WhatsApp a petición de %s.") % equipo.name,
                           message_type="comment", subtype_xmlid="mail.mt_note")
        return {"ok": True, "confirmado": True, "nota": f"{orden.name} confirmado como pedido (${orden.amount_total:,.2f} con IVA)."}

    def _xb_sa_store_confirm_paid(self, job, orden, monto):
        """Cliente de una tienda que vende sola: con su comprobante se confirma el pedido y el equipo verifica el depósito."""
        acc = self.wa_account_id.sudo()
        monto = float(monto or 0)
        minimo = round(orden.amount_total * (acc.xb_sa_store_prepayment or 1.0), 2)
        comprobante = self._xb_sa_last_inbound_file()
        if not comprobante or monto <= 0:
            return {"ok": False, "motivo": "Para apartar necesito el comprobante de su pago (foto o PDF) aquí en la plática, "
                                           "o que pague en línea con la liga de su cotización."}
        if monto < minimo - 1:
            return {"ok": False, "motivo": f"El comprobante es por ${monto:,.2f} y para apartar se necesitan al menos "
                                           f"${minimo:,.2f}. Pregúntale si le falta algo por depositar."}
        orden.action_confirm()
        copia = comprobante.copy({"res_model": "sale.order", "res_id": orden.id})
        orden.message_post(body=Markup("Pedido confirmado por el agente de WhatsApp con el comprobante del cliente por "
                                       "<b>$%s</b>. Falta verificar el depósito.") % f"{monto:,.2f}",
                           attachment_ids=copia.ids, message_type="comment", subtype_xmlid="mail.mt_note")
        self._xb_sa_notify(orden, acc.xb_sa_sales_user_ids or acc.xb_sa_support_user_ids,
                           f"Pedido {orden.name} de {orden.partner_id.name} confirmado con su comprobante por ${monto:,.2f} "
                           f"(total ${orden.amount_total:,.2f}): verifica que el depósito sí llegó.", bandeja=True)
        job.mode = "sales"
        saldo = max(orden.amount_total - monto, 0)
        return {"ok": True, "confirmado": True, "pedido": orden.name, "pagado_segun_comprobante": monto,
                "saldo_por_liquidar": round(saldo, 2),
                "nota": "Ya es pedido y la piedra quedó apartada. Dile que el equipo verifica el depósito y, si algo no cuadra, "
                        "le escribimos. " + ("Si falta saldo, se liquida antes de la entrega." if saldo else "")}

    def _xb_sa_tool_avisar_a_la_tienda(self, job, entrada):
        acc = self.wa_account_id.sudo()
        asuntos = {"envio": "Cotizar envío", "factura": "Factura", "pago_en_oficina": "Visita a la oficina",
                   "entrega": "Entrega en persona", "otro": "Aviso"}
        orden = self._xb_sa_store_order(entrada.get("pedido"), self._xb_sa_store_team()) if entrada.get("pedido") else None
        partner = self.whatsapp_partner_id.sudo()
        texto = (f"{asuntos.get(entrada.get('asunto'), 'Aviso')} · {partner.name or self.whatsapp_number} "
                 f"({self.whatsapp_number}): {entrada.get('detalle') or ''}")
        self._xb_sa_notify(orden or self.xb_sa_lead_id.sudo() or job, acc.xb_sa_sales_user_ids or acc.xb_sa_support_user_ids, texto, bandeja=True)
        return {"ok": True, "nota": "Ya le llegó el aviso al equipo. Tú sigues atendiendo; no digas que pasaste la plática."}
