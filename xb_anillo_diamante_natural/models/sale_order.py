# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

SESION = "xb_diamante_natural"


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _xb_gema_de_sesion(self, tmpl_id):
        if not request:
            return None
        return (request.session.get(SESION) or {}).get(str(tmpl_id))

    def _xb_gema_elegida(self, gema_id):
        """El diamante natural que el cliente eligió para el anillo, si todavía se puede vender."""
        gema = self.env["product.product"].sudo().browse(int(gema_id or 0)).exists()
        if not gema or not gema._xb_es_diamante_natural(self.website_id):
            raise UserError(_("Elige el diamante natural de tu anillo antes de agregarlo al carrito."))
        if gema in self.order_line.product_id:
            raise UserError(_("Ese diamante ya está en tu carrito con otro anillo. Elige otro diamante."))
        if self.website_id and self.website_id._get_product_available_qty(gema) <= 0:
            raise UserError(_("Ese diamante ya no está disponible. Elige otro diamante."))
        return gema

    def _cart_add(self, product_id, quantity=1.0, *, uom_id=None, **kwargs):
        product = self.env["product.product"].browse(product_id)
        gema_id = kwargs.pop("xb_gema_id", None)
        if kwargs.get("linked_line_id") or not product._xb_es_anillo_natural():
            return super()._cart_add(product_id, quantity, uom_id=uom_id, **kwargs)
        # Anillo con diamante natural: entra con el diamante que eligió el cliente, ligado a su línea.
        # Cada uno es una pieza única: cantidad 1.
        gema = self._xb_gema_elegida(gema_id or self._xb_gema_de_sesion(product.product_tmpl_id.id))
        res = super()._cart_add(product_id, 1, uom_id=uom_id, **kwargs)
        if res.get("line_id"):
            super()._cart_add(gema.id, 1, linked_line_id=res["line_id"])
        return res

    def _cart_find_product_line(self, product_id, uom_id, linked_line_id=False, **kwargs):
        # Dos anillos iguales con diamantes distintos son dos líneas, nunca una con cantidad 2.
        if not linked_line_id and self.env["product.product"].browse(product_id)._xb_es_anillo_natural():
            return self.env["sale.order.line"]
        return super()._cart_find_product_line(product_id, uom_id, linked_line_id=linked_line_id, **kwargs)

    def _verify_updated_quantity(self, order_line, product_id, new_qty, uom_id, **kwargs):
        new_qty, warning = super()._verify_updated_quantity(order_line, product_id, new_qty, uom_id, **kwargs)
        anillo = order_line.linked_line_id.product_id if order_line.linked_line_id else \
            self.env["product.product"].browse(product_id)
        if new_qty > 1 and anillo._xb_es_anillo_natural():
            return 1, _("Cada anillo con diamante natural es una pieza única. Para otro, agrégalo de nuevo con otro diamante.")
        return new_qty, warning

    def _cart_update_order_line(self, order_line, quantity, **kwargs):
        # Quitar el diamante de un anillo «Diamante natural» quita también el anillo: sin su diamante
        # no se puede vender.
        if quantity <= 0 and order_line.linked_line_id and order_line.linked_line_id.product_id._xb_es_anillo_natural():
            anillo = order_line.linked_line_id
            res = super()._cart_update_order_line(order_line, quantity, **kwargs)
            anillo.exists().unlink()
            return res
        return super()._cart_update_order_line(order_line, quantity, **kwargs)

    def _xb_anillos_sin_diamante(self):
        return self.order_line.filtered(
            lambda l: not l.linked_line_id and l.product_id and l.product_id._xb_es_anillo_natural()
            and not l.linked_line_ids.filtered(lambda s: s.product_id._xb_es_diamante_natural()))

    def _is_cart_ready(self):
        return super()._is_cart_ready() and not self._xb_anillos_sin_diamante()

    def _check_cart_is_ready_to_be_paid(self):
        if self._xb_anillos_sin_diamante():
            raise ValidationError(_("Un anillo de tu carrito no tiene su diamante natural. Quítalo y vuelve a "
                                    "agregarlo eligiendo el diamante."))
        return super()._check_cart_is_ready_to_be_paid()
