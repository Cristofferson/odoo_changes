# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _action_done(self):
        """Tras validar la salida a cliente, genera el código de registro de
        propiedad (Fase 2) para cada pieza vendida que aún no lo tenga."""
        res = super()._action_done()
        try:
            self._dmn_generate_claims()
        except Exception:  # pragma: no cover - nunca romper la validación
            _logger.exception("DMN: no se pudo generar el código de registro")
        return res

    def _dmn_generate_claims(self):
        for picking in self:
            move_lines = picking.move_line_ids.filtered(
                lambda ml: ml.lot_id
                and ml.quantity > 0
                and ml.location_dest_id.usage == "customer"
            )
            for ml in move_lines:
                lot = ml.lot_id
                if lot.dmn_claim_state and lot.dmn_claim_state != "none":
                    continue  # ya tiene token (pending/claimed)
                lot._dmn_generate_claim(picking.partner_id)
