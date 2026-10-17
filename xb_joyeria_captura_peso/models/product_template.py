# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.xb_joyeria_peso.models.product_template import TALLA_CAPTURA

HECHURA = 'Hechura estándar'


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    xb_peso_captura = fields.Float(
        'Peso (g)', digits=(16, 3), compute='_compute_xb_captura', inverse='_inverse_xb_peso_captura',
        help='Peso de la pieza de muestra, en gramos. Si la joya se ofrece en varios metales, '
             'pesada en oro de 14 kt; a la talla y el ancho que dice «Se pesa en».')
    xb_se_pesa = fields.Char('Se pesa en', compute='_compute_xb_captura')
    xb_hechura = fields.Float(
        'Hechura', digits=(16, 2), compute='_compute_xb_captura', inverse='_inverse_xb_hechura',
        help='Costo de la «Hechura estándar» de su lista de materiales.')
    xb_precio_desde = fields.Float(
        'Precio desde (con IVA)', digits=(16, 2), compute='_compute_xb_captura',
        help='Lo que cobra la lista de precios de la tienda por la combinación más barata en oro.')
    xb_captura_estado = fields.Selection(
        [('falta', 'Falta peso'), ('sin_metal', 'Sin opción de metal'), ('listo', 'Cotiza por metal')],
        'Estado de captura', compute='_compute_xb_captura')

    # ------------------------------------------------------------------
    def _xb_linea(self, nombre):
        return self.attribute_line_ids.filtered(lambda l: l.attribute_id.name == nombre)

    def _xb_tiene_metal(self):
        return bool(self._xb_linea('Metal').value_ids.filtered(
            lambda v: (v.x_ley or 0) > 0 and (v.x_densidad or 0) > 0))

    def _xb_operacion_hechura(self):
        bom = self.env['mrp.bom'].sudo().search(
            [('product_tmpl_id', '=', self.id), ('product_id', '=', False)], order='sequence, id', limit=1)
        return bom, bom.operation_ids.filtered(lambda o: o.name == HECHURA)[:1]

    def _xb_lista_tienda(self):
        cia = self.company_id or self.env.company
        return self.env['product.pricelist'].sudo().search(
            [('company_id', '=', cia.id)], order='sequence, id', limit=1)

    @api.depends_context('company')
    def _compute_xb_captura(self):
        for t in self:
            peso = t._xb_numero(t.x_studio_peso_joya) if 'x_studio_peso_joya' in t._fields else 0.0
            t.xb_peso_captura = peso
            partes = []
            if len(t._xb_linea('Metal').value_ids) > 1:
                partes.append('oro 14 kt')
            ref = t._xb_referencia()
            if len(t._xb_linea('Medida').value_ids) > 1:
                partes.append('talla %g' % TALLA_CAPTURA)
            elif ref.get('Medida'):
                partes.append('talla %s' % ref['Medida'].name)
            if ref.get('Ancho'):
                partes.append('ancho %s' % ref['Ancho'].name)
            t.xb_se_pesa = ' · '.join(partes) or 'la pieza tal cual'
            _bom, op = t._xb_operacion_hechura()
            t.xb_hechura = op.cost if op else 0.0
            if not t._xb_tiene_metal():
                t.xb_captura_estado = 'sin_metal'
            elif not peso:
                t.xb_captura_estado = 'falta'
            else:
                t.xb_captura_estado = 'listo' if t.xb_precio_por_metal else 'falta'
            t.xb_precio_desde = t._xb_calcular_desde() if t.xb_captura_estado == 'listo' else 0.0

    def _xb_calcular_desde(self):
        lista = self._xb_lista_tienda()
        if not lista:
            return 0.0
        try:
            comb = self._xb_combinacion_desde()
            precio = lista._get_product_price(self.with_context(xb_combinacion=tuple(comb.ids)), 1.0)
            impuestos = self.taxes_id._filter_taxes_by_company(lista.company_id or self.env.company)
            return impuestos.compute_all(precio, currency=lista.currency_id, product=self)['total_included']
        except Exception:  # noqa: BLE001 - un dato mal capturado no debe tumbar la pantalla
            return 0.0

    # ------------------------------------------------------------------
    def _inverse_xb_peso_captura(self):
        for t in self:
            peso = t.xb_peso_captura or 0.0
            t.x_studio_peso_joya = ('%.3f' % peso).rstrip('0').rstrip('.') if peso > 0 else False
            if peso > 0 and t._xb_tiene_metal():
                bom, _op = t._xb_operacion_hechura()
                if not bom:
                    hechura = float(self.env['ir.config_parameter'].sudo().get_param(
                        'xb_joyeria_captura_peso.hechura', 600) or 0)
                    t._xb_poner_hechura(hechura)
                if not t.xb_precio_por_metal:
                    t.xb_precio_por_metal = True

    def _inverse_xb_hechura(self):
        for t in self:
            t._xb_poner_hechura(t.xb_hechura or 0.0)

    def _xb_poner_hechura(self, monto):
        """Deja la «Hechura estándar» de la lista de materiales en `monto`, creando la lista o la
        operación si no existen. El costo de una operación es minutos × costo por hora del taller."""
        self.ensure_one()
        Bom = self.env['mrp.bom'].sudo()
        bom, op = self._xb_operacion_hechura()
        taller = op.workcenter_id or self.env['mrp.routing.workcenter'].sudo().search(
            [('name', '=', HECHURA)], limit=1).workcenter_id
        cia = self.company_id or self.env.company
        if not taller:
            taller = self.env['mrp.workcenter'].sudo().search(
                [('company_id', 'in', [cia.id, False])], limit=1)
        if not taller or not taller.costs_hour:
            return
        minutos = monto * 60.0 / taller.costs_hour
        if op:
            op.time_cycle_manual = minutos
            return
        vals_op = {'name': HECHURA, 'workcenter_id': taller.id,
                   'time_mode': 'manual', 'time_cycle_manual': minutos}
        if bom:
            bom.operation_ids = [(0, 0, vals_op)]
        else:
            Bom.create({'product_tmpl_id': self.id, 'product_qty': 1.0, 'type': 'normal',
                        'company_id': cia.id, 'operation_ids': [(0, 0, vals_op)]})
