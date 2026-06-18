# -*- coding: utf-8 -*-
# XUBAX - Delivery Receipt Signature
# Portal self-sign page for a delivery order. No native portal page exists for
# stock.picking, so this is custom; access is authorised through the linked sale
# order's access_token, reusing sale_stock's _stock_picking_check_access helper.
import binascii

from werkzeug.exceptions import NotFound

from odoo import _, exceptions
from odoo.addons.sale_stock.controllers.portal import SaleStockPortal
from odoo.http import request, route


class DeliverySignaturePortal(SaleStockPortal):

    def _xb_delivery_sign_access(self, picking_id, access_token):
        """Authorise + gate: outgoing delivery of a company that has the portal
        self-signature feature on. Raises like the native access helper."""
        picking_sudo = self._stock_picking_check_access(picking_id, access_token=access_token)
        company = picking_sudo.company_id
        if picking_sudo.picking_type_code != "outgoing" or not (
            company.xb_delivery_signature_required and company.xb_delivery_signature_portal
        ):
            raise NotFound()
        return picking_sudo

    @route(["/my/delivery/<int:picking_id>/sign"], type="http", auth="public", website=True)
    def xb_portal_delivery_sign(self, picking_id, access_token=None, **kw):
        try:
            picking_sudo = self._xb_delivery_sign_access(picking_id, access_token)
        except (exceptions.AccessError, exceptions.MissingError):
            return request.redirect("/my")
        token_qs = ("?access_token=%s" % access_token) if access_token else ""
        values = {
            "picking": picking_sudo,
            "already_signed": bool(picking_sudo.signature),
            "call_url": "/my/delivery/%s/sign/accept%s" % (picking_sudo.id, token_qs),
            "default_name": picking_sudo.partner_id.name or "",
            "page_name": "delivery_signature",
        }
        return request.render("xb_delivery_signature.portal_delivery_sign", values)

    @route(["/my/delivery/<int:picking_id>/sign/accept"], type="jsonrpc",
           auth="public", website=True)
    def xb_portal_delivery_sign_accept(self, picking_id, access_token=None,
                                       name=None, signature=None):
        try:
            picking_sudo = self._xb_delivery_sign_access(picking_id, access_token)
        except (exceptions.AccessError, exceptions.MissingError, NotFound):
            return {"error": _("This delivery is not available for signature.")}
        if not signature:
            return {"error": _("Please draw your signature before submitting.")}
        try:
            picking_sudo._xb_apply_signature(signature, signed_by=name)
        except (TypeError, binascii.Error):
            return {"error": _("Invalid signature data.")}
        # Reload the page so it shows the confirmation state.
        token_qs = ("?access_token=%s" % access_token) if access_token else ""
        return {
            "force_refresh": True,
            "redirect_url": "/my/delivery/%s/sign%s" % (picking_sudo.id, token_qs),
        }
