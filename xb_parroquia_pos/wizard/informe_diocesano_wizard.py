from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


def _primer_dia_mes(hoy):
    return hoy.replace(day=1)


def _ultimo_dia_mes(hoy):
    siguiente = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1)
    return siguiente - timedelta(days=1)


class ParroquiaInformeWizard(models.TransientModel):
    _name = 'parroquia.informe.wizard'
    _description = 'Informe mensual diocesano / recibo de ingresos'

    fecha_desde = fields.Date(
        string='Desde', required=True,
        default=lambda self: _primer_dia_mes(fields.Date.context_today(self)))
    fecha_hasta = fields.Date(
        string='Hasta', required=True,
        default=lambda self: _ultimo_dia_mes(fields.Date.context_today(self)))

    def _validar(self):
        self.ensure_one()
        if self.fecha_hasta < self.fecha_desde:
            raise UserError('La fecha final debe ser posterior a la inicial.')

    def action_imprimir_informe(self):
        self._validar()
        return self.env.ref(
            'xb_parroquia_pos.action_report_informe_diocesano'
        ).report_action(self)

    def action_crear_recibo(self):
        """Suma las categorías de ingreso del rango y crea el recibo foliado."""
        self._validar()
        Datos = self.env['parroquia.informe.datos']
        from odoo.addons.xb_parroquia_pos.models.parroquia_diocesano import \
            CATEGORIAS_INGRESO
        totales = Datos.totales_ingresos(self.fecha_desde, self.fecha_hasta)
        lineas = [(0, 0, {'concepto': etiqueta, 'monto': totales[clave]})
                  for clave, etiqueta in CATEGORIAS_INGRESO
                  if totales.get(clave)]
        if not lineas:
            raise UserError('No hay ingresos cobrados en ese rango.')
        recibo = self.env['parroquia.recibo'].create({
            'periodo_desde': self.fecha_desde,
            'periodo_hasta': self.fecha_hasta,
            'linea_ids': lineas,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'parroquia.recibo',
            'res_id': recibo.id,
            'view_mode': 'form',
            'target': 'current',
        }
