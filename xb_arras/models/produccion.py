# -*- coding: utf-8 -*-
from odoo import models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    def _xb_arras_detalle(self):
        """«Vuelta: Nombres · Grabar: Ana y Luis» de una línea de arras."""
        self.ensure_one()
        partes = [
            '%s: %s' % (v.attribute_id.name, v.name)
            for v in self.attribute_value_ids
            if v.attribute_id.create_variant == 'no_variant' and not v.is_custom
        ]
        partes += ['Grabar: %s' % c.custom_value for c in self.custom_attribute_value_ids if c.custom_value]
        return ' · '.join(partes)

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if self.product_id.product_tmpl_id.xb_arras:
            values['xb_arras_detalle'] = self._xb_arras_detalle()
        return values


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        """La vuelta y el texto a grabar viajan en la descripción de la entrega y de ahí a la orden
        de fabricación (``product_description_variants``), para que el taller los vea."""
        res = super()._get_stock_move_values(product_id, product_qty, product_uom, location_id, name, origin, company_id, values)
        if values.get('xb_arras_detalle'):
            res['description_picking_manual'] = values['xb_arras_detalle']
        return res

    def _should_auto_confirm_procurement_mo(self, p):
        # La imitación no lleva componentes (solo material y baño como operaciones): Odoo dejaría
        # su orden de fabricación en borrador; las arras se confirman igual que las de metal.
        if p.product_id.product_tmpl_id.xb_arras:
            return not p.orderpoint_id
        return super()._should_auto_confirm_procurement_mo(p)
