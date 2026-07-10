from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Flujo NOVADIAM: exhibición gratis → venta → taller (limpieza/verificación/
# certificado, opcionalmente personalización) → envío → inspección 72 h →
# liberación del pago. Ramas: rechazo en moderación, cancelación por
# verificación fallida y devolución (con reversión de personalizaciones).
LISTING_STATES = [
    ('draft', 'Borrador'),
    ('review', 'En revisión'),
    ('published', 'Publicado'),
    ('reserved', 'Vendido / reservado'),
    ('to_workshop', 'En tránsito a taller'),
    ('verifying', 'En verificación'),
    ('certified', 'Certificada'),
    ('personalizing', 'En personalización'),
    ('shipped', 'Enviada al comprador'),
    ('inspection', 'Inspección 72 h'),
    ('released', 'Liberada / pagada'),
    ('rejected', 'Rechazado (moderación)'),
    ('cancelled_verif', 'Cancelada: no pasó verificación'),
    ('returned', 'Devuelta'),
]

PERSONALIZATION_XMLIDS = [
    'xb_marketplace.svc_ajuste_talla',
    'xb_marketplace.svc_restauracion',
    'xb_marketplace.svc_grabado_joya',
    'xb_marketplace.svc_inscripcion_piedra',
]


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nv_is_listing = fields.Boolean('Anuncio de marketplace', index=True)
    nv_seller_id = fields.Many2one(
        'marketplace.seller', string='Vendedor', index=True, ondelete='restrict',
        tracking=True)
    nv_state = fields.Selection(
        LISTING_STATES, string='Etapa', default='draft', tracking=True, copy=False)
    nv_brand = fields.Char('Marca', help='Marca de la pieza, si aplica (se coteja en taller).')
    nv_city = fields.Char('Ciudad', help='Ciudad de origen; único dato de ubicación que se publica.')
    nv_story = fields.Text(
        'Nota personal del vendedor',
        help='Opcional y siempre anónima; se muestra en el anuncio.')
    nv_size = fields.Char('Talla')
    nv_carats = fields.Float('Quilates (centro)', digits=(6, 2))
    nv_cert_type = fields.Selection([
        ('gia', 'GIA'),
        ('igi', 'IGI'),
        ('other', 'Otra certificadora'),
        ('none', 'Sin certificado'),
        ('unknown', 'Por confirmar'),
    ], string='Certificado original', default='unknown')
    nv_cert_number = fields.Char('No. de certificado')
    nv_cert_file = fields.Binary('Archivo del certificado', attachment=True)
    nv_cert_filename = fields.Char('Nombre archivo certificado')
    nv_serial = fields.Char(
        'No. de serie Novadiam', copy=False, tracking=True,
        help='Se asigna al certificar: inscrito con láser en el diamante y grabado en la joya.')
    nv_workshop_notes = fields.Text('Notas de taller')

    # Venta / escrow (F4c)
    nv_sale_order_id = fields.Many2one(
        'sale.order', string='Orden de venta', copy=False, tracking=True,
        help='Orden confirmada que reservó esta pieza.')
    nv_inspection_deadline = fields.Datetime(
        'Fin de inspección', copy=False, tracking=True,
        help='Vencido este plazo sin disputa, el cron libera el pago.')
    nv_disputed = fields.Boolean('En disputa', copy=False, tracking=True)
    nv_release_move_id = fields.Many2one(
        'account.move', string='Asiento de liberación', copy=False, readonly=True)
    nv_contract_accept_date = fields.Datetime(
        'Contrato aceptado el', copy=False, readonly=True)
    nv_contract_version = fields.Char('Versión del contrato', copy=False, readonly=True)
    nv_sold_price = fields.Monetary(
        'Precio de venta final', copy=False,
        help='Lo que pagó el comprador por la pieza (sin personalizaciones).')
    nv_commission_amount = fields.Monetary(
        'Comisión Novadiam', compute='_compute_nv_amounts')
    nv_payout_amount = fields.Monetary(
        'Payout al vendedor', compute='_compute_nv_amounts')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _nv_param(self, key, default):
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'xb_marketplace.%s' % key, default)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    def _nv_deal_price(self):
        """Precio efectivamente cobrado por la pieza (línea de la orden)."""
        self.ensure_one()
        line = self.nv_sale_order_id.order_line.filtered(
            lambda l: l.product_id.product_tmpl_id == self)[:1]
        return line.price_total if line else self.list_price

    @api.depends('nv_sold_price', 'list_price', 'nv_sale_order_id')
    def _compute_nv_amounts(self):
        pct = self._nv_param('commission_pct', 18.0)
        for rec in self:
            price = rec.nv_sold_price or (
                rec.nv_sale_order_id and rec._nv_deal_price()) or rec.list_price
            commission = rec.currency_id.round(price * pct / 100.0)
            rec.nv_commission_amount = commission
            rec.nv_payout_amount = price - commission

    @api.model
    def _get_marketplace_website(self):
        website = self.env['website'].sudo().search(
            [('nv_is_marketplace', '=', True)], limit=1)
        if not website:
            website = self.env['website'].sudo().search(
                [('name', 'ilike', 'novadiam')], limit=1)
        return website or self.env['website'].sudo().search([], limit=1)

    def _bind_to_marketplace(self):
        """Amarra el producto al website y compañía del marketplace para no
        contaminar catálogos/POS de las demás compañías de la BD. Además fija
        la cuenta de ingreso = escrow (la pieza no es ingreso de Novadiam) y
        quita impuestos de venta (la comisión es lo único gravado)."""
        website = self._get_marketplace_website()
        vals = {}
        if website:
            vals['website_id'] = website.id
            if website.company_id:
                vals['company_id'] = website.company_id.id
        if vals:
            self.write(vals)
        company = website.company_id or self.env.company
        accounts = company._nv_get_marketplace_accounts()
        for rec in self.filtered('nv_is_listing').with_company(company):
            rec.property_account_income_id = accounts['escrow']
            rec.taxes_id = [(5, 0, 0)]

    # ------------------------------------------------------------------
    # Moderación
    # ------------------------------------------------------------------
    def action_submit_review(self):
        self.filtered(lambda l: l.nv_state in ('draft', 'rejected')).write(
            {'nv_state': 'review'})

    def action_publish_listing(self):
        optional = self.env['product.template']
        for xmlid in PERSONALIZATION_XMLIDS:
            tmpl = self.env.ref(xmlid, raise_if_not_found=False)
            if tmpl:
                optional |= tmpl
        for rec in self:
            if not rec.nv_seller_id:
                raise UserError(_('El anuncio no tiene vendedor asignado.'))
            if rec.list_price <= 0:
                raise UserError(_('El anuncio necesita un precio de venta.'))
            rec._bind_to_marketplace()
            vals = {'nv_state': 'published', 'is_published': True}
            if optional:
                vals['optional_product_ids'] = [(6, 0, optional.ids)]
            rec.write(vals)

    def action_reject_listing(self):
        self.write({'nv_state': 'rejected', 'is_published': False})

    def action_unpublish_listing(self):
        self.write({'nv_state': 'review', 'is_published': False})

    # ------------------------------------------------------------------
    # Post-venta
    # ------------------------------------------------------------------
    def action_mark_reserved(self, order=None):
        vals = {'nv_state': 'reserved', 'is_published': False}
        if order:
            vals['nv_sale_order_id'] = order.id
        self.write(vals)
        for rec in self:
            if order:
                rec.nv_sold_price = rec._nv_deal_price()
                rec.message_post(body=_(
                    'Pieza reservada por la orden %s.', order.name))

    def action_send_to_workshop(self):
        self.write({'nv_state': 'to_workshop'})

    def action_receive_workshop(self):
        self.write({'nv_state': 'verifying'})

    def action_certify(self):
        for rec in self:
            if not rec.nv_serial:
                raise UserError(_(
                    'Asigna primero el No. de serie Novadiam (inscripción '
                    'láser) para poder certificar la pieza.'))
            rec.write({'nv_state': 'certified'})

    def action_personalize(self):
        self.write({'nv_state': 'personalizing'})

    def action_ship(self):
        self.filtered(
            lambda l: l.nv_state in ('certified', 'personalizing')).write(
            {'nv_state': 'shipped'})

    def action_start_inspection(self):
        hours = int(self._nv_param('inspection_hours', 72))
        self.write({
            'nv_state': 'inspection',
            'nv_inspection_deadline': fields.Datetime.now() + timedelta(hours=hours),
        })

    def action_dispute(self):
        self.write({'nv_disputed': True})
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        for rec in self:
            rec.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Disputa de comprador en inspección'),
                note=_('El comprador reportó un problema; el pago queda '
                       'retenido hasta mediar la disputa.'),
                user_id=admin and admin.id or self.env.uid)

    def action_resolve_dispute(self):
        self.write({'nv_disputed': False})

    # ------------------------------------------------------------------
    # Liberación del escrow (F4c)
    # ------------------------------------------------------------------
    def _nv_check_order_paid(self):
        """La liberación exige factura publicada y pagada del comprador:
        el asiento debita el escrow que esa factura alimentó."""
        self.ensure_one()
        if self.env.context.get('nv_force_release'):
            return
        order = self.nv_sale_order_id
        invoices = order.invoice_ids.filtered(
            lambda m: m.state == 'posted'
            and m.payment_state in ('paid', 'in_payment'))
        if not order or not invoices:
            raise UserError(_(
                'No se puede liberar "%s": la orden %s no tiene factura '
                'publicada y pagada. Factura y registra el pago del '
                'comprador primero.', self.name,
                order.name or _('(sin orden)')))

    def _nv_release_move_vals(self):
        self.ensure_one()
        company = self.env['res.company']._nv_marketplace_company()
        accounts = company._nv_get_marketplace_accounts()
        price = self.nv_sold_price or self._nv_deal_price()
        pct = self._nv_param('commission_pct', 18.0)
        currency = company.currency_id
        commission = currency.round(price * pct / 100.0)
        payout = currency.round(price - commission)
        buyer = self.nv_sale_order_id.partner_id
        seller = self.nv_seller_id.partner_id
        lines = [
            (0, 0, {
                'name': _('Escrow liberado · %s', self.name),
                'account_id': accounts['escrow'].id,
                'partner_id': buyer.id,
                'debit': price, 'credit': 0.0,
            }),
            (0, 0, {
                'name': _('Payout vendedor · %s', self.name),
                'account_id': accounts['payout'].id,
                'partner_id': seller.id,
                'debit': 0.0, 'credit': payout,
            }),
        ]
        if accounts['vat']:
            # Comisión 18% con IVA incluido: 18/1.16 ingreso + IVA cobrado.
            net = currency.round(commission / 1.16)
            vat = currency.round(commission - net)
            lines.append((0, 0, {
                'name': _('Comisión marketplace (neta) · %s', self.name),
                'account_id': accounts['commission'].id,
                'partner_id': seller.id,
                'debit': 0.0, 'credit': net,
            }))
            lines.append((0, 0, {
                'name': _('IVA de comisión · %s', self.name),
                'account_id': accounts['vat'].id,
                'partner_id': seller.id,
                'debit': 0.0, 'credit': vat,
            }))
        else:
            lines.append((0, 0, {
                'name': _('Comisión marketplace · %s', self.name),
                'account_id': accounts['commission'].id,
                'partner_id': seller.id,
                'debit': 0.0, 'credit': commission,
            }))
        return {
            'journal_id': accounts['journal'].id,
            'company_id': company.id,
            'date': fields.Date.context_today(self),
            'ref': _('Liberación escrow %s · %s',
                     self.nv_sale_order_id.name or '', self.name),
            'line_ids': lines,
        }

    def action_release(self):
        for rec in self:
            if rec.nv_state not in ('shipped', 'inspection'):
                raise UserError(_(
                    'Solo se libera una pieza enviada o en inspección '
                    '("%s" está en otra etapa).', rec.name))
            if rec.nv_disputed:
                raise UserError(_(
                    'La pieza "%s" tiene una disputa abierta; resuélvela '
                    'antes de liberar el pago.', rec.name))
            if rec.nv_release_move_id:
                rec.write({'nv_state': 'released'})
                continue
            rec._nv_check_order_paid()
            move = self.env['account.move'].sudo().create(
                rec._nv_release_move_vals())
            move._post()
            rec.write({'nv_state': 'released', 'nv_release_move_id': move.id})
            rec.message_post(body=_(
                'Pago liberado: payout %(payout).2f al vendedor, comisión '
                '%(commission).2f. Asiento %(move)s.',
                payout=rec.nv_payout_amount,
                commission=rec.nv_commission_amount,
                move=move.name))
            rec.nv_seller_id.message_post(body=_(
                'Pago por liberar de "%(listing)s": %(payout).2f a la CLABE '
                'registrada (asiento %(move)s).',
                listing=rec.name, payout=rec.nv_payout_amount,
                move=move.name))

    @api.model
    def _cron_release_due(self):
        """Libera automáticamente las piezas cuya inspección venció sin
        disputa; si algo impide liberar (p. ej. factura sin pagar), deja
        actividad para el equipo en lugar de tronar."""
        due = self.search([
            ('nv_is_listing', '=', True),
            ('nv_state', '=', 'inspection'),
            ('nv_disputed', '=', False),
            ('nv_inspection_deadline', '!=', False),
            ('nv_inspection_deadline', '<=', fields.Datetime.now()),
        ])
        for listing in due:
            try:
                listing.action_release()
                self.env.cr.commit()
            except UserError as exc:
                self.env.cr.rollback()
                pending = self.env['mail.activity'].search_count([
                    ('res_model', '=', 'product.template'),
                    ('res_id', '=', listing.id),
                    ('summary', '=', 'Liberación automática detenida'),
                ])
                if not pending:
                    listing.activity_schedule(
                        'mail.mail_activity_data_todo',
                        summary='Liberación automática detenida',
                        note=str(exc))
                    self.env.cr.commit()

    def action_cancel_verification(self):
        """La pieza no corresponde a lo publicado: reembolso al comprador y
        devolución al vendedor."""
        self.write({'nv_state': 'cancelled_verif', 'is_published': False})
        for rec in self.filtered('nv_sale_order_id'):
            rec.message_post(body=_(
                'Venta cancelada por verificación: procede reembolso al '
                'comprador de la orden %s y devolución de la pieza al '
                'vendedor.', rec.nv_sale_order_id.name))

    def action_mark_returned(self):
        self.write({'nv_state': 'returned', 'is_published': False})
