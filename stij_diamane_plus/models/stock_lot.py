# -*- coding: utf-8 -*-
import logging
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
    @api.model
    def _dmn_quick_categ(self):
        """Categoría para la joya recién creada: la configurada en la compañía o,
        en su defecto, la primera categoría que NO sea 'Gema' (para que el visor la
        trate como joya y muestre Metal/Medida, no como diamante)."""
        categ = self.env.company.dmn_quick_categ_id
        if categ and "gema" not in (categ.name or "").lower():
            return categ
        return self.env["product.category"].sudo().search(
            [("name", "not ilike", "gema")], order="id", limit=1
        )

    @staticmethod
    def _dmn_clean_b64(data):
        """Quita el prefijo data-url (data:image/png;base64,) si viene del front."""
        if data and isinstance(data, str) and "," in data and data[:5] == "data:":
            return data.split(",", 1)[1]
        return data

    @api.model
    def _dmn_quick_create(self, vals):
        """Alta rápida de una pieza STIJ desde el mostrador: con los datos mínimos
        crea la joya (producto) + el lote ya escaneable (visor activo, Activo) y le
        liga la foto. Devuelve la URL del visor y el id para el QR.

        vals: {joya, metal, medidas, pieza, plastico, foto}
        - joya     -> nombre del producto (obligatorio)
        - plastico -> x_studio_url_stij = lo que se escanea (obligatorio, único)
        - pieza    -> número de lote/serie (si falta, se usa el plástico)
        - metal/medidas/foto -> opcionales
        """
        joya = (vals.get("joya") or "").strip()
        plastico = (vals.get("plastico") or "").strip()
        pieza = (vals.get("pieza") or "").strip()
        metal = (vals.get("metal") or "").strip()
        medidas = (vals.get("medidas") or "").strip()
        foto_raw = vals.get("foto")
        foto_mime = "image/png"
        if foto_raw and isinstance(foto_raw, str) and foto_raw[:5] == "data:" and ";" in foto_raw:
            foto_mime = foto_raw[5:foto_raw.index(";")] or "image/png"
        foto = self._dmn_clean_b64(foto_raw)

        if not joya:
            return {"ok": False, "error": _("Falta el nombre/descripción de la joya.")}
        if not plastico:
            return {"ok": False, "error": _("Falta el número de plástico (el código que se escanea).")}

        # El número de plástico debe ser único: es la llave del visor.
        dup = self.sudo().search([("x_studio_url_stij", "=", plastico)], limit=1)
        if dup:
            return {"ok": False, "error": _("Ese número de plástico ya está registrado en otra pieza.")}

        Product = self.env["product.template"].sudo()
        prod_vals = {
            "name": joya,
            "categ_id": (self._dmn_quick_categ().id or False),
            "is_storable": True,
            "tracking": "serial",
        }
        # Campos Studio de la joya (guardados: pueden no existir en otra BD).
        if metal and "x_studio_metal_1" in Product._fields:
            prod_vals["x_studio_metal_1"] = metal
        if medidas and "x_studio_medida_joya" in Product._fields:
            prod_vals["x_studio_medida_joya"] = medidas
        # La descripción (= la joya) la pinta el visor en "Información de la Joya".
        if "x_studio_descripcion" in Product._fields:
            prod_vals["x_studio_descripcion"] = joya
        if foto:
            prod_vals["image_1920"] = foto
        product = Product.create(prod_vals)

        lot_vals = {
            "name": pieza or plastico,
            "product_id": product.product_variant_id.id,
            "company_id": self.env.company.id,
        }
        for fname, fval in (
            ("x_studio_url_stij", plastico),
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

        # Foto en la galería del visor (stij.lot.image) para que se muestre.
        if foto and "stij.lot.image" in self.env:
            try:
                self.env["stij.lot.image"].sudo().create({
                    "lot_id": lot.id,
                    "image": foto,
                    "name": joya,
                    "mimetype": foto_mime,
                    "sequence": 1,
                })
            except Exception:  # pragma: no cover
                _logger.exception("DMN: no se pudo ligar la foto al lote %s", lot.id)

        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        from urllib.parse import quote
        visor_url = "%s/stijid?id=%s" % (base, quote(plastico, safe=""))
        return {
            "ok": True,
            "lot_id": lot.id,
            "plastico": plastico,
            "visor_url": visor_url,
            "joya": joya,
        }
