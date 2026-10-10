from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    xb_peso_proyectado = fields.Float(
        'Peso proyectado (g)', compute='_compute_xb_pesos', digits=(10, 3),
        help='Lo que va a pesar esta combinación, calculado desde la pieza de '
             'referencia. No es el peso real de una pieza ya fabricada: ése '
             'se captura en el lote.')
    xb_fino_proyectado = fields.Float(
        'Metal fino proyectado (g)', compute='_compute_xb_pesos', digits=(10, 3),
        help='Gramos de metal puro que contiene, según la ley del metal.')
    xb_peso_detalle = fields.Char(
        'Detalle del peso', compute='_compute_xb_pesos',
        help='La frase que se le puede decir al cliente.')

    # ------------------------------------------------------------------
    # La cuenta vive en la plantilla, porque la tienda tiene que poder
    # cotizar combinaciones que todavía no existen como variante. Aquí sólo
    # se le pasan los valores de ESTA variante.
    # ------------------------------------------------------------------
    def _xb_proyectar(self):
        self.ensure_one()
        return self.product_tmpl_id._xb_proyectar_ptavs(
            self.product_template_attribute_value_ids)

    @api.depends('product_template_attribute_value_ids',
                 'product_tmpl_id.x_studio_peso_joya')
    def _compute_xb_pesos(self):
        for prod in self:
            peso, fino, metal = prod._xb_proyectar()
            prod.xb_peso_proyectado = peso
            prod.xb_fino_proyectado = fino
            if peso and metal:
                base = (metal.x_metal or 'metal').lower()
                prod.xb_peso_detalle = (
                    '%.2f g de %s, con %.2f g de %s puro'
                    % (peso, metal.name, fino, base))
            else:
                prod.xb_peso_detalle = ''

    # ------------------------------------------------------------------
    # El costo de la variante
    #
    # El módulo NO fija precios: entrega el costo y deja que una regla de
    # lista de precios («Costo + 226%») ponga el margen, que es donde el
    # negocio lo puede ver y cambiar sin tocar código.
    # ------------------------------------------------------------------
    def _price_compute(self, price_type, uom=None, currency=None, company=None, date=False):
        res = super()._price_compute(
            price_type, uom=uom, currency=currency, company=company, date=date)
        if price_type != 'standard_price':
            return res
        company = company or self.env.company
        date = date or fields.Date.context_today(self)
        for prod in self:
            tmpl = prod.product_tmpl_id
            if not tmpl.xb_precio_por_metal:
                continue
            costo = tmpl.with_company(company)._xb_costo_combinacion(
                prod.product_template_attribute_value_ids)
            if costo is None:
                continue
            if uom:
                costo = prod.uom_id._compute_price(costo, uom)
            if currency:
                costo = prod.cost_currency_id._convert(
                    costo, currency, company, date)
            res[prod.id] = costo
        return res
