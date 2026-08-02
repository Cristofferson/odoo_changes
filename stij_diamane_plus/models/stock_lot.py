# -*- coding: utf-8 -*-
import logging
import re
import uuid

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Estatus STIJ que marcan una pieza como buscada (custodia comprometida).
DMN_THEFT_STATES = ("Robado", "Extraviado")


class StockLot(models.Model):
    _inherit = "stock.lot"

    # ----- Fase 2: registro de propiedad + garantía -------------------- #
    dmn_claim_token = fields.Char(
        string="Código de registro de propiedad", copy=False, readonly=True, index=True,
        help="Código de un solo uso, impreso en el ticket, con el que el comprador "
             "reclama la propiedad de la pieza en el visor.",
    )
    dmn_claim_state = fields.Selection(
        [("none", "Sin venta"), ("pending", "Pendiente de reclamar"), ("claimed", "Reclamada")],
        string="Estado de registro", default="none", copy=False, readonly=True,
    )
    dmn_claim_partner_id = fields.Many2one(
        "res.partner", string="Comprador (esperado)", copy=False, readonly=True,
    )
    dmn_purchase_date = fields.Date(
        string="Fecha de compra", copy=False, readonly=True,
    )
    dmn_warranty_until = fields.Date(
        string="Garantía hasta", compute="_compute_dmn_warranty", store=True,
    )

    @api.depends("dmn_purchase_date", "company_id.dmn_warranty_months")
    def _compute_dmn_warranty(self):
        for lot in self:
            if lot.dmn_purchase_date:
                months = lot.company_id.dmn_warranty_months or 12
                lot.dmn_warranty_until = lot.dmn_purchase_date + relativedelta(months=months)
            else:
                lot.dmn_warranty_until = False

    # ----- Fase 6: origen del alta + gema certificada de la pieza ------ #
    dmn_quick_origin = fields.Boolean(
        string="Alta rápida (mostrador)", copy=False, readonly=True, index=True,
        help="La pieza se registró desde /dmn/alta, no por el catálogo.",
    )
    dmn_quick_user_id = fields.Many2one(
        "res.users", string="Registrada por", copy=False, readonly=True,
    )
    dmn_quick_date = fields.Datetime(
        string="Fecha de registro", copy=False, readonly=True,
    )
    dmn_gem_lot_id = fields.Many2one(
        "stock.lot", string="Gema certificada", copy=False, index=True,
        domain="[('id', '!=', id)]",
        help="Gema ya registrada (con su propio certificado) que lleva montada "
             "esta joya. El visor de la joya muestra la gema, y el de la gema "
             "muestra la joya.",
    )
    dmn_jewel_lot_ids = fields.One2many(
        "stock.lot", "dmn_gem_lot_id", string="Joyas que la llevan montada",
    )

    def _dmn_is_gem(self):
        """Mismo criterio que el visor de STIJ: la categoría lleva 'Gema'."""
        self.ensure_one()
        return "Gema" in (self.product_id.categ_id.name or "")

    @api.model
    def _dmn_find_gem(self, code):
        """Busca una gema ya dada de alta por el código que se escanea (su
        plástico) o, en su defecto, por el nombre del lote."""
        code = (code or "").strip()
        if not code:
            return self.browse()
        lot = self.sudo().search([("x_studio_url_stij", "=", code)], limit=1)
        if not lot:
            lot = self.sudo().search([("name", "=", code)], limit=1)
        return lot if (lot and lot._dmn_is_gem()) else self.browse()

    @api.model
    def _dmn_gem_info(self, code):
        """Para el alta rápida: confirma al staff que el código tecleado es una
        gema registrada antes de crear la pieza."""
        lot = self._dmn_find_gem(code)
        if not lot:
            return {"ok": False, "error": _(
                "No encontré ninguna gema registrada con ese número.")}
        product = lot.product_id
        # Los datos gemológicos son de tipos distintos (quilataje float, pureza /
        # color / corte many2one a modelos de Studio): se normalizan a texto.
        detalles = []
        for fname, etiqueta in (
            ("x_studio_quilataje_c", _("%s ct")),
            ("x_studio_pureza_real", "%s"),
            ("x_studio_color_real", "%s"),
            ("x_studio_corte", "%s"),
        ):
            value = getattr(product, fname, False)
            if not value:
                continue
            if hasattr(value, "display_name"):
                value = value.display_name
            elif isinstance(value, float):
                value = ("%g" % value)
            detalles.append(etiqueta % value)
        return {
            "ok": True,
            "lot_id": lot.id,
            "name": product.display_name or lot.name,
            "detalle": " · ".join(detalles),
        }

    def _dmn_visor_pair(self):
        """Pareja joya/gema que el visor debe pintar. Devuelve (jewel, diamond)
        como productos, o False cada uno si no aplica.

        Sustituye a los productos tipo `combo` de STIJ, que en Odoo 19 no pueden
        llevar inventario ni número de serie (`type != 'consu'` fuerza
        `is_storable = False` y eso a su vez `tracking = 'none'`): una joya real
        con lote NO puede ser un combo.
        """
        self.ensure_one()
        if self._dmn_is_gem():
            jewel_lot = self.dmn_jewel_lot_ids[:1]
            return (jewel_lot.product_id if jewel_lot else False), False
        gem_lot = self.dmn_gem_lot_id
        return False, (gem_lot.product_id if gem_lot else False)

    # ----- Fase 3: dedicatoria secreta (regalo) ------------------------ #
    dmn_dedication_text = fields.Text(
        string="Dedicatoria", copy=False,
        help="Mensaje que aparece al abrir el visor de la pieza (regalo).",
    )
    dmn_dedication_from = fields.Char(string="Dedicatoria de", copy=False)
    dmn_dedication_image = fields.Image(
        string="Imagen de dedicatoria", max_width=1024, max_height=1024, copy=False,
    )
    dmn_dedication_visibility = fields.Selection(
        [("owner", "Solo el dueño"), ("public", "Pública")],
        string="Visibilidad de la dedicatoria", default="owner", copy=False,
    )

    def _dmn_has_dedication(self):
        self.ensure_one()
        return bool(self.dmn_dedication_text or self.dmn_dedication_image)

    def _dmn_dedication_is_visible_to(self, user, lot_in_session):
        """Reglas de gating: pública la ve quien tenga la pieza en sesión; privada
        solo el dueño logueado. Así un regalo íntimo no se filtra a desconocidos."""
        self.ensure_one()
        if not self._dmn_has_dedication():
            return False
        if self.dmn_dedication_visibility == "public":
            return bool(lot_in_session)
        # 'owner': solo el dueño autenticado
        if user and not user._is_public():
            owner = self.x_studio_beneficiario
            if owner and user.partner_id and owner.id == user.partner_id.id:
                return True
        return False

    def _dmn_dedication_payload(self):
        self.ensure_one()
        image = None
        if self.dmn_dedication_image:
            raw = self.dmn_dedication_image
            b64 = raw.decode() if isinstance(raw, bytes) else raw
            image = "data:image/png;base64,%s" % b64
        return {
            "text": self.dmn_dedication_text or "",
            "from": self.dmn_dedication_from or "",
            "image": image,
        }

    # ----- Fase 0: vista de cliente por pieza --------------------------- #
    dmn_view_count = fields.Integer(
        string="Vistas de cliente", readonly=True, copy=False, default=0,
        help="Número de veces que un cliente (no personal) abrió el visor de esta pieza.",
    )
    dmn_last_customer_view = fields.Datetime(
        string="Última vista de cliente", readonly=True, copy=False,
    )

    # ----- Fase 4: heatmap interés vs conversión ----------------------- #
    dmn_sold_flag = fields.Integer(
        string="Vendida (0/1)", compute="_compute_dmn_sold_flag", store=True,
        help="1 si la pieza se vendió (tiene registro de propiedad). Medible en el "
             "tablero como número de piezas convertidas.",
    )
    dmn_categ_id = fields.Many2one(
        "product.category", string="Categoría", related="product_id.categ_id",
        store=True,
    )

    @api.depends("dmn_claim_state")
    def _compute_dmn_sold_flag(self):
        for lot in self:
            lot.dmn_sold_flag = 1 if lot.dmn_claim_state in ("pending", "claimed") else 0

    # ----- Fase 1: trampa de pieza robada ------------------------------- #
    dmn_last_theft_alert = fields.Datetime(
        string="Última alerta de robo enviada", readonly=True, copy=False,
        help="Marca de tiempo de la última notificación de avistamiento (anti-spam).",
    )
    dmn_theft_sighting_count = fields.Integer(
        string="Avistamientos", readonly=True, copy=False, default=0,
    )

    # ------------------------------------------------------------------- #
    #  Fase 0
    # ------------------------------------------------------------------- #
    def _dmn_count_view(self, request):
        """Suma una vista de CLIENTE a la pieza, con dedup por sesión para no
        inflar el contador con refrescos. Nunca rompe la request."""
        self.ensure_one()
        try:
            minutes = self.company_id.dmn_view_dedup_minutes or 30
            key = "dmn_viewed_%d" % self.id
            now = fields.Datetime.now()
            last = request.session.get(key)
            if last:
                try:
                    last_dt = fields.Datetime.to_datetime(last)
                    if last_dt and (now - last_dt).total_seconds() < minutes * 60:
                        return  # ya contada en esta sesión hace poco
                except Exception:
                    pass
            request.session[key] = fields.Datetime.to_string(now)
            self.sudo().write({
                "dmn_view_count": (self.dmn_view_count or 0) + 1,
                "dmn_last_customer_view": now,
            })
        except Exception:  # pragma: no cover
            _logger.exception("DMN: no se pudo contar la vista del lote %s", self.id)

    # ------------------------------------------------------------------- #
    #  Fase 1
    # ------------------------------------------------------------------- #
    def _dmn_record_theft_sighting(self, request):
        """Registra el avistamiento de una pieza buscada en el ledger STIJ
        (scan_alert) con la metadata disponible server-side. Devuelve el dict
        de datos del avistamiento para la notificación."""
        self.ensure_one()
        ip = request.httprequest.remote_addr
        ua = request.httprequest.user_agent
        os_found = (ua.platform if ua else None) or "desconocido"
        geo = request.geoip or {}
        city = getattr(geo, "city", None) or "Desconocida"
        country = getattr(geo, "country_name", None) or "Desconocido"
        when = fields.Datetime.now()

        note = _("Avistamiento de pieza %(estatus)s · IP %(ip)s · %(city)s, %(country)s · %(os)s") % {
            "estatus": self.x_studio_estatus or "",
            "ip": ip or "?",
            "city": city,
            "country": country,
            "os": os_found,
        }
        try:
            self.env["stij.lot.event"].sudo()._record(
                self, "scan_alert",
                source="visor_web",
                ip_address=ip,
                partner_id=self.x_studio_beneficiario.id if self.x_studio_beneficiario else False,
                note=note,
            )
            self.sudo().write({
                "dmn_theft_sighting_count": (self.dmn_theft_sighting_count or 0) + 1,
            })
        except Exception:  # pragma: no cover
            _logger.exception("DMN: no se pudo registrar el avistamiento del lote %s", self.id)
        return {
            "ip": ip, "os": os_found, "city": city, "country": country,
            "when": when, "estatus": self.x_studio_estatus,
        }

    def _dmn_theft_recipients(self):
        """Correos a alertar: dueño (beneficiario) + tienda + extras de config."""
        self.ensure_one()
        emails = []
        owner = self.x_studio_beneficiario
        if owner and owner.email:
            emails.append(owner.email)
        company = self.company_id
        if company.email:
            emails.append(company.email)
        extra = (company.dmn_theft_alert_extra_emails or "").replace(";", ",")
        emails += [e.strip() for e in extra.split(",") if e.strip()]
        # dedup conservando orden
        seen, out = set(), []
        for e in emails:
            if e not in seen:
                seen.add(e)
                out.append(e)
        return out

    def _dmn_theft_map_link(self, sighting):
        """Link a un mapa del avistamiento: usa la última geolocalización precisa
        del visor si existe; si no, la ciudad/país de la geoip."""
        self.ensure_one()
        loc = self.env["stij.location.history"].sudo().search(
            [("lot_id", "=", self.id)], order="date desc", limit=1
        )
        if loc and loc.latitude and loc.longitude:
            return "https://www.google.com/maps/search/?api=1&query=%s,%s" % (
                loc.latitude, loc.longitude,
            )
        query = ", ".join([p for p in (sighting.get("city"), sighting.get("country")) if p])
        if query:
            from urllib.parse import quote
            return "https://www.google.com/maps/search/?api=1&query=%s" % quote(query)
        return ""

    def _dmn_notify_theft(self, sighting):
        """Envía la alerta proactiva (correo) al dueño y la tienda, con throttle
        por pieza para no spamear ante escaneos repetidos."""
        self.ensure_one()
        company = self.company_id
        if not company.dmn_theft_alert_email:
            return
        try:
            throttle = company.dmn_theft_alert_throttle_minutes or 15
            now = fields.Datetime.now()
            if self.dmn_last_theft_alert:
                if (now - self.dmn_last_theft_alert).total_seconds() < throttle * 60:
                    return
            recipients = self._dmn_theft_recipients()
            if not recipients:
                return
            map_link = self._dmn_theft_map_link(sighting)
            subject = _("⚠️ Alerta: pieza %(estatus)s escaneada — %(pieza)s") % {
                "estatus": (sighting.get("estatus") or "").upper(),
                "pieza": self.name or self.product_id.display_name or "",
            }
            body = _(
                "<p>Se escaneó una pieza reportada como <b>%(estatus)s</b>.</p>"
                "<ul>"
                "<li><b>Pieza:</b> %(pieza)s (%(producto)s)</li>"
                "<li><b>Dueño:</b> %(owner)s</li>"
                "<li><b>Cuándo:</b> %(when)s</li>"
                "<li><b>IP:</b> %(ip)s</li>"
                "<li><b>Ubicación aproximada:</b> %(city)s, %(country)s</li>"
                "<li><b>Dispositivo:</b> %(os)s</li>"
                "</ul>"
                "%(map)s"
                "<p style='color:#888'>La ubicación precisa puede llegar después si el "
                "visitante concede su geolocalización.</p>"
            ) % {
                "estatus": sighting.get("estatus") or "",
                "pieza": self.name or "",
                "producto": self.product_id.display_name or "",
                "owner": self.x_studio_beneficiario.display_name if self.x_studio_beneficiario else _("sin asignar"),
                "when": fields.Datetime.to_string(sighting.get("when") or now),
                "ip": sighting.get("ip") or "?",
                "city": sighting.get("city") or "?",
                "country": sighting.get("country") or "?",
                "os": sighting.get("os") or "?",
                "map": ("<p><a href='%s'>Ver en el mapa</a></p>" % map_link) if map_link else "",
            }
            self.env["mail.mail"].sudo().create({
                "subject": subject,
                "body_html": body,
                "email_to": ",".join(recipients),
                "auto_delete": True,
            }).send()
            self.sudo().write({"dmn_last_theft_alert": now})
        except Exception:  # pragma: no cover
            _logger.exception("DMN: no se pudo enviar la alerta de robo del lote %s", self.id)

    # ------------------------------------------------------------------- #
    #  Fase 2 — registro de propiedad
    # ------------------------------------------------------------------- #
    def _dmn_generate_claim(self, partner):
        """Genera el código de registro de propiedad para la pieza recién vendida.
        Atar la propiedad a la COMPRA (este token impreso en el ticket), no a quien
        toque la pieza, es lo que cierra el viejo agujero de toma de posesión (C1)."""
        self.ensure_one()
        self.sudo().write({
            "dmn_claim_token": uuid.uuid4().hex,
            "dmn_claim_state": "pending",
            "dmn_claim_partner_id": partner.id if partner else False,
            "dmn_purchase_date": fields.Date.context_today(self),
        })

    @api.model
    def _dmn_try_claim(self, token, name, email=None, phone=None):
        """Registra al comprador como dueño validando el token de un solo uso.
        Llamado por el controlador público /dmn/claim."""
        token = (token or "").strip()
        name = (name or "").strip()
        if not token:
            return {"ok": False, "error": _("Falta el código de registro.")}
        if not name:
            return {"ok": False, "error": _("Falta tu nombre.")}
        lot = self.sudo().search(
            [("dmn_claim_token", "=", token), ("dmn_claim_state", "=", "pending")], limit=1
        )
        if not lot:
            return {"ok": False, "error": _("Código inválido o ya utilizado.")}

        partner = self.env["res.partner"]
        email = (email or "").strip()
        if email:
            partner = partner.sudo().search([("email", "=ilike", email)], limit=1)
        if not partner:
            partner = self.env["res.partner"].sudo().create({
                "name": name,
                "email": email or False,
                "phone": (phone or "").strip() or False,
            })
        # El write de x_studio_beneficiario dispara el hook de STIJ -> owner_changed.
        lot.sudo().with_context(stij_event_source="visor_web").write({
            "x_studio_beneficiario": partner.id,
            "x_studio_estatus": "Activo",
            "dmn_claim_state": "claimed",
        })
        return {
            "ok": True,
            "partner": partner.name,
            "warranty_until": fields.Date.to_string(lot.dmn_warranty_until) if lot.dmn_warranty_until else None,
        }

    # ------------------------------------------------------------------- #
    #  Fase 5 — alta rápida de pieza STIJ (registro de mostrador)
    # ------------------------------------------------------------------- #
    # Categorías que NO son joya: no deben ofrecerse como "tipo de pieza".
    _DMN_NON_JEWEL = ("Gasto", "Servicio", "Envíos", "Envios", "XUBAX",
                      "Reparación", "Reparacion")

    @api.model
    def _dmn_categ_is_ring(self, categ):
        """La Medida (talla) solo aplica a la familia 'Anillo' (incluye argolla,
        churumbela, montadura..., que cuelgan de Anillo)."""
        if not categ:
            return False
        return (categ.complete_name or categ.name or "").strip().lower().startswith("anillo")

    @api.model
    def _dmn_attr_values(self, attr_name):
        """Valores del atributo de producto canónico (Metal, Medida) para los
        desplegables; resuelto por NOMBRE (los ids difieren entre BDs)."""
        attr = self.env["product.attribute"].sudo().search(
            [("name", "=", attr_name)], limit=1)
        return [{"id": v.id, "name": v.name} for v in attr.value_ids] if attr else []

    @api.model
    def _dmn_quick_form_options(self):
        """Opciones de los desplegables del alta rápida: tipos de joya
        (categorías, marcando cuáles son anillo para mostrar la Medida), metales
        y medidas (de los atributos de producto)."""
        Categ = self.env["product.category"].sudo()
        tipos = []
        for c in Categ.search([], order="complete_name"):
            cn = c.complete_name or c.name or ""
            if c.name in self._DMN_NON_JEWEL or "gema" in cn.lower():
                continue
            tipos.append({"id": c.id, "name": cn, "is_ring": self._dmn_categ_is_ring(c)})
        return {
            "tipos": tipos,
            "metales": self._dmn_attr_values("Metal"),
            "medidas": self._dmn_attr_values("Medida"),
        }

    @api.model
    def _dmn_quick_categ(self):
        """Fallback de categoría cuando no se eligió tipo: la configurada en la
        compañía o la primera no-'Gema'."""
        categ = self.env.company.dmn_quick_categ_id
        if categ and "gema" not in (categ.name or "").lower():
            return categ
        return self.env["product.category"].sudo().search(
            [("name", "not ilike", "gema")], order="id", limit=1
        )

    @staticmethod
    def _dmn_split_b64(data):
        """De un data-url (data:image/png;base64,...) saca (mimetype, base64 limpio)."""
        mime = "image/png"
        if data and isinstance(data, str) and data[:5] == "data:":
            if ";" in data:
                mime = data[5:data.index(";")] or "image/png"
            if "," in data:
                data = data.split(",", 1)[1]
        return mime, data

    # Ley (pureza) por kilataje, según la convención histórica de Anello.
    _DMN_LEY_BY_KT = {"24": 1.0, "22": 0.917, "21": 0.9, "18": 0.75,
                      "14": 0.585, "10": 0.417, "8": 0.333}

    @api.model
    def _dmn_parse_metal(self, value_name):
        """Descompone el valor del atributo Metal (ej. 'Oro blanco 14Kt') en
        base/color/kilataje/ley, igual que el alta tradicional captura a mano.
        Devuelve {base, color, kilataje, ley}."""
        name = (value_name or "").strip()
        low = name.lower()
        res = {"base": "", "color": "", "kilataje": "", "ley": 0.0}
        if not name:
            return res
        # Metal base.
        if low.startswith("oro") or "imitación oro" in low or "imitacion oro" in low:
            res["base"] = "Oro"
        elif low.startswith("plata") or "imitación plata" in low or "imitacion plata" in low:
            res["base"] = "Plata"
        elif low.startswith("platino"):
            res["base"] = "Platino"
        else:
            res["base"] = name.split()[0].capitalize()
        # Color del metal.
        for key, val in (("amarillo", "Amarillo"), ("blanco", "Blanco"),
                         ("rosa", "Rosa"), ("bitono", "Bitono"),
                         ("tricolor", "Tricolor"), ("florentino", "Florentino")):
            if key in low:
                res["color"] = val
                break
        if not res["color"] and res["base"] in ("Plata", "Platino"):
            res["color"] = "Plateado"
        # Kilataje + ley.
        mk = re.search(r"(\d+)\s*kt", low)
        if mk:
            res["kilataje"] = "%sKt" % mk.group(1)
            res["ley"] = self._DMN_LEY_BY_KT.get(mk.group(1), 0.0)
        if not res["ley"]:
            mp = re.search(r"\((\d{3})\)", low)  # ej. Plata (925), Platino (999)
            if mp:
                res["ley"] = int(mp.group(1)) / 1000.0
            elif res["base"] == "Plata":
                res["ley"] = 0.925
            elif res["base"] == "Platino":
                res["ley"] = 0.999
        return res

    @api.model
    def _dmn_ai_describe(self, vals):
        """Sugiere la 'Descripción STIJ' a partir de la primera foto usando visión
        de OpenAI (reusa la clave `ai.openai_key` de Odoo). Solo PROPONE texto: el
        staff lo revisa y edita antes de guardar. Nunca crea nada."""
        imagenes = vals.get("imagenes") or []
        if not imagenes and vals.get("foto"):
            imagenes = [vals.get("foto")]
        if not imagenes:
            return {"ok": False, "error": _("Sube al menos una foto para describir la pieza.")}
        key = self.env["ir.config_parameter"].sudo().get_param("ai.openai_key")
        if not key:
            return {"ok": False, "error": _("No hay clave de IA configurada (ai.openai_key).")}

        raw = imagenes[0]
        if not (isinstance(raw, str) and raw[:5] == "data:"):
            raw = "data:image/png;base64," + (raw or "")

        contexto = (
            "Datos conocidos de la pieza -> Tipo: %s; Metal: %s; Peso: %s; "
            "Medida: %s; Nombre interno: %s."
            % (vals.get("tipo") or "?", vals.get("metal") or "?",
               vals.get("peso") or "?", vals.get("medida") or "?",
               vals.get("joya") or "?")
        )
        system = (
            "Eres un catalogador de joyería que redacta una descripción OBJETIVA y "
            "FACTUAL para la ficha técnica (pasaporte STIJ) de una pieza. A partir de la "
            "FOTO y de los datos conocidos, describe únicamente lo observable: tipo de "
            "pieza, metal y color, forma/estructura, gemas o aplicaciones visibles, "
            "acabado y disposición. Español neutro, en tercera persona, 2 a 3 frases en "
            "prosa (sin listas). PROHIBIDO usar lenguaje publicitario o de venta, "
            "superlativos, juicios de valor o emociones (evita palabras como 'elegante', "
            "'hermosa', 'exquisita', 'única', 'lujo', 'perfecta', 'ideal para'). NO "
            "inventes quilatajes, pesos, leyes, materiales ni certificados; si un dato no "
            "es visible ni conocido, omítelo. Respeta los datos conocidos que te doy."
        )
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": contexto + " Describe objetivamente esta pieza para su ficha técnica."},
                    {"type": "image_url", "image_url": {"url": raw, "detail": "low"}},
                ]},
            ],
            "max_tokens": 320,
            "temperature": 0.2,
        }
        try:
            import requests as _rq
            resp = _rq.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": "Bearer %s" % key,
                         "Content-Type": "application/json"},
                json=payload, timeout=30,
            )
            data = resp.json()
            if resp.status_code != 200:
                msg = (data.get("error") or {}).get("message") or ("HTTP %s" % resp.status_code)
                return {"ok": False, "error": _("IA: %s") % msg}
            text = (data["choices"][0]["message"]["content"] or "").strip()
            return {"ok": True, "descripcion": text}
        except Exception:  # pragma: no cover
            _logger.exception("DMN: fallo al describir con IA")
            return {"ok": False, "error": _("No se pudo conectar con la IA.")}

    @api.model
    def _dmn_ensure_variant(self, product):
        """Devuelve la variante de la joya recién creada, creándola si hace falta.

        Los atributos Metal y Medida de esta base son `dynamic` (así se bajaron
        las decenas de miles de variantes que cargaba el POS). Con atributos
        dinámicos Odoo NO genera la variante al crear la plantilla:
        `product_variant_id` queda vacío y el lote se quedaría sin producto.
        """
        # Los valores de las líneas de atributo se materializan al vaciar el
        # buffer del ORM. Sin esto la combinación se lee VACÍA y Odoo crearía
        # una variante suelta, sin metal ni medida.
        product.env.flush_all()
        product.invalidate_recordset()
        if product.product_variant_id:
            return product.product_variant_id
        combination = product.attribute_line_ids.product_template_value_ids
        try:
            if combination:
                product._create_product_variant(combination, log_warning=True)
                product.invalidate_recordset(["product_variant_id", "product_variant_ids"])
        except Exception:  # pragma: no cover
            _logger.exception("DMN: falló la variante de la joya %s", product.id)
        if product.product_variant_id:
            return product.product_variant_id
        # Red de seguridad: sin líneas de atributo el core sí crea la variante
        # base. Vale más registrar la pieza que perder el alta por el metal.
        _logger.warning(
            "DMN: la joya %s no generó variante con sus atributos; se crea sin ellos.",
            product.id)
        product.attribute_line_ids.unlink()
        product.invalidate_recordset(["product_variant_id", "product_variant_ids"])
        return product.product_variant_id

    @api.model
    def _dmn_quick_create(self, vals):
        """Alta rápida de una pieza STIJ desde el mostrador: con los datos mínimos
        crea la joya (producto) + el lote ya escaneable (visor activo, Activo) y le
        liga las imágenes. Devuelve la URL del visor y el id para el QR.

        vals: {joya, categ_id, metal_value_id, medida_value_id, peso, codigo, imagenes[]}
        - joya            -> nombre/descripción del producto (obligatorio)
        - codigo          -> nº de pieza = nº de plástico = x_studio_url_stij (obligatorio, único)
        - categ_id        -> tipo de joya (categoría); si falta, fallback no-Gema
        - metal_value_id  -> valor del atributo Metal (dropdown)
        - medida_value_id -> valor del atributo Medida (solo anillos)
        - peso            -> texto libre (ej. "4.7 gr")
        - imagenes        -> lista de data-urls (varias)
        - gema_codigo     -> nº de una gema YA registrada, para ligarla (opcional)
        """
        joya = (vals.get("joya") or "").strip()
        codigo = (vals.get("codigo") or vals.get("plastico") or "").strip()
        peso = (vals.get("peso") or "").strip()
        metal_value_id = vals.get("metal_value_id") or False
        medida_value_id = vals.get("medida_value_id") or False
        medida_text = (vals.get("medida_text") or "").strip()
        ancho = (vals.get("ancho") or "").strip()
        grosor = (vals.get("grosor") or "").strip()
        descripcion = (vals.get("descripcion") or "").strip()
        categ_id = vals.get("categ_id") or False
        gema_codigo = (vals.get("gema_codigo") or "").strip()
        imagenes = vals.get("imagenes") or []
        if not imagenes and vals.get("foto"):  # compat: una sola foto
            imagenes = [vals.get("foto")]

        if not joya:
            return {"ok": False, "error": _("Falta el nombre/descripción de la joya.")}
        if not codigo:
            return {"ok": False, "error": _("Falta el número de pieza (el código del plástico que se escanea).")}

        # El número (plástico) es la llave del visor: debe ser único.
        dup = self.sudo().search([("x_studio_url_stij", "=", codigo)], limit=1)
        if dup:
            return {"ok": False, "error": _("Ese número ya está registrado en otra pieza.")}

        # Gema montada: se valida ANTES de crear nada, para no dejar a medias una
        # pieza por un número mal tecleado.
        gem_lot = self.browse()
        if gema_codigo:
            gem_lot = self._dmn_find_gem(gema_codigo)
            if not gem_lot:
                return {"ok": False, "error": _(
                    "No encontré ninguna gema registrada con el número %s.") % gema_codigo}

        Categ = self.env["product.category"].sudo()
        categ = Categ.browse(int(categ_id)) if categ_id else Categ
        if not categ or not categ.exists():
            categ = self._dmn_quick_categ()
        is_ring = self._dmn_categ_is_ring(categ)

        AttrVal = self.env["product.attribute.value"].sudo()
        metal_val = AttrVal.browse(int(metal_value_id)) if metal_value_id else AttrVal
        medida_val = AttrVal.browse(int(medida_value_id)) if (medida_value_id and is_ring) else AttrVal

        # Imágenes: data-url -> (mimetype, base64).
        imgs = []
        for raw in imagenes:
            mime, clean = self._dmn_split_b64(raw)
            if clean:
                imgs.append((mime, clean))

        Product = self.env["product.template"].sudo()
        prod_vals = {
            "name": joya,
            "categ_id": categ.id,
            "is_storable": True,
            "tracking": "serial",
        }
        # --- Descomposición del Metal (como el alta tradicional) --- #
        metal_info = self._dmn_parse_metal(metal_val.name if (metal_val and metal_val.exists()) else "")
        ley = metal_info["ley"]

        # --- Peso de oro puro = peso * ley --- #
        peso_num = 0.0
        mnum = re.search(r"\d+(?:\.\d+)?", (peso or "").replace(",", "."))
        if mnum:
            peso_num = float(mnum.group())
        peso_oro = ("%.3f gr" % (peso_num * ley)) if (peso_num and ley) else ""

        # Campos del producto que rellena el alta tradicional (guardados si existen).
        studio = {
            "x_studio_metal_1": metal_info["base"],        # visor: Metal base (ej. "Oro")
            "x_studio_color_metal": metal_info["color"],
            "x_studio_kilataje_metal": metal_info["kilataje"],
            "x_studio_ley": (("%g" % ley) if ley else ""),
            "x_studio_ley_float": ley,
            "x_studio_tipo_joya": (categ.name or ""),       # = categoría
            "x_studio_peso_joya": peso,
            "x_studio_peso_de_oro_puro": peso_oro,
            "x_studio_descripcion": (descripcion or joya),  # IA (revisada) o el nombre
            "x_studio_ancho_joya": ancho,
            "x_studio_grosor_joya": grosor,
        }
        # Medida: anillo -> valor del atributo; otro tipo -> texto libre. Mismo campo.
        if is_ring and medida_val and medida_val.exists():
            studio["x_studio_medida_joya"] = medida_val.name
        elif medida_text:
            studio["x_studio_medida_joya"] = medida_text
        for fname, fval in studio.items():
            if fval not in (None, "", False) and fname in Product._fields:
                prod_vals[fname] = fval
        # Id de joya: secuencia automática.
        if "x_studio_id_joya" in Product._fields:
            id_joya = self.env["ir.sequence"].sudo().next_by_code("dmn.stij.id_joya")
            if id_joya:
                prod_vals["x_studio_id_joya"] = id_joya
        if imgs:
            prod_vals["image_1920"] = imgs[0][1]
        # Atributo real (como el alta tradicional).
        attr_lines = []
        for val in (metal_val, medida_val):
            if val and val.exists() and val.attribute_id:
                attr_lines.append((0, 0, {
                    "attribute_id": val.attribute_id.id,
                    "value_ids": [(6, 0, [val.id])],
                }))
        if attr_lines:
            prod_vals["attribute_line_ids"] = attr_lines
        product = Product.create(prod_vals)

        variant = self._dmn_ensure_variant(product)
        if not variant:
            return {"ok": False, "error": _(
                "No se pudo preparar la joya en el catálogo. Avisa a sistemas.")}

        lot_vals = {
            "name": codigo,
            "product_id": variant.id,
            "company_id": self.env.company.id,
            # Origen del alta: sin esto una pieza de mostrador es
            # indistinguible de una capturada por el catálogo.
            "dmn_quick_origin": True,
            "dmn_quick_user_id": self.env.user.id,
            "dmn_quick_date": fields.Datetime.now(),
        }
        if gem_lot:
            lot_vals["dmn_gem_lot_id"] = gem_lot.id
        for fname, fval in (
            ("x_studio_url_stij", codigo),
            ("x_studio_estatus", "Activo"),
            ("x_studio_visor_activo", True),
            # Encender los módulos del visor para que se vea completo.
            ("x_studio_informacion_general", True),
            ("x_studio_galeria", True),
            ("x_studio_publicar_imagenes_1", True),
        ):
            if fname in self._fields:
                lot_vals[fname] = fval
        lot = self.sudo().create(lot_vals)

        # Galería del visor: una stij.lot.image por imagen.
        if imgs and "stij.lot.image" in self.env:
            for seq, (mime, clean) in enumerate(imgs, start=1):
                try:
                    self.env["stij.lot.image"].sudo().create({
                        "lot_id": lot.id,
                        "image": clean,
                        "name": ("%s %s" % (joya, seq)) if len(imgs) > 1 else joya,
                        "mimetype": mime,
                        "sequence": seq,
                    })
                except Exception:  # pragma: no cover
                    _logger.exception("DMN: no se pudo ligar imagen %s al lote %s", seq, lot.id)

        # Ledger STIJ: el alta queda como el primer eslabón de la trazabilidad.
        note = _("Alta rápida desde el mostrador.")
        if gem_lot:
            note = "%s %s" % (note, _("Gema montada: %s.") % (
                gem_lot.product_id.display_name or gem_lot.name))
        self.env["stij.lot.event"].sudo()._record(
            lot, "dmn_quick_created",
            user_id=self.env.user.id,
            company_id=lot.company_id.id,
            note=note,
            source="visor_web",
        )

        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        from urllib.parse import quote
        visor_url = "%s/stijid?id=%s" % (base, quote(codigo, safe=""))
        return {
            "ok": True,
            "lot_id": lot.id,
            "plastico": codigo,
            "visor_url": visor_url,
            "joya": joya,
        }
