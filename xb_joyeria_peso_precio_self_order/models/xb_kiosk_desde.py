# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# The cron refreshes every 15 minutes; past this age a price is computed again live.
MAX_AGE = timedelta(hours=6)


class XbKioskDesde(models.Model):
    """The "from" price of each jewel priced by its metal, per kiosk, computed ahead.

    Computing it takes ~35 ms per jewel (gold of the day, bill of materials, price
    list): with hundreds of jewels the kiosk took 15 s or more to open. A cron keeps
    this table fresh and the kiosk only reads it."""
    _name = "xb.kiosk.desde"
    _description = "Kiosk 'from' price of a jewel"

    config_id = fields.Many2one("pos.config", required=True, ondelete="cascade", index=True)
    product_tmpl_id = fields.Many2one("product.template", required=True, ondelete="cascade")
    price = fields.Float()

    _config_tmpl_uniq = models.Constraint(
        "unique(config_id, product_tmpl_id)", "One price per jewel and kiosk.")

    @api.model
    def _xb_compute(self, config, templates):
        """{template id: "from" price (untaxed, with the kiosk's price list)}."""
        pricelist = config.pricelist_id
        desde = {}
        if not pricelist:
            return desde
        for tmpl in templates.with_company(config.company_id):
            try:
                comb = tmpl._xb_combinacion_desde()
                desde[tmpl.id] = pricelist._get_product_price(
                    tmpl.with_context(xb_combinacion=tuple(comb.ids)), 1.0
                )
            except Exception:  # noqa: BLE001 - one badly set up jewel must not break the kiosk
                _logger.warning("Kiosk: no 'from' price for product.template %s", tmpl.id, exc_info=True)
        return desde

    @api.model
    def _xb_get(self, config, templates):
        """Prices for the kiosk: the fresh ones from the table, the rest computed now."""
        limite = fields.Datetime.now() - MAX_AGE
        rows = self.sudo().search([
            ("config_id", "=", config.id), ("product_tmpl_id", "in", templates.ids),
            ("write_date", ">=", limite),
        ])
        desde = {r.product_tmpl_id.id: r.price for r in rows}
        faltan = templates.filtered(lambda t: t.id not in desde)
        if faltan:
            desde.update(self._xb_compute(config, faltan))
        return desde

    @api.model
    def _xb_kiosk_templates(self, config):
        domain = [
            ("xb_precio_por_metal", "=", True),
            ("self_order_available", "=", True),
            ("available_in_pos", "=", True),
        ]
        if config.limit_categories and config.iface_available_categ_ids:
            domain.append(("pos_categ_ids", "in", config.iface_available_categ_ids.ids))
        return self.env["product.template"].with_company(config.company_id).search(domain)

    @api.model
    def _xb_refresh(self, configs=None):
        configs = configs or self.env["pos.config"].search([
            ("self_ordering_mode", "!=", "nothing"), ("pricelist_id", "!=", False),
        ])
        for config in configs:
            templates = self._xb_kiosk_templates(config)
            desde = self._xb_compute(config, templates)
            rows = self.search([("config_id", "=", config.id)])
            por_tmpl = {r.product_tmpl_id.id: r for r in rows}
            (rows - self.browse([r.id for t, r in por_tmpl.items() if t in desde])).unlink()
            nuevos = []
            for tmpl_id, price in desde.items():
                row = por_tmpl.get(tmpl_id)
                if row:
                    # Always written, so write_date says the price is fresh.
                    row.write({"price": price})
                else:
                    nuevos.append({"config_id": config.id, "product_tmpl_id": tmpl_id, "price": price})
            self.create(nuevos)
            _logger.info("Kiosk %s: %s 'from' prices refreshed", config.name, len(desde))
        return True
