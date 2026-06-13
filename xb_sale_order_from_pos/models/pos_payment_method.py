# -*- coding: utf-8 -*-
# XUBAX - Sales, Quotations & Layaway from POS
# Bridge POS payment methods to the SAT "Forma de pago" catalog so the CFDI of a
# POS-issued invoice reflects HOW it was paid (cash 01, transfer 03, credit 04,
# debit 28...). l10n_mx_edi_pos provides this natively; we reproduce the minimal
# mapping field clean-room (it is NOT installed here). Native logic only.
from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    l10n_mx_edi_payment_method_id = fields.Many2one(
        comodel_name="l10n_mx_edi.payment.method",
        string="Forma de pago (SAT)",
        help="SAT 'Forma de pago' reported on the CFDI when an order paid with this "
        "method is invoiced (e.g. 01 Efectivo, 03 Transferencia, 04 Tarjeta de "
        "crédito, 28 Tarjeta de débito).",
    )

    # Fiscal country of the method's company, used ONLY to hide the SAT field above on
    # non-Mexican companies (the Mexican support stays dormant outside MX). Keyed on the
    # fiscal country like l10n_mx_edi, so a company running a generic chart never shows it.
    xb_company_country_code = fields.Char(
        related="company_id.account_fiscal_country_id.code",
        string="Company fiscal country code",
    )
