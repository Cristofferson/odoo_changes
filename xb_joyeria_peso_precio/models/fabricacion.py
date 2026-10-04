# -*- coding: utf-8 -*-
from odoo import models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _get_moves_raw_values(self):
        """Además de la lista de materiales (piedras), la orden de una joya cotizada por metal consume su
        ALEACIÓN: el producto ligado al valor de Metal de la variante, por el peso proyectado de esa
        combinación (metal, medida…) × cantidad. La aleación puede fabricarse a su vez desde metal fino."""
        moves = super()._get_moves_raw_values()
        for production in self:
            prod = production.product_id
            if not prod.product_tmpl_id.xb_precio_por_metal:
                continue
            metal = prod.product_template_attribute_value_ids.filtered(lambda v: v.attribute_id.name == 'Metal')[:1]
            aleacion = metal.product_attribute_value_id.xb_aleacion_id
            peso = prod.xb_peso_proyectado if 'xb_peso_proyectado' in prod._fields else 0.0
            if not aleacion or not peso:
                continue
            qty = peso * production.product_uom_id._compute_quantity(production.product_qty, prod.uom_id)
            moves.append(production._get_move_raw_values(aleacion, round(qty, 3), aleacion.uom_id))
        return moves


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _xb_lineas_a_fabricar(self):
        """Joyas por metal que no hay en existencia: se mandan a fabricar en vez de salir del inventario."""
        self.ensure_one()
        return self.lines.filtered(lambda l: l.qty > 0 and l.product_id.product_tmpl_id.xb_precio_por_metal
                                   and l.product_id.with_company(l.company_id).free_qty < l.qty)

    def _create_order_picking(self):
        """En la caja, una joya sin existencia sigue el mismo camino que «enviar después»: regla de
        abastecimiento → orden de fabricación + entrega en espera. El resto de la venta sale como siempre."""
        self.ensure_one()
        fab = self._xb_lineas_a_fabricar() if not self.shipping_date else self.env['pos.order.line']
        if not fab:
            return super()._create_order_picking()
        resto = self.lines - fab
        if resto and self._should_create_picking_real_time():
            picking_type = self.config_id.picking_type_id
            if self.partner_id.property_stock_customer:
                destino = self.partner_id.property_stock_customer.id
            elif not picking_type or not picking_type.default_location_dest_id:
                destino = self.env['stock.warehouse']._get_partner_locations()[0].id
            else:
                destino = picking_type.default_location_dest_id.id
            pickings = self.env['stock.picking']._create_picking_from_pos_order_lines(destino, resto, picking_type, self.partner_id)
            pickings.write({'pos_session_id': self.session_id.id, 'pos_order_id': self.id, 'origin': self.name})
        fab.sudo()._launch_stock_rule_from_pos_order_lines()
