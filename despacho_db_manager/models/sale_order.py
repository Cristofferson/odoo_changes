from odoo import models, api


class SaleOrder(models.Model):
    """En el asistente de ligado de suscripciones, el selector debe mostrar y buscar
    por NOMBRE DEL CLIENTE (el folio S00014 no dice nada). Se activa con el flag de
    contexto `despacho_sub_label` (solo lo pone ese asistente; el resto de Ventas no
    cambia)."""
    _inherit = 'sale.order'

    @api.depends('partner_id')
    @api.depends_context('despacho_sub_label')
    def _compute_display_name(self):
        if not self.env.context.get('despacho_sub_label'):
            return super()._compute_display_name()
        for order in self:
            partner = order.partner_id.name or order.partner_id.display_name or '(sin cliente)'
            order.display_name = ('%s — %s' % (partner, order.name)) if order.name else partner

    @property
    def _rec_names_search(self):
        if self.env.context.get('despacho_sub_label'):
            # Buscar primero por nombre de cliente, también por folio.
            return ['partner_id.name', 'name']
        return super()._rec_names_search
