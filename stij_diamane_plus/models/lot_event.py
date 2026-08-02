# -*- coding: utf-8 -*-
from odoo import fields, models


class StijLotEvent(models.Model):
    """El ledger de STIJ no contempla el alta de la pieza porque en el flujo
    tradicional la joya nace en el catálogo, no en el visor. El alta rápida de
    mostrador sí es un hecho trazable ("esta pieza la registró Fulana el día X"),
    así que se añade su tipo por herencia, sin tocar el repo de Gerardo."""

    _inherit = "stij.lot.event"

    event_type = fields.Selection(
        selection_add=[("dmn_quick_created", "Alta rápida (mostrador)")],
        ondelete={"dmn_quick_created": "cascade"},
    )
