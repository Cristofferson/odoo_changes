# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

CATEG_GEMA = 71
# El «Precio público» ya trae el IVA; la tienda se lo suma al precio de
# venta, así que se guarda sin él.
IVA = 0.16
# Campos de los que depende x_studio_precio_publico (compute de Studio) y
# la cotización de rapaport_pricing, que escribe x_studio_precio_rapnet_qt.
CAMPOS_PRECIO = {
    "categ_id", "x_studio_precio_rapnet_qt", "x_studio_quilataje_c", "x_studio_corte",
    "x_studio_triple_excelente_c", "x_studio_ha_c", "x_studio_certificados",
    "x_studio_origen_c",
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _xb_tasa_usd_mxn(self):
        """Pesos por dólar de hoy, de la compañía que lleva tasas de USD (en
        esta BD solo la principal; Anello no tiene tasas propias)."""
        usd = self.env.ref("base.USD")
        mxn = self.env.ref("base.MXN")
        tasa = self.env["res.currency.rate"].sudo().search(
            [("currency_id", "=", usd.id)], order="name desc", limit=1)
        compania = tasa.company_id or self.env.company
        return usd._convert(1.0, mxn, compania, fields.Date.context_today(self), round=False)

    def _xb_aplicar_precio_rapaport(self, tasa=None):
        gemas = self.filtered(lambda t: t.categ_id.id == CATEG_GEMA
                              and "x_studio_precio_publico" in t._fields
                              and t.x_studio_precio_publico > 0)
        if not gemas:
            return 0
        tasa = tasa or self._xb_tasa_usd_mxn()
        cambiadas = 0
        for gema in gemas:
            precio = round(gema.x_studio_precio_publico * tasa / (1 + IVA), 2)
            if float_compare(gema.list_price, precio, precision_digits=2):
                gema.with_context(xb_precio_rapaport=True).write({"list_price": precio})
                cambiadas += 1
        return cambiadas

    @api.model
    def _cron_xb_precio_rapaport(self):
        gemas = self.with_context(active_test=False).search(
            [("categ_id", "=", CATEG_GEMA), ("x_studio_precio_publico", ">", 0)])
        cambiadas = gemas._xb_aplicar_precio_rapaport()
        _logger.info("Precio de venta Rapaport: %s de %s gemas actualizadas", cambiadas, len(gemas))
        return cambiadas

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        if not self.env.context.get("xb_precio_rapaport"):
            templates._xb_aplicar_precio_rapaport()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("xb_precio_rapaport") and CAMPOS_PRECIO.intersection(vals):
            self._xb_aplicar_precio_rapaport()
        return res
