# -*- coding: utf-8 -*-
# XUBAX - Delivery Receipt Signature - POS Bridge
from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    xb_delivery_signature = fields.Image(
        string="Delivery signature",
        copy=False,
        max_width=1024,
        max_height=1024,
        attachment=True,
    )
    xb_delivery_signed_by = fields.Char(string="Signed by", copy=False)
    xb_delivery_signed_on = fields.Datetime(string="Signed on", copy=False)

    def xb_set_delivery_signature(self, signature, signed_by=False):
        """Store the hand-over signature on the POS order and (optionally) mirror
        it to the linked Sale Order's native signature fields. Called from the
        POS frontend right after the order is validated/synced."""
        self.ensure_one()
        signed_on = fields.Datetime.now()
        signed_by = signed_by or (self.partner_id.name if self.partner_id else "") or ""
        self.write({
            "xb_delivery_signature": signature,
            "xb_delivery_signed_by": signed_by,
            "xb_delivery_signed_on": signed_on,
        })
        # POS orders created from sale.order (quotation/order/layaway) keep the
        # link through their lines' sale_order_origin_id (pos_sale).
        if self.company_id.xb_delivery_signature_mirror_so:
            sale_order = self.lines.mapped("sale_order_origin_id")[:1]
            if sale_order:
                sale_order.write({
                    "signature": signature,
                    "signed_by": signed_by,
                    "signed_on": signed_on,
                })
        # POS configs that deliver from stock generate their own stock.picking
        # directly (no sale.order in between). Mirror onto the picking's native
        # signature field so the delivery slip / picking form show the hand-over.
        self._xb_mirror_signature_to_pickings(signature, signed_by, signed_on)
        return True

    def _xb_mirror_signature_to_pickings(self, signature, signed_by, signed_on):
        """Copy the hand-over signature onto the POS order's own pickings."""
        for order in self:
            pickings = order.picking_ids.filtered(lambda p: not p.signature)
            if pickings:
                pickings.write({
                    "signature": signature,
                    "xb_delivery_signed_by": signed_by,
                    "xb_delivery_signed_on": signed_on,
                })
