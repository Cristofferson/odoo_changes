# -*- coding: utf-8 -*-
# XUBAX - Delivery Receipt Signature
from odoo import _, fields, models
from odoo.exceptions import UserError


class DeliverySignatureWizard(models.TransientModel):
    _name = "xb.delivery.signature.wizard"
    _description = "Delivery receipt signature pad"

    picking_id = fields.Many2one(
        "stock.picking", string="Delivery", required=True, ondelete="cascade"
    )
    partner_id = fields.Many2one(related="picking_id.partner_id", string="Customer")
    signed_by = fields.Char(string="Signed by")
    signature = fields.Image(
        string="Signature", max_width=1024, max_height=1024, attachment=False
    )
    # True when launched from the validation flow (signature mandatory): after
    # signing we resume button_validate. False when launched manually from the
    # "Request signature" button: we only record the signature.
    validate_after = fields.Boolean(default=False)

    def action_sign(self):
        self.ensure_one()
        if not self.signature:
            raise UserError(_("Please capture the customer's signature before confirming."))
        self.picking_id._xb_apply_signature(self.signature, self.signed_by)
        if self.validate_after:
            return self.picking_id.with_context(
                xb_skip_signature_check=True
            ).button_validate()
        return {"type": "ir.actions.act_window_close"}
