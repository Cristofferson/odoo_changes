import re

from odoo import api, fields, models

# Divisa en la que cotiza cada metal base. El campo `x_metal` del valor de
# atributo ya distingue Oro / Plata / Platino.
DIVISA_POR_METAL = {
    'Oro': 'XAU',
    'Plata': 'XAG',
    'Platino': 'XPT',
}

# El peso que se captura en la ficha se entiende en ORO DE 14 KILATES cuando la
# joya ofrece varios metales: es la convención del catálogo y es como viene el
# dato del taller («PESO Oro 14»). Si la joya ofrece un solo metal es una pieza
# concreta y el peso es el suyo, tal cual.
DENSIDAD_CAPTURA_14K = 13.1

# ...y a la talla 4, que es donde el taller pesa la pieza de muestra. Sin esto
# el sistema tomaba como base la talla más chica que ofrece el modelo (la 3) y
# le sumaba metal de más a todas las demás.
TALLA_CAPTURA = 4.0

# Qué parte del peso de la pieza crece con la talla. En una argolla el aro es
# toda la pieza; en un solitario la cabeza y la piedra no cambian de tamaño,
# así que el efecto se diluye.
FRACCION_ARO_ARGOLLA = 1.0
FRACCION_ARO_ANILLO = 0.65


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    xb_precio_por_metal = fields.Boolean(
        'Cotizar por peso de metal',
        help='Cuando está activo, el precio de cada combinación se calcula '
             'con el peso de su metal y la cotización del día, en vez de '
             'sumar los recargos capturados a mano.\n\n'
             'Requiere el peso de la pieza de referencia y que el metal '
             'tenga su ley y su densidad. Si falta alguno, la joya se sigue '
             'cotizando como siempre.')

    xb_margen = fields.Float(
        'Margen sobre costo (%)', default=226.0,
        help='Cuánto se cobra por encima del costo. El costo son tres cosas: '
             'el metal de esa combinación, más lo que diga la lista de '
             'materiales (piedras y hechura), más nada. 226% significa cobrar '
             '3.26 veces el costo.')

    xb_ref_modelo = fields.Char(
        'Referencia del modelo', copy=False, index=True,
        help='La referencia del diseño, guardada aparte para que no se pierda.\n\n'
             'Odoo calcula `default_code` a partir de la ÚNICA variante del '
             'producto: en cuanto una joya materializa su segunda combinación '
             '—algo que pasa con cada venta de un modelo configurable— el '
             'código de la plantilla se vacía y el modelo deja de encontrarse '
             'por su número. Aquí queda a salvo.')

    @api.depends('product_variant_ids.default_code', 'xb_ref_modelo')
    def _compute_default_code(self):
        """Devuelve la referencia guardada cuando Odoo se queda sin ninguna."""
        super()._compute_default_code()
        for t in self:
            if not t.default_code and t.xb_ref_modelo:
                t.default_code = t.xb_ref_modelo

    def write(self, vals):
        res = super().write(vals)
        # Al capturar una referencia se guarda también en su sitio seguro.
        if vals.get('default_code'):
            for t in self:
                if t.xb_ref_modelo != vals['default_code']:
                    super(ProductTemplate, t).write({'xb_ref_modelo': vals['default_code']})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for t, vals in zip(recs, vals_list):
            if vals.get('default_code') and not t.xb_ref_modelo:
                t.xb_ref_modelo = vals['default_code']
        return recs

    # ==================================================================
    # Proyección del peso a partir de una combinación
    #
    # Todo esto vive en la plantilla —y no en la variante— porque la tienda
    # tiene que poder poner precio a una combinación que TODAVÍA NO EXISTE.
    # Los atributos de estas joyas son dinámicos (si no, serían 50,000
    # variantes), así que al pintar la ficha no hay ningún `product.product`
    # que consultar: Odoo cotiza la plantilla. La variante nace después, al
    # agregar al carrito.
    # ==================================================================
    @api.model
    def _xb_numero(self, texto):
        """Primer número de un texto. Las capturas de peso vienen sucias
        ('4,8 grs', '3.63grs') y los anchos como '4mm'."""
        m = re.search(r'\d+(?:[.,]\d+)?', (texto or '').replace(',', '.'))
        return float(m.group(0)) if m else 0.0

    @api.model
    def _xb_circunferencia(self, talla):
        """Circunferencia interior en mm de una talla (escala estadounidense,
        que es la que usan los valores del atributo Medida)."""
        return 3.14159265 * (11.54 + 0.8128 * talla)

    def _xb_valor_de(self, ptavs, nombre_atributo):
        """El valor de atributo que la combinación trae para un atributo dado."""
        v = ptavs.filtered(lambda p: p.attribute_id.name == nombre_atributo)[:1]
        return v.product_attribute_value_id if v else False

    def _xb_referencia(self):
        """La combinación de referencia: el valor más bajo que ofrezca la
        plantilla en cada atributo. Así todos los factores son mayores o
        iguales a uno y el precio base resulta ser el de la combinación más
        barata, que además es el «desde $X» de la ficha."""
        self.ensure_one()
        ref = {}
        for linea in self.attribute_line_ids:
            nombre = linea.attribute_id.name
            valores = linea.value_ids
            if not valores:
                continue
            if nombre == 'Metal':
                # el de menor ley, y a igualdad el de menor densidad
                candidatos = valores.filtered(lambda v: (v.x_ley or 0) > 0)
                if candidatos:
                    ref[nombre] = min(
                        candidatos,
                        key=lambda v: (v.x_ley, v.x_densidad or 0))
            elif nombre in ('Ancho', 'Medida'):
                # Sin los valores que no son un número: el atributo Medida
                # trae un «Otro» que, valiendo cero, ganaría siempre la
                # comparación y dejaría la talla sin efecto.
                numericos = valores.filtered(lambda v: self._xb_numero(v.name) > 0)
                if numericos:
                    ref[nombre] = min(
                        numericos, key=lambda v: self._xb_numero(v.name))
        return ref

    def _xb_proyectar_ptavs(self, ptavs):
        """(peso, fino, metal) de una combinación, o (0, 0, False) si faltan
        datos para calcularlo."""
        self.ensure_one()
        peso_ref = 0.0
        if 'x_studio_peso_joya' in self._fields:
            peso_ref = self._xb_numero(self.x_studio_peso_joya)
        if peso_ref <= 0:
            return 0.0, 0.0, False

        metal = self._xb_valor_de(ptavs, 'Metal')
        if not metal or not (metal.x_ley or 0) or not (metal.x_densidad or 0):
            return 0.0, 0.0, False

        ref = self._xb_referencia()

        # Densidad a la que corresponde el peso capturado. Con varios metales
        # ofrecidos, el dato viene en 14 Kt; con uno solo, en ese mismo metal.
        linea_metal = self.attribute_line_ids.filtered(
            lambda l: l.attribute_id.name == 'Metal')
        varios = len(linea_metal.value_ids) > 1
        dens_base = DENSIDAD_CAPTURA_14K if varios else (metal.x_densidad or 1)
        factor = (metal.x_densidad or 0) / (dens_base or 1)

        ancho = self._xb_valor_de(ptavs, 'Ancho')
        ancho_ref = ref.get('Ancho')
        if ancho and ancho_ref:
            mm, mm_ref = self._xb_numero(ancho.name), self._xb_numero(ancho_ref.name)
            if mm and mm_ref:
                factor *= mm / mm_ref

        medida = self._xb_valor_de(ptavs, 'Medida')
        medida_ref = ref.get('Medida')
        if medida and medida_ref:
            t = self._xb_numero(medida.name)
            # La talla base es aquella a la que se pesó la pieza, no la más
            # chica del modelo. Si el modelo ofrece una sola talla, esa es.
            linea_medida = self.attribute_line_ids.filtered(
                lambda l: l.attribute_id.name == 'Medida')
            t_ref = (TALLA_CAPTURA if len(linea_medida.value_ids) > 1
                     else self._xb_numero(medida_ref.name))
            if t and t_ref:
                fraccion = FRACCION_ARO_ARGOLLA if ancho else FRACCION_ARO_ANILLO
                crece = self._xb_circunferencia(t) / self._xb_circunferencia(t_ref)
                factor *= 1.0 + fraccion * (crece - 1.0)

        peso = peso_ref * factor
        return peso, peso * (metal.x_ley or 0), metal

    def _xb_cotizacion(self, metal):
        """Pesos por gramo de metal puro, de la divisa que le corresponda."""
        nombre = DIVISA_POR_METAL.get((metal.x_metal or '').strip())
        if not nombre:
            return 0.0
        divisa = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', nombre)], limit=1)
        if not divisa or not divisa.rate:
            return 0.0
        return 1.0 / divisa.rate

    # ------------------------------------------------------------------
    # Costo de la lista de materiales para una combinación
    # ------------------------------------------------------------------
    @api.model
    def _xb_linea_aplica(self, restriccion, ptavs):
        """Misma regla que usa `mrp` en `_match_all_variant_values`: una línea
        sin restricción entra siempre, y una restringida entra si la
        combinación trae uno de sus valores por cada atributo nombrado."""
        if not restriccion:
            return True
        return len(restriccion & ptavs) == len(restriccion.attribute_id)

    def _xb_costo_ldm(self, ptavs, cia):
        """Lo que cuesta la joya sin contar el metal: piedras y hechura, según
        la lista de materiales y para ESTA combinación.

        Es el equivalente de `product.product._compute_bom_price`, pero
        trabajando desde la plantilla: en la tienda no hay variante que
        consultar.
        """
        self.ensure_one()
        if 'mrp.bom' not in self.env:
            return 0.0
        bom = self.env['mrp.bom'].sudo().search(
            [('product_tmpl_id', '=', self.id), ('product_id', '=', False)],
            order='sequence, id', limit=1)
        if not bom:
            return 0.0
        total = 0.0
        for op in bom.operation_ids:
            if not op.active:
                continue
            if self._xb_linea_aplica(op.bom_product_template_attribute_value_ids, ptavs):
                total += op.cost
        for linea in bom.bom_line_ids:
            if not self._xb_linea_aplica(
                    linea.bom_product_template_attribute_value_ids, ptavs):
                continue
            comp = linea.product_id.with_company(cia)
            total += comp.uom_id._compute_price(
                comp.standard_price, linea.product_uom_id) * linea.product_qty
        # La lista puede estar hecha para varias piezas de golpe.
        return total / (bom.product_qty or 1.0)

    # ------------------------------------------------------------------
    # El COSTO de una combinación — y nada más que el costo
    #
    # Aquí termina el trabajo del módulo. Lo que sigue —el margen, el
    # redondeo, quién paga qué, desde cuándo— es configuración de listas de
    # precios y se hace en la pantalla de Odoo, no en código.
    #
    # La razón de que esto tenga que ser código es una sola: una fórmula de
    # lista de precios sólo sabe leer tres números (precio de venta, costo, u
    # otra lista). No sabe calcular los gramos de oro fino de una combinación
    # que ni siquiera existe todavía como variante. Eso es lo que se resuelve
    # aquí; el resto se deja en manos de Odoo.
    # ------------------------------------------------------------------
    def _xb_costo_combinacion(self, ptavs):
        """Lo que CUESTA una combinación, o None si esta joya no se cotiza así.

        Dos pedazos: el metal de ESTA combinación al precio del día, más lo que
        diga la lista de materiales (piedras y hechura). Sin margen.
        """
        self.ensure_one()
        if not self.xb_precio_por_metal:
            return None
        _peso, fino, metal = self._xb_proyectar_ptavs(ptavs)
        if not fino or not metal:
            return None
        por_gramo = self._xb_cotizacion(metal)
        if not por_gramo:
            return None
        cia = self.company_id or self.env.company
        return (fino * por_gramo) + self._xb_costo_ldm(ptavs, cia)

    def _xb_ptavs_del_contexto(self):
        """La combinación que se está cotizando, si alguien la puso en el
        contexto (lo hace `_get_product_price_context`)."""
        ids = self.env.context.get('xb_combinacion')
        if ids:
            return self.env['product.template.attribute.value'].browse(ids)
        return self.env['product.template.attribute.value']

    def _get_product_price_context(self, combination):
        """Deja la combinación en el contexto para que el costo se pueda
        calcular más abajo. Es el gancho nativo que ya usa Odoo para llevar
        los recargos por atributo hasta `_price_compute`."""
        res = super()._get_product_price_context(combination)
        if self.xb_precio_por_metal and combination:
            res['xb_combinacion'] = tuple(combination.ids)
        return res

    def _price_compute(self, price_type, uom=None, currency=None, company=None, date=False):
        """Cuando una regla de lista de precios pregunta el COSTO, se le
        responde con el de la combinación que se está cotizando.

        Una regla con `base = Costo` hace exactamente
        `product._price_compute('standard_price')`, así que con esto una regla
        nativa «Costo + 226%» funciona igual para una variante ya fabricada
        que para una que nace en el momento de la venta.
        """
        res = super()._price_compute(
            price_type, uom=uom, currency=currency, company=company, date=date)
        if price_type != 'standard_price':
            return res
        company = company or self.env.company
        date = date or fields.Date.context_today(self)
        for tmpl in self:
            if not tmpl.xb_precio_por_metal:
                continue
            costo = tmpl.with_company(company)._xb_costo_combinacion(
                tmpl._xb_ptavs_del_contexto())
            if costo is None:
                continue
            if uom:
                costo = tmpl.uom_id._compute_price(costo, uom)
            if currency:
                costo = tmpl.cost_currency_id._convert(
                    costo, currency, company, date)
            res[tmpl.id] = costo
        return res
