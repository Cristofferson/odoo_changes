# -*- coding: utf-8 -*-
# XUBAX - Delivery Receipt Signature
# Original, clean-room implementation. Native-only logic: the signature is
# captured through Odoo's own signature widget / portal.signature_form, stored
# on the picking, and mirrored to the native sale.order signature fields.
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # The signature image itself lives on Odoo's NATIVE stock.picking.signature
    # field, so it renders on the standard delivery slip and reuses the native
    # signature widget. We only add who/when, which the native model lacks.
    xb_delivery_signed_by = fields.Char(string="Signed by", copy=False)
    xb_delivery_signed_on = fields.Datetime(string="Signed on", copy=False)

    # Drives UI visibility (button + signature group) without leaking company
    # flags into every view: True only for outgoing deliveries of a company that
    # has the feature on.
    xb_show_delivery_signature = fields.Boolean(
        compute="_compute_xb_show_delivery_signature"
    )

    @api.depends("picking_type_code", "company_id.xb_delivery_signature_required")
    def _compute_xb_show_delivery_signature(self):
        for picking in self:
            picking.xb_show_delivery_signature = picking._xb_signature_feature_on()

    # --------------------------------------------------------------------- #
    #  Helpers
    # --------------------------------------------------------------------- #
    def _xb_signature_feature_on(self):
        """Master toggle for this picking (outgoing delivery + company flag)."""
        self.ensure_one()
        return bool(
            self.picking_type_code == "outgoing"
            and self.company_id.xb_delivery_signature_required
        )

    def _xb_signature_mandatory(self):
        """Whether a missing signature must block validation."""
        self.ensure_one()
        return bool(
            self._xb_signature_feature_on()
            and self.company_id.xb_delivery_signature_mandatory
        )

    def _xb_apply_signature(self, signature, signed_by=False, signed_on=False):
        """Write the signature on the picking and (optionally) mirror it to the
        linked Sale Order's native signature fields. Shared by the backend
        wizard and the portal controller so both behave identically."""
        self.ensure_one()
        signed_on = signed_on or fields.Datetime.now()
        self.write({
            "signature": signature,
            "xb_delivery_signed_by": signed_by or self.partner_id.name or "",
            "xb_delivery_signed_on": signed_on,
        })
        if self.company_id.xb_delivery_signature_mirror_so and self.sale_id:
            # Native fields are reset to draft only when a quotation reverts; for
            # our confirmed orders they are otherwise unused, so this is a safe
            # place to surface the delivery acknowledgement.
            self.sale_id.write({
                "signature": signature,
                "signed_by": signed_by or self.partner_id.name or "",
                "signed_on": signed_on,
            })
        return True

    def _xb_open_signature_wizard(self, validate_after=False):
        """Return the action that opens the signature pad for this picking.

        validate_after=True resumes button_validate once signed (mandatory
        validation flow); False just records the signature (manual button)."""
        self.ensure_one()
        wizard = self.env["xb.delivery.signature.wizard"].create({
            "picking_id": self.id,
            "signed_by": self.partner_id.name or "",
            "validate_after": validate_after,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Delivery receipt signature"),
            "res_model": "xb.delivery.signature.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_xb_request_signature(self):
        """Manual entry point (smart button / header button on the form)."""
        self.ensure_one()
        if self.picking_type_code != "outgoing":
            raise UserError(_("The delivery signature only applies to outgoing transfers."))
        return self._xb_open_signature_wizard()

    # --------------------------------------------------------------------- #
    #  Validation hook
    # --------------------------------------------------------------------- #
    def _pre_action_done_hook(self):
        # Intercept BEFORE the native pre-done logic (backorder wizard, etc.):
        # for a mandatory, still-unsigned outgoing delivery, pop the signature
        # pad. The wizard re-launches button_validate with xb_skip_signature_check
        # so the native flow then proceeds normally.
        if not self.env.context.get("xb_skip_signature_check"):
            need = self.filtered(
                lambda p: p._xb_signature_mandatory() and not p.signature
            )
            if need:
                return need[:1]._xb_open_signature_wizard(validate_after=True)
        return super()._pre_action_done_hook()
