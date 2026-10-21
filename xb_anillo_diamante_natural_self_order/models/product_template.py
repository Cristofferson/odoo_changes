# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        """El kiosco carga también los diamantes naturales para poder agregarlos junto con el anillo,
        aunque su categoría no esté en el kiosco (no salen en la lista de productos)."""
        domain = super()._load_pos_self_data_domain(data, config)
        gemas = Domain.AND([
            self._xb_diamantes_naturales_domain(),
            self._check_company_domain(config.company_id),
            [("available_in_pos", "=", True), ("self_order_available", "=", True)],
        ])
        return Domain.OR([domain, gemas])

    def _load_pos_self_data_read(self, data, config):
        """El kiosco solo necesita saber SI hay miniatura (Odoo la vuelve True/False), pero la lee completa.
        Las miniaturas de los diamantes son GIF animados de 3-6 MB: ~480 MB por carga tumbaban la memoria
        y el kiosco se quedaba en blanco. Con bin_size se lee solo el tamaño; el resultado es el mismo."""
        return super(ProductTemplate, self.with_context(bin_size=True))._load_pos_self_data_read(data, config)
