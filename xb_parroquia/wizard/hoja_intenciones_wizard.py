from odoo import fields, models
from odoo.exceptions import UserError


class ParroquiaHojaWizard(models.TransientModel):
    _name = 'parroquia.hoja.wizard'
    _description = 'Imprimir hoja de intenciones'

    fecha_desde = fields.Date(string='Desde', required=True,
                              default=fields.Date.context_today)
    fecha_hasta = fields.Date(string='Hasta', required=True,
                              default=fields.Date.context_today)

    def action_imprimir(self):
        self.ensure_one()
        if self.fecha_hasta < self.fecha_desde:
            raise UserError('La fecha final debe ser posterior a la inicial.')
        celebraciones = self.env['parroquia.celebracion'].search([
            ('fecha', '>=', self.fecha_desde),
            ('fecha', '<=', self.fecha_hasta),
        ])
        if not celebraciones:
            raise UserError('No hay celebraciones agendadas en ese rango.')
        return self.env.ref(
            'xb_parroquia.action_report_hoja_intenciones'
        ).report_action(celebraciones)
