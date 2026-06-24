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
