# -*- coding: utf-8 -*-
from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _load_pos_self_data_read(self, data, config):
        """Each jewel priced by its metal gets its "from" price (untaxed, with the kiosk's
        price list), as the website shows it: the kiosk cannot compute it by itself.
        The prices come computed ahead (xb.kiosk.desde) so the kiosk opens fast."""
        res = super()._load_pos_self_data_read(data, config)
        ids = [r["id"] for r in res if r.get("xb_precio_por_metal")]
        if not config.pricelist_id or not ids:
            return res
        desde = self.env["xb.kiosk.desde"]._xb_get(config, self.browse(ids))
        for r in res:
            if desde.get(r["id"]):
                r["_xb_desde"] = desde[r["id"]]
        return res
