# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _load_pos_self_data_read(self, data, config):
        """Each jewel priced by its metal gets its "from" price (untaxed, with the kiosk's
        price list), as the website shows it: the kiosk cannot compute it by itself."""
        res = super()._load_pos_self_data_read(data, config)
        pricelist = config.pricelist_id
        ids = [r["id"] for r in res if r.get("xb_precio_por_metal")]
        if not pricelist or not ids:
            return res
        desde = {}
        for tmpl in self.browse(ids).with_company(config.company_id):
            try:
                comb = tmpl._xb_combinacion_desde()
                desde[tmpl.id] = pricelist._get_product_price(
                    tmpl.with_context(xb_combinacion=tuple(comb.ids)), 1.0
                )
            except Exception:  # noqa: BLE001 - one badly set up jewel must not break the kiosk
                _logger.warning("Kiosk: no 'from' price for product.template %s", tmpl.id, exc_info=True)
        for r in res:
            if desde.get(r["id"]):
                r["_xb_desde"] = desde[r["id"]]
        return res
