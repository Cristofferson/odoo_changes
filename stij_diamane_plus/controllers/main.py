# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request
from odoo.addons.stij_website.controllers.main import StijWebsite

_logger = logging.getLogger(__name__)

DMN_THEFT_STATES = ("Robado", "Extraviado")


class StijWebsitePlus(StijWebsite):
    """Extiende el visor de STIJ sin tocar su repo: misma ruta /stijid, se llama
    super() para conservar la lógica de Gerardo y se añade alrededor el conteo de
    vistas (Fase 0) y la trampa de pieza robada (Fase 1)."""

    def _dmn_resolve_lot(self, kw):
        url_s = kw.get("id")
        if not url_s:
            return None
        lot = (
            request.env["stock.lot"].sudo()
            .search([("x_studio_url_stij", "=", url_s)], limit=1)
        )
        if not lot or not lot.product_id or not lot.x_studio_visor_activo:
            return None
        return lot

    def stij_entry(self, **kw):
        lot = self._dmn_resolve_lot(kw)

        # --- Fase 1: trampa de pieza robada (antes del flujo normal) --- #
        if lot and lot.x_studio_estatus in DMN_THEFT_STATES:
            try:
                sighting = lot._dmn_record_theft_sighting(request)
                lot._dmn_notify_theft(sighting)
            except Exception:  # pragma: no cover
                _logger.exception("DMN: fallo en la trampa de robo del lote %s", lot.id)
            mode = lot.company_id.dmn_theft_mode or "deterrent"
            if mode == "decoy":
                # Señuelo: muestra el visor como si nada y cuenta la vista.
                request.session["active_stij_lot_id"] = lot.id
                lot._dmn_count_view(request)
                return request.redirect("/visor")
            # Disuasivo: cae al flujo normal de STIJ (redirige a /report).

        # --- Fase 2: pieza vendida sin reclamar -> formulario de registro --- #
        if lot and lot.dmn_claim_state == "pending":
            user = request.env.user
            is_owner = (
                not user._is_public()
                and lot.x_studio_beneficiario
                and user.partner_id.id == lot.x_studio_beneficiario.id
            )
            if not is_owner:
                request.session["active_stij_lot_id"] = lot.id
                return request.redirect("/dmn/register")

        # --- flujo original de STIJ (Gerardo) --- #
        resp = super().stij_entry(**kw)

        # --- Fase 0: contar vista de cliente (no staff, pieza no buscada) --- #
        try:
            if (
                lot
                and lot.x_studio_estatus not in DMN_THEFT_STATES
                and request.env.user._is_public()
            ):
                lot._dmn_count_view(request)
        except Exception:  # pragma: no cover
            _logger.exception("DMN: fallo al contar vista del lote %s", lot.id if lot else "?")
        return resp

    @http.route("/dmn/claim", type="jsonrpc", auth="public", website=True)
    def dmn_claim(self, token=None, name=None, email=None, phone=None, **kw):
        """Registro de propiedad por el comprador: valida el código de un solo uso
        impreso en su ticket y lo asigna como dueño. Sin token válido no se asigna
        nada (cierra la toma de posesión por enumeración, C1)."""
        return request.env["stock.lot"].sudo()._dmn_try_claim(token, name, email, phone)

    @http.route("/dmn/register", type="http", auth="public", website=True)
    def dmn_register_page(self, **kw):
        """Página de registro de propiedad: la ve el comprador al escanear su pieza
        recién comprada. Pide el código del ticket + sus datos y llama a /dmn/claim."""
        lot_id = request.session.get("active_stij_lot_id")
        lot = request.env["stock.lot"].sudo().browse(int(lot_id)) if lot_id else None
        if not lot or not lot.exists():
            return request.redirect("/")
        if lot.dmn_claim_state != "pending":
            return request.redirect("/visor")
        return request.render(
            "stij_diamane_plus.page_dmn_register",
            {"piece_name": lot.product_id.display_name or (lot.name or "")},
        )

    # ------------------------------------------------------------------- #
    #  Fase 5 — alta rápida de pieza STIJ (mostrador, solo staff)
    # ------------------------------------------------------------------- #
    def _dmn_is_staff(self):
        user = request.env.user
        return bool(user) and not user._is_public() and not user.share

    @http.route("/dmn/alta", type="http", auth="user", website=True)
    def dmn_quick_page(self, **kw):
        """Formulario de alta rápida de una pieza STIJ (uso de mostrador). Con los
        datos mínimos crea la joya + el lote escaneable y muestra el QR del visor."""
        if not self._dmn_is_staff():
            return request.redirect("/web/login")
        opts = request.env["stock.lot"].sudo()._dmn_quick_form_options()
        return request.render("stij_diamane_plus.page_dmn_quick", {"opts": opts})

    @http.route("/dmn/alta/describir", type="jsonrpc", auth="user")
    def dmn_quick_describe(self, **kw):
        """Sugiere la Descripción STIJ por IA a partir de la(s) foto(s). Solo staff;
        no crea nada, solo devuelve texto para que el staff lo revise/edite."""
        if not self._dmn_is_staff():
            return {"ok": False, "error": "No autorizado."}
        return request.env["stock.lot"].sudo()._dmn_ai_describe(kw)

    @http.route("/dmn/alta/crear", type="jsonrpc", auth="user")
    def dmn_quick_create(self, **kw):
        """Crea la pieza desde el alta rápida. Solo personal interno."""
        if not self._dmn_is_staff():
            return {"ok": False, "error": "No autorizado."}
        return request.env["stock.lot"].sudo()._dmn_quick_create(kw)

    @http.route("/dmn/dedication", type="jsonrpc", auth="public", website=True)
    def dmn_dedication(self, **kw):
        """Devuelve la dedicatoria de la pieza en sesión, respetando su visibilidad
        (pública o solo el dueño). El front del visor la pinta si visible=True."""
        lot_id = request.session.get("active_stij_lot_id")
        if not lot_id:
            return {"visible": False}
        lot = request.env["stock.lot"].sudo().browse(int(lot_id))
        if not lot.exists():
            return {"visible": False}
        if not lot._dmn_dedication_is_visible_to(request.env.user, True):
            return {"visible": False}
        payload = lot._dmn_dedication_payload()
        payload["visible"] = True
        return payload
