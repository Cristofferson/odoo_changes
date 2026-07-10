from odoo import _, models
from odoo.exceptions import UserError

# Contabilidad del escrow (código agrupador SAT):
# - 206.05.xx  pasivo "escrow por liberar": ahí cae el precio de la pieza al
#   facturarse al comprador (la pieza NO es ingreso de Novadiam, que actúa
#   como comisionista).
# - 205.06.xx  acreedores diversos: lo que se le debe al vendedor (82%).
# - 401.01.xx  ingreso por la comisión (18%), IVA incluido si hay cuenta
#   208.01 (IVA trasladado cobrado) donde desglosarlo.
ESCROW_SPEC = {
    'escrow': ('206.05.02', 'NOVADIAM escrow por liberar',
               'liability_current', True),
    'payout': ('205.06.03', 'NOVADIAM vendedores marketplace por pagar',
               'liability_current', True),
    'commission': ('401.01.02', 'NOVADIAM comisión marketplace',
                   'income', False),
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _nv_get_marketplace_accounts(self):
        """Cuentas y diario del escrow del marketplace (se crean si faltan)."""
        self.ensure_one()
        Account = self.env['account.account'].sudo().with_company(self)
        accounts = {}
        for key, (code, name, account_type, reconcile) in ESCROW_SPEC.items():
            account = Account.search([
                ('company_ids', 'in', self.id), ('code', '=', code)], limit=1)
            if not account:
                account = Account.create({
                    'code': code,
                    'name': name,
                    'account_type': account_type,
                    'reconcile': reconcile,
                    'company_ids': [(6, 0, [self.id])],
                })
            accounts[key] = account
        # IVA trasladado cobrado (208.01.xx): si no existe, la comisión se
        # abona completa al ingreso y el desglose lo hace el contador.
        accounts['vat'] = Account.search([
            ('company_ids', 'in', self.id), ('code', '=like', '208.01%')],
            limit=1)
        journal = self.env['account.journal'].sudo().search([
            ('company_id', '=', self.id), ('code', '=', 'NVMKT')], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': 'Marketplace NOVADIAM',
                'code': 'NVMKT',
                'type': 'general',
                'company_id': self.id,
            })
        accounts['journal'] = journal
        return accounts

    def _nv_marketplace_company(self):
        """Compañía del marketplace = la del website marcado."""
        website = self.env['website'].sudo().search(
            [('nv_is_marketplace', '=', True)], limit=1)
        company = website.company_id or self.env.company
        if not company:
            raise UserError(_('No hay compañía para el marketplace.'))
        return company
