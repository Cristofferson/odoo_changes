# -*- coding: utf-8 -*-
# XUBAX - Delivery Receipt Signature
# Original, clean-room implementation. Mirrors the native sale "portal
# confirmation signature" configuration pattern (res.company flags surfaced in
# res.config.settings), applied to delivery (stock.picking) hand-over.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # --- Master toggle: the whole feature for this company ---
    xb_delivery_signature_required = fields.Boolean(
        string="Delivery receipt signature",
        help="Capture the customer's received signature on outgoing deliveries "
             "of this company (on the operator's tablet and/or from the portal).",
    )

    # --- Sub-toggles (only relevant when the master toggle is on) ---
    xb_delivery_signature_mandatory = fields.Boolean(
        string="Signature mandatory to validate",
        help="When enabled, an outgoing delivery cannot be validated until it is "
             "signed: validating it pops up the signature pad on the operator's "
             "device. When disabled, the signature is offered (\"Request "
             "signature\" button / portal) but never blocks validation.",
    )
    xb_delivery_signature_portal = fields.Boolean(
        string="Allow portal self-signature",
        default=True,
        help="Expose a secure portal link (/my/delivery/<id>/sign, authorised by "
             "the sale order's access token) so the customer can sign the "
             "delivery from their own phone.",
    )
    xb_delivery_signature_mirror_so = fields.Boolean(
        string="Copy signature to the Sale Order",
        default=True,
        help="Also write the captured signature to the linked Sale Order's "
             "native signature fields (Signature / Signed By / Signed On). With "
             "partial deliveries the Sale Order reflects the most recent one; the "
             "per-delivery copy is always kept.",
    )
    xb_delivery_signature_on_slip = fields.Boolean(
        string="Print signature on the delivery slip",
        default=True,
        help="Show the captured signature (and who signed) on the printed "
             "delivery slip (PDF).",
    )
