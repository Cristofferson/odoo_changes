from odoo import models, fields, api


class SubscriptionLinkWizard(models.TransientModel):
    """Mini-asistente para ligar a mano una BD con su suscripción. Solo se abre con
    la compañía XUBAX activa (el botón que lo lanza lo verifica), así el selector de
    suscripciones se puede mostrar sin chocar con la regla multiempresa."""
    _name = 'despacho.subscription.link.wizard'
    _description = 'Ligar BD con su suscripción'

    project_id = fields.Many2one('project.project', required=True, readonly=True)
    subscription_id = fields.Many2one(
        'sale.order', string='Suscripción',
        domain="[('id', 'in', available_ids)]",
        help='Suscripciones que aún no están asignadas a otra BD (más la actual).')
    available_ids = fields.Many2many(
        'sale.order', compute='_compute_available', compute_sudo=True)

    @api.depends('project_id')
    def _compute_available(self):
        for w in self:
            w.available_ids = w.project_id.despacho_available_subscription_ids

    def action_confirm(self):
        self.ensure_one()
        self.project_id.despacho_subscription_id = self.subscription_id
        return {'type': 'ir.actions.act_window_close'}
