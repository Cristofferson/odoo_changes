# -*- coding: utf-8 -*-
# XUBAX - Sales, Quotations & Layaway from POS
# Original, clean-room implementation. Native-only logic.
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    xb_cfdi_emisor_rfc = fields.Char(
        string="CFDI issuer RFC (receipt)",
        compute="_compute_xb_cfdi_emisor_rfc",
        help="RFC of the fiscal entity that issues the CFDI, for the POS receipt "
        "footer. Resolves to the company's own VAT or, for a branch without one, "
        "the nearest parent that has one — exactly as l10n_mx_edi picks the CFDI "
        "issuer (l10n_mx_edi_document: parent_ids[::-1].filtered('partner_id.vat')).",
    )

    def _compute_xb_cfdi_emisor_rfc(self):
        for company in self:
            # DORMANT outside Mexico: keyed on the fiscal country (like l10n_mx_edi).
            # On a non-MX company this stays False, so the receipt footer falls back to
            # the native vatText / native t-if (company.vat) -- pure native behaviour.
            if (company.account_fiscal_country_id.code or company.country_id.code) != "MX":
                company.xb_cfdi_emisor_rfc = False
                continue
            # Same selection l10n_mx_edi uses for the CFDI 'emisor': walk the company
            # hierarchy from self up to the root, take the nearest one that carries a
            # VAT on its partner, and use its commercial partner's VAT.
            root = company.sudo().parent_ids[::-1].filtered("partner_id.vat")[:1] or company
            company.xb_cfdi_emisor_rfc = (
                root.partner_id.commercial_partner_id.vat or company.vat or False
            )

    @api.model
    def _load_pos_data_fields(self, config):
        # Expose the resolved issuer RFC so the receipt footer shows the fiscal
        # entity's RFC (the parent's, for a branch) instead of an empty value.
        return super()._load_pos_data_fields(config) + ["xb_cfdi_emisor_rfc"]
