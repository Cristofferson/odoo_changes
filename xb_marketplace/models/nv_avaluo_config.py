from odoo import api, fields, models

# Lo que se crea la primera vez que alguien abre la configuración. Son los
# números que se acordaron con el dueño el 21-oct-2026 en la página de tablas;
# de ahí en adelante se cambian desde Marketplace › Configuración › Avalúo.
BANDAS_NATURAL = [(0.30, 60.0), (0.70, 90.0), (1.00, 80.0), (2.00, 55.0), (99.0, 55.0)]
BANDAS_LAB = [(1.00, 210.0), (2.00, 245.0), (99.0, 280.0)]
ESTILOS = [
    # (nombre, peso en 14K a talla 6, montaduras de Anello con las que se compara)
    ('Solitario', 3.0, 'Turín · Solitario clásico de cuatro garras'),
    ('Halo', 4.0, 'Cefalú · Solitario clásico con pavé'),
    ('Pavé', 3.5, 'Cefalú · Solitario clásico con pavé'),
    ('Otro', 3.5, 'Turín · Solitario clásico de cuatro garras'),
]
MARCAS = [
    ('Harry Winston', 1.60, ''), ('Graff', 1.60, ''), ('Van Cleef & Arpels', 1.50, 'van cleef'),
    ('Tiffany & Co.', 1.40, 'tiffany'), ('Cartier', 1.40, ''), ('Bvlgari', 1.30, 'bulgari'),
    ('Chopard', 1.25, ''), ('Boucheron', 1.25, ''), ('Chaumet', 1.25, ''), ('Piaget', 1.25, ''),
    ('Buccellati', 1.25, ''), ('De Beers', 1.25, ''), ('Mikimoto', 1.15, ''), ('Messika', 1.15, ''),
    ('Pomellato', 1.15, ''), ('Repossi', 1.15, ''), ('Fred', 1.15, ''), ('Damiani', 1.15, ''),
    ('David Yurman', 1.10, ''), ('Mauboussin', 1.05, ''), ('Anello', 1.10, ''),
    ('Bizzarro', 1.00, 'bizarro'), ('Carranza y Carranza', 1.00, 'carranza'),
    ('Tutto Terra', 1.00, ''), ('Mario Ramos', 1.00, ''), ('Guvier', 1.00, ''),
]
REGLAS_LAB = [('3', 'A', 'cert'), ('2', 'B', 'cert'), ('1', 'C', 'baja'), ('0', 'C', 'supuesta')]
ACOMPANANTES = [
    ('comprobante', 'Factura o ticket de compra', 2.25),
    ('comprobante', 'Garantía o tarjeta de autenticidad de la marca', 1.5),
    ('comprobante', 'Certificado del diamante original, impreso', 2.0),
    ('comprobante', 'Avalúo anterior de una joyería', 0.5),
    ('comprobante', 'Comprobantes de servicio (ajuste de talla, rodinado, limpieza)', 0.5),
    ('comprobante', 'Folleto, manual de cuidados o libreta de la marca', 0.5),
    ('empaque', 'Estuche original del anillo', 2.0),
    ('empaque', 'Caja exterior o sobrecaja de la marca', 1.0),
    ('empaque', 'Bolsa de compra de la tienda', 0.5),
    ('empaque', 'Estuche o bolsita de viaje', 0.5),
    ('empaque', 'Paño de limpieza u otros accesorios de la marca', 0.5),
    ('pieza', 'Número del certificado grabado con láser en la piedra', 2.0),
]

PROPOSITO = ('Estimar el valor de reventa de la pieza para fijar el rango de precio con que se publica '
             'en el marketplace NOVADIAM. Uso previsto: orientar al vendedor y al comprador de esa '
             'publicación. No sirve para seguros, créditos, garantías, herencias ni trámites legales o fiscales.')
TIPO_VALOR = ('Valor de reventa en el mercado secundario: el precio en que, a la fecha del informe, '
              'cambiaría de manos la pieza usada entre un vendedor y un comprador dispuestos, ambos '
              'informados y sin presión. No es valor de reposición para seguro (que es mayor) ni valor de '
              'liquidación o empeño (que es menor).')
CONDICIONES = """<ol>
<li><b>Naturaleza del documento.</b> Es una estimación de valor de reventa emitida por NOVADIAM para comercializar la pieza en su marketplace. No es un dictamen pericial, ni un avalúo judicial, fiscal o para seguro, ni un certificado de laboratorio gemológico, ni acredita la propiedad. No sustituye el avalúo de un perito valuador registrado.</li>
<li><b>Fuente de la información.</b> Salvo que se indique examen físico en taller, se hizo con fotografías, documentos y declaraciones del vendedor. Se supone que esa información es verdadera, completa y corresponde a esta pieza; NOVADIAM no responde por ella. Si resulta falsa o incompleta, el valor puede cambiar de forma importante.</li>
<li><b>Límites de las fotografías.</b> Con fotografías no se puede confirmar si el diamante es natural o de laboratorio, si tiene tratamientos, su color, pureza, fluorescencia o peso real, la ley del metal, reparaciones o soldaduras, ni el desgaste de las garras. El color depende de la cámara, la luz y la pantalla. Las fotografías no están a escala.</li>
<li><b>Pesos y medidas.</b> Son declarados o estimados, salvo que se indique «verificado» o examen en taller. Un diamante montado no puede pesarse con exactitud sin desmontarlo.</li>
<li><b>Reportes de laboratorio.</b> Los grados citados son los del laboratorio que emitió el reporte, no de NOVADIAM. Mientras el taller no revise la inscripción láser y las medidas, no está comprobado que el reporte corresponda físicamente a esta piedra.</li>
<li><b>Verificación al vender.</b> Cuando la pieza se vende pasa a revisión física en el taller de NOVADIAM: prueba del metal y de su quintado conforme a la NOM-033/1-SE-2020, peso y medidas, revisión del diamante con lupa e instrumental, y cotejo del reporte y su inscripción. Si el resultado no coincide con lo declarado, la venta puede cancelarse o el precio ajustarse, y este informe queda sin efecto.</li>
<li><b>Tipo de valor, moneda y vigencia.</b> El valor es una estimación del precio probable de venta de la pieza usada en el mercado secundario mexicano, en pesos mexicanos con IVA incluido, a la fecha del avalúo. No es valor de reposición para seguro ni de liquidación inmediata. El oro, los diamantes y el tipo de cambio cambian: el informe vale hasta la fecha de vigencia indicada.</li>
<li><b>Conflicto de interés.</b> NOVADIAM cobra una comisión sobre el precio de venta de esta pieza, por lo que tiene interés económico en la operación y esta estimación no es independiente. Quien necesite una opinión imparcial puede pedir un avalúo a un perito independiente.</li>
<li><b>Uso permitido.</b> Sirve solo para publicar y negociar la pieza en NOVADIAM entre el vendedor y los compradores de la plataforma. Usarlo para otro fin (seguro, crédito, empeño, juicio, impuestos), o alterarlo o separar alguna de sus partes, lo invalida. NOVADIAM no responde ante terceros que lo usen así.</li>
<li><b>Propiedad y origen.</b> NOVADIAM no investigó la propiedad ni el origen de la pieza. El vendedor declaró bajo protesta de decir verdad ser su dueño legítimo y que la pieza es de origen lícito, y responde ante cualquier reclamación.</li>
</ol>"""

# Para la pieza que llega al taller. Cambia lo que se dio por cierto con fotos
# por lo que se midió, y dice qué no alcanza a ver el equipo que sí hay.
CONDICIONES_FISICO = """<ol>
<li><b>Naturaleza del documento.</b> Es una estimación de valor de reventa emitida por NOVADIAM, con examen físico de la pieza, para comercializarla en su marketplace. No es un dictamen pericial, ni un avalúo judicial, fiscal o para seguro, ni acredita la propiedad. Solo es certificado de laboratorio gemológico si se adjunta el reporte DIAMANE indicado.</li>
<li><b>Examen realizado.</b> La pieza se examinó en el taller de NOVADIAM con el equipo y los resultados que se detallan en «Pruebas realizadas». Los resultados corresponden a la pieza tal como se recibió y a la fecha del examen.</li>
<li><b>Límites del examen.</b> No se usó análisis por rayos X: la prueba de ácidos y de piedra de toque revisa la superficie y puede no detectar un metal de menor ley bajo un recubrimiento grueso. El detector de diamante sintético separa los diamantes que requieren estudio de laboratorio; cuando el resultado es «referir», el origen no queda confirmado. Algunos tratamientos (relleno de fracturas, HPHT) solo se detectan en laboratorio.</li>
<li><b>Pesos, medidas y grados.</b> El peso del metal es el total en báscula menos el peso de las piedras. Si la piedra no se desmontó, su peso es el del reporte o el estimado por sus medidas, y el color y la pureza graduados montados tienen una tolerancia de un grado.</li>
<li><b>Reportes de laboratorio.</b> Los grados citados en un reporte son los del laboratorio que lo emitió. NOVADIAM cotejó la inscripción láser y las medidas como se indica en el informe.</li>
<li><b>Recepción y resguardo.</b> La pieza estuvo bajo resguardo de NOVADIAM entre la recepción y la devolución indicadas. El estado al recibirla quedó descrito y fotografiado, y el vendedor lo aceptó con su firma de recepción.</li>
<li><b>Tipo de valor, moneda y vigencia.</b> El valor es una estimación del precio probable de venta de la pieza usada en el mercado secundario mexicano, en pesos mexicanos con IVA incluido, a la fecha del avalúo. No es valor de reposición para seguro ni de liquidación inmediata. El oro, los diamantes y el tipo de cambio cambian: el informe vale hasta la fecha de vigencia indicada.</li>
<li><b>Conflicto de interés.</b> NOVADIAM cobra una comisión sobre el precio de venta de esta pieza, por lo que tiene interés económico en la operación y esta estimación no es independiente. Quien necesite una opinión imparcial puede pedir un avalúo a un perito independiente.</li>
<li><b>Uso permitido.</b> Sirve solo para publicar y negociar la pieza en NOVADIAM entre el vendedor y los compradores de la plataforma. Usarlo para otro fin (seguro, crédito, empeño, juicio, impuestos), o alterarlo o separar alguna de sus partes, lo invalida. NOVADIAM no responde ante terceros que lo usen así.</li>
<li><b>Propiedad y origen.</b> NOVADIAM no investigó la propiedad ni el origen de la pieza. El vendedor declaró bajo protesta de decir verdad ser su dueño legítimo y que la pieza es de origen lícito, y responde ante cualquier reclamación.</li>
</ol>"""

# El equipo que hay en el taller (21-oct-2026: todo menos rayos X para metal).
EQUIPO = [
    ('bascula', 'Báscula de joyería'),
    ('acido', 'Prueba de ácidos y piedra de toque'),
    ('detector', 'Detector de diamante sintético'),
    ('lupa', 'Lupa 10x y microscopio'),
    ('patron', 'Piedras patrón de color'),
    ('uv', 'Lámpara ultravioleta'),
    ('calibrador', 'Calibrador o micrómetro'),
]
TIPOS_EQUIPO = [
    ('bascula', 'Peso'), ('acido', 'Ley del metal'), ('xrf', 'Ley del metal (rayos X)'),
    ('detector', 'Natural o laboratorio'), ('lupa', 'Pureza, inscripción y estado'),
    ('patron', 'Color'), ('uv', 'Fluorescencia'), ('calibrador', 'Medidas'), ('otro', 'Otro'),
]

CONFIANZAS = [('A', 'A'), ('B', 'B'), ('C', 'C')]
CALIDADES = [
    ('cert', 'Los del certificado'),
    ('baja', 'Un grado abajo'),
    ('supuesta', 'Supuesta I / SI2'),
]
# Etiqueta de cómo se obtuvo el color y la pureza con que se valúa.
CALIDAD_TEXTO = {
    'cert': 'la del certificado',
    'baja': 'un grado abajo del certificado',
    'supuesta': 'supuesta, sin certificado confiable',
    'taller': 'graduada en el taller de NOVADIAM',
}
DESGASTES = [
    ('A', 'A · como nuevo'),
    ('B', 'B · uso normal'),
    ('C', 'C · rayones y garras gastadas'),
    ('D', 'D · necesita taller'),
]


class NvAvaluoConfig(models.Model):
    _name = 'nv.avaluo.config'
    _description = 'Configuración del avalúo del marketplace'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', required=True, ondelete='cascade',
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    # Piedras
    banda_natural_ids = fields.One2many(
        'nv.avaluo.banda', 'config_id', domain=[('tipo', '=', 'natural')],
        context={'default_tipo': 'natural'}, string='Diamante natural')
    banda_lab_ids = fields.One2many(
        'nv.avaluo.banda', 'config_id', domain=[('tipo', '=', 'lab')],
        context={'default_tipo': 'lab'}, string='Diamante de laboratorio')
    regla_lab_ids = fields.One2many('nv.avaluo.regla.lab', 'config_id', string='Laboratorios')
    acento_natural_usd = fields.Float(
        'Acentos naturales (USD/ct)', default=300.0,
        help='Lo que vale un quilate de piedras de acento naturales usadas.')
    acento_lab_usd = fields.Float(
        'Acentos de laboratorio (USD/ct)', default=50.0)
    dudoso_ct = fields.Float(
        'Quilates «dudosos» sin certificado', default=5.0,
        help='Una piedra de este tamaño o más sin certificado verificable se '
             'toma como dato dudoso (casi siempre es un error de captura: '
             '10.00 en lugar de 0.10).')

    # Metal
    montadura_pct = fields.Float(
        'Montadura sobre el oro fino (%)', default=110.0,
        help='110 % = el oro fino al precio del día más 10 % por estar armado '
             'como anillo, frente a fundirlo.')
    estilo_ids = fields.One2many('nv.avaluo.estilo', 'config_id', string='Estilos')

    # Marca, estado y lo que acompaña
    marca_ids = fields.One2many('nv.avaluo.marca', 'config_id', string='Marcas')
    desgaste_a = fields.Float('A · como nuevo (%)', default=100.0)
    desgaste_b = fields.Float('B · uso normal (%)', default=95.0)
    desgaste_c = fields.Float('C · rayones y garras gastadas (%)', default=85.0)
    desgaste_d = fields.Float('D · necesita taller (%)', default=70.0)
    desgaste_supuesto = fields.Selection(
        DESGASTES, 'Grado supuesto sin foto', default='B', required=True)
    acompanante_ids = fields.One2many('nv.avaluo.acompanante', 'config_id', string='Lo que acompaña')
    acompanante_tope = fields.Float('Lo más que suma todo junto (%)', default=18.0)

    # Piso, sugerido y techo
    rango_a = fields.Float('Rango confianza A (± %)', default=10.0)
    rango_b = fields.Float('Rango confianza B (± %)', default=20.0)
    rango_c = fields.Float('Rango confianza C (± %)', default=30.0)
    piso_alerta = fields.Float(
        'Avisar «¿error?» abajo de (% del piso)', default=50.0)
    descuento_pedido = fields.Float(
        'Descuento a precios pedidos (%)', default=15.0,
        help='A los precios de usados que solo se piden (no ventas cerradas) '
             'se les quita este porcentaje para el precio sugerido.')
    techo_pct = fields.Float(
        'Techo, % del precio de nuevo', default=70.0,
        help='Promesa al comprador: nunca paga más de este porcentaje de lo que '
             'cuesta nuevo (lo más barato entre Anello y el mercado).')

    # Referencia «nuevo en Anello»
    pricelist_id = fields.Many2one(
        'product.pricelist', 'Lista de precios de Anello',
        help='Con esta lista se cotiza la montadura nueva equivalente.')
    medida_ref = fields.Char('Talla de referencia', default='6.0')
    lab_anello = fields.Char(
        'Certificado con que vende Anello', default='DIAMANE',
        help='Nombre del laboratorio (app Gemas). Su recargo se suma al diamante '
             'natural nuevo, igual que en las gemas de la tienda.')
    anello_max_natural = fields.Float('Anello vende naturales hasta (ct)', default=3.5)
    anello_max_lab = fields.Float('Anello vende laboratorio hasta (ct)', default=2.0)

    # Informe de avalúo (PDF)
    vigencia_dias = fields.Integer('Vigencia del informe (días)', default=30)
    valuador_nombre = fields.Char('Valuador', help='Vacío = el usuario que imprime el informe.')
    valuador_cargo = fields.Char('Cargo o credencial', default='Valuador de joyería · NOVADIAM')
    valuador_firma = fields.Image('Firma', max_width=600, max_height=240)
    reporte_proposito = fields.Text('Propósito y uso previsto', default=lambda self: PROPOSITO)
    reporte_tipo_valor = fields.Text('Tipo de valor', default=lambda self: TIPO_VALOR)
    reporte_condiciones = fields.Html('Condiciones · avalúo documental',
                                      default=lambda self: CONDICIONES, sanitize=True)
    reporte_condiciones_fisico = fields.Html('Condiciones · avalúo con examen físico',
                                             default=lambda self: CONDICIONES_FISICO, sanitize=True)

    # Examen físico
    equipo_ids = fields.One2many('nv.avaluo.equipo', 'config_id', string='Equipo del taller')

    _company_uniq = models.Constraint('UNIQUE(company_id)', 'Ya hay una configuración para esta compañía.')

    def _compute_display_name(self):
        for cfg in self:
            cfg.display_name = 'Avalúo del marketplace'

    @api.model
    def _nv_get(self, company=None):
        """La configuración de la compañía; si no existe, se crea con los números acordados."""
        # Una sola configuración: la de la compañía del marketplace.
        company = self.env['res.company'].sudo()._nv_marketplace_company()
        cfg = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if not cfg:
            cfg = self.sudo()._nv_crear(company)
        return cfg

    @api.model
    def _nv_crear(self, company):
        Tmpl = self.env['product.template'].sudo().with_context(active_test=False)
        estilos = []
        for nombre, peso, montadura in ESTILOS:
            refs = Tmpl.search([('name', '=', montadura)])
            estilos.append((0, 0, {'name': nombre, 'peso_14k': peso, 'montadura_ids': [(6, 0, refs.ids)]}))
        vals = {
            'company_id': company.id,
            'banda_natural_ids': [(0, 0, {'tipo': 'natural', 'hasta': h, 'valor': v}) for h, v in BANDAS_NATURAL],
            'banda_lab_ids': [(0, 0, {'tipo': 'lab', 'hasta': h, 'valor': v}) for h, v in BANDAS_LAB],
            'regla_lab_ids': [(0, 0, {'estrellas': s, 'confianza': c, 'calidad': q}) for s, c, q in REGLAS_LAB],
            'estilo_ids': estilos,
            'marca_ids': [(0, 0, {'name': n, 'factor': f, 'alias': a}) for n, f, a in MARCAS],
            'acompanante_ids': [(0, 0, {'grupo': g, 'name': n, 'pct': p, 'sequence': i})
                                for i, (g, n, p) in enumerate(ACOMPANANTES)],
            'equipo_ids': [(0, 0, {'tipo': t, 'name': n, 'sequence': i}) for i, (t, n) in enumerate(EQUIPO)],
        }
        # La lista con la que se vende en anello.mx; si no hay, la primera del sitio.
        Pricelist = self.env['product.pricelist'].sudo()
        lista = Pricelist.search([('name', 'ilike', 'Anello')], limit=1)
        if not lista:
            website = self.env['website'].sudo().search([], limit=1)
            lista = website.pricelist_ids[:1]
        vals['pricelist_id'] = lista.id or False
        return self.create(vals)

    @api.model
    def _nv_sembrar_equipo(self):
        """Al actualizar el módulo: la configuración que ya existía no tiene equipo."""
        for cfg in self.sudo().search([]):
            if not cfg.with_context(active_test=False).equipo_ids:
                cfg.equipo_ids = [(0, 0, {'tipo': t, 'name': n, 'sequence': i}) for i, (t, n) in enumerate(EQUIPO)]
            if not cfg.reporte_condiciones_fisico:
                cfg.reporte_condiciones_fisico = CONDICIONES_FISICO

    def _nv_equipo(self, tipo):
        self.ensure_one()
        return self.equipo_ids.filtered(lambda e: e.tipo == tipo)[:1]

    @api.model
    def action_abrir(self):
        cfg = self._nv_get()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Avalúo',
            'res_model': self._name,
            'res_id': cfg.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _nv_desgaste(self, grado):
        self.ensure_one()
        return {'A': self.desgaste_a, 'B': self.desgaste_b,
                'C': self.desgaste_c, 'D': self.desgaste_d}.get(grado or self.desgaste_supuesto, 100.0)

    def _nv_rango(self, confianza):
        self.ensure_one()
        return {'A': self.rango_a, 'B': self.rango_b, 'C': self.rango_c}.get(confianza, self.rango_c)

    def _nv_banda(self, tipo, ct):
        """El valor de la banda que corresponde al tamaño: % de Rapaport o USD/ct."""
        self.ensure_one()
        bandas = (self.banda_natural_ids if tipo == 'natural' else self.banda_lab_ids).sorted('hasta')
        for b in bandas:
            if ct < b.hasta:
                return b.valor
        return bandas[-1:].valor or 0.0

    def _nv_regla(self, estrellas):
        self.ensure_one()
        regla = self.regla_lab_ids.filtered(lambda r: r.estrellas == str(estrellas or 0))[:1]
        return (regla.confianza or 'C'), (regla.calidad or 'supuesta')

    def _nv_marca(self, texto):
        """La marca de la tabla que corresponde al texto que escribió el vendedor."""
        self.ensure_one()
        norm = self.env['nv.avaluo.marca']._nv_norm(texto)
        if not norm:
            return self.env['nv.avaluo.marca']
        for m in self.marca_ids:
            nombres = [m.name] + [a for a in (m.alias or '').split(',')]
            for n in nombres:
                n = m._nv_norm(n)
                if n and (n == norm or norm.startswith(n + ' ') or n in norm.split(' y ')):
                    return m
        return self.env['nv.avaluo.marca']


class NvAvaluoBanda(models.Model):
    _name = 'nv.avaluo.banda'
    _description = 'Valor de reventa de un diamante por tamaño'
    _order = 'tipo, hasta'

    config_id = fields.Many2one('nv.avaluo.config', required=True, ondelete='cascade')
    tipo = fields.Selection([('natural', 'Natural'), ('lab', 'Laboratorio')], required=True)
    hasta = fields.Float('Menos de (ct)', digits=(6, 2), required=True,
                         help='La banda aplica a piedras de menos de este tamaño. 99 = «o más».')
    valor = fields.Float('Valor', required=True,
                         help='Natural: % del precio Rapaport. Laboratorio: dólares por quilate.')


class NvAvaluoReglaLab(models.Model):
    _name = 'nv.avaluo.regla.lab'
    _description = 'Cómo se toma un certificado según las estrellas del laboratorio'
    _order = 'estrellas desc'

    config_id = fields.Many2one('nv.avaluo.config', required=True, ondelete='cascade')
    estrellas = fields.Selection(
        [('3', '★★★'), ('2', '★★'), ('1', '★'), ('0', 'Sin certificado o sin número')],
        required=True)
    laboratorios = fields.Char(compute='_compute_laboratorios', string='Laboratorios')
    confianza = fields.Selection(CONFIANZAS, required=True)
    calidad = fields.Selection(CALIDADES, 'Color y pureza', required=True)

    @api.depends('estrellas')
    def _compute_laboratorios(self):
        Lab = self.env['x_laboratorios_gemolog'].sudo() if 'x_laboratorios_gemolog' in self.env else None
        for r in self:
            if Lab is None or r.estrellas == '0':
                r.laboratorios = 'Ninguno, «Otro» o certificado sin número' if r.estrellas == '0' else ''
                continue
            labs = Lab.search([('x_studio_pupularidad', '=', r.estrellas)])
            r.laboratorios = ', '.join(l.x_name for l in labs if l.x_name not in ('Ninguno', 'Otro'))


class NvAvaluoEstilo(models.Model):
    _name = 'nv.avaluo.estilo'
    _description = 'Estilo de anillo: peso estimado y montadura de referencia'
    _order = 'sequence, id'

    config_id = fields.Many2one('nv.avaluo.config', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char('Estilo', required=True)
    peso_14k = fields.Float('Peso estimado (g, 14K, talla 6)', digits=(6, 2))
    montadura_ids = fields.Many2many(
        'product.template', 'nv_avaluo_estilo_montadura_rel', 'estilo_id', 'tmpl_id',
        'Montaduras de Anello para comparar',
        help='El precio de nuevo se cotiza con la que ofrezca el mismo metal.')


class NvAvaluoMarca(models.Model):
    _name = 'nv.avaluo.marca'
    _description = 'Cuánto sube el avalúo por la marca'
    _order = 'factor desc, name'

    config_id = fields.Many2one('nv.avaluo.config', required=True, ondelete='cascade')
    name = fields.Char('Marca', required=True)
    alias = fields.Char('También se escribe', help='Otras formas de escribirla, separadas por coma.')
    factor = fields.Float('Factor', digits=(4, 2), default=1.0,
                          help='1.40 = vale 40 % más que la misma pieza sin marca.')

    @api.model
    def _nv_norm(self, texto):
        import unicodedata
        t = unicodedata.normalize('NFKD', (texto or '').lower())
        t = ''.join(c for c in t if not unicodedata.combining(c))
        t = t.replace('&', ' y ').replace('.', ' ')
        return ' '.join(t.split())


class NvAvaluoAcompanante(models.Model):
    _name = 'nv.avaluo.acompanante'
    _description = 'Lo que se entrega con la pieza y cuánto suma'
    _order = 'sequence, id'

    config_id = fields.Many2one('nv.avaluo.config', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    grupo = fields.Selection(
        [('comprobante', 'Comprobantes'), ('empaque', 'Empaque'), ('pieza', 'En la pieza')],
        required=True, default='comprobante')
    name = fields.Char('Qué es', required=True)
    pct = fields.Float('Suma (%)', digits=(5, 2))


class NvAvaluoEquipo(models.Model):
    _name = 'nv.avaluo.equipo'
    _description = 'Equipo del taller para el examen físico'
    _order = 'sequence, id'

    config_id = fields.Many2one('nv.avaluo.config', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    active = fields.Boolean('Activo', default=True)
    tipo = fields.Selection(TIPOS_EQUIPO, 'Qué mide', required=True, default='otro')
    name = fields.Char('Equipo', required=True)
    detalle = fields.Char('Marca, modelo y serie')
    calibracion = fields.Date('Última calibración o revisión')
