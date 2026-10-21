import re

from odoo import api, fields, models

from .nv_avaluo_config import DESGASTES

# Escalas de grado para «un grado abajo» de lo que dice el certificado.
COLORES = 'DEFGHIJKLMNOPQRSTUVWXYZ'
PUREZAS = ['FL', 'IF', 'VVS1', 'VVS2', 'VS1', 'VS2', 'SI1', 'SI2', 'I1', 'I2', 'I3']
# Calidad que se supone cuando no hay certificado en el que confiar.
COLOR_SUPUESTO, PUREZA_SUPUESTA = 'I', 'SI2'

# Ley y densidad relativa a 14K, por si el metal no trae las suyas.
LEY_KT = {'10K': 0.417, '14K': 0.585, '18K': 0.750, 'PT': 0.950}
DENS_KT = {'10K': 0.89, '14K': 1.00, '18K': 1.18, 'PT': 1.63}
# Densidad del 14K con la que se capturan los pesos del catálogo (xb_joyeria_peso).
DENSIDAD_14K = 13.1
# Peso que un vendedor puede escribir con sentido para un anillo (g).
PESO_MIN, PESO_MAX = 1.0, 15.0
# Un quilate pesa 0.2 g: se resta del peso en báscula para quedarse con el metal.
GRAMOS_POR_QUILATE = 0.2

TIPOS_INFORME = [('documental', 'Documental (fotos y documentos)'), ('fisico', 'Con examen físico en taller')]
LEYES_PROBADAS = [('10K', '10K · 0.417'), ('14K', '14K · 0.585'), ('18K', '18K · 0.750'),
                  ('PT', 'Platino 950'), ('menor', 'Menor a 10K o no es oro')]
ORIGENES = [('natural', 'Diamante natural'), ('lab', 'Diamante de laboratorio'),
            ('referir', 'Referir a laboratorio (no concluyente)'), ('simulante', 'No es diamante')]
FLUORESCENCIAS = [('none', 'Nula'), ('faint', 'Débil'), ('medium', 'Media'),
                  ('strong', 'Fuerte'), ('very_strong', 'Muy fuerte')]
LASER = [('coincide', 'Coincide con el reporte'), ('no_coincide', 'NO coincide con el reporte'),
         ('sin', 'La piedra no tiene inscripción')]

VEREDICTOS = [
    ('dudoso', 'Dato dudoso'),
    ('sin_precio', 'Sin precio'),
    ('bajo', 'Muy bajo: ¿error?'),
    ('sin_ct', 'Faltan los quilates'),
    ('sin_nuevo', 'A revisión: sin pieza nueva comparable'),
    ('techo_bajo', 'A revisión: el techo queda abajo del piso'),
    ('bajar', 'Debe bajar al techo'),
    ('bajo_piso', 'Se publica (abajo del piso: avisarle)'),
    ('rapido', 'Se publica: se vende rápido'),
    ('tardar', 'Se publica: puede tardar'),
    ('publica', 'Se publica'),
]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ---------------- Lo que se captura ----------------
    nv_peso_g = fields.Float(
        'Peso verificado (g)', digits=(6, 2),
        help='Peso real de la pieza (foto en báscula o pesada en taller). Si está '
             'vacío se usa el peso que escribió el vendedor, y si no es creíble, '
             'el peso típico del estilo.')
    nv_desgaste = fields.Selection(
        DESGASTES, 'Desgaste',
        help='Vacío = el grado supuesto de la configuración.')
    nv_acompanante_ids = fields.Many2many(
        'nv.avaluo.acompanante', 'nv_product_acompanante_rel', 'tmpl_id', 'acompanante_id',
        'Lo que acompaña a la pieza')
    nv_mercado_nuevo = fields.Monetary(
        'Nuevo en el mercado', currency_field='currency_id',
        help='Lo más barato que cuesta una pieza igual NUEVA en otra joyería.')
    nv_usado_min = fields.Monetary('Usados desde', currency_field='currency_id')
    nv_usado_max = fields.Monetary('Usados hasta', currency_field='currency_id')
    nv_usado_tipo = fields.Selection(
        [('vendido', 'Ventas cerradas'), ('pedido', 'Precios pedidos')],
        'Tipo de dato de usados', default='pedido')
    nv_mercado_notas = fields.Text('Fuentes del mercado')
    nv_examen_fecha = fields.Date(
        'Examen físico', help='Fecha en que la pieza se examinó en mano en el taller. Vacío = avalúo documental.')
    nv_metal_probado = fields.Boolean(
        'Metal probado en taller', help='La ley del metal se comprobó (quintado y prueba de ácido o electrónica).')
    nv_cert_verificado = fields.Boolean(
        'Reporte verificado', help='El número del certificado se consultó en la base en línea del laboratorio '
                                   'y sus datos coinciden con lo declarado.')

    # ---------------- Examen físico en taller ----------------
    nv_av_tipo = fields.Selection(
        TIPOS_INFORME, 'Tipo de avalúo', default='documental', required=True,
        help='Con examen físico, lo que se midió en el taller reemplaza lo declarado por el vendedor.')
    nv_rec_folio = fields.Char('Folio de recepción', copy=False)
    nv_rec_fecha = fields.Datetime('Recibida', copy=False)
    nv_rec_user_id = fields.Many2one('res.users', 'Recibió', copy=False)
    nv_rec_estado = fields.Text('Estado al recibirla', copy=False,
                                help='Cómo llegó: golpes, piedras flojas, garras, suciedad. Lo firma el vendedor.')
    nv_examen_user_id = fields.Many2one('res.users', 'Examinó', copy=False)
    nv_dev_fecha = fields.Datetime('Devuelta o entregada', copy=False)
    nv_dev_persona = fields.Char('Entregada a', copy=False)
    nv_fis_ley = fields.Selection(LEYES_PROBADAS, 'Ley comprobada', copy=False)
    nv_fis_quintado = fields.Char('Quintado leído', copy=False, help='Lo que dice el quintado, leído con lupa.')
    nv_fis_origen = fields.Selection(ORIGENES, 'Detector de sintéticos', copy=False)
    nv_fis_color = fields.Selection([(c, c) for c in COLORES], 'Color en taller', copy=False)
    nv_fis_pureza = fields.Selection([(p, p) for p in PUREZAS], 'Pureza en taller', copy=False)
    nv_fis_fluorescencia = fields.Selection(FLUORESCENCIAS, 'Fluorescencia (UV)', copy=False)
    nv_fis_medidas = fields.Char('Medidas de la piedra (mm)', copy=False)
    nv_fis_ct = fields.Float('Peso estimado por medidas (ct)', digits=(6, 2), copy=False)
    nv_fis_desmontada = fields.Boolean('Se desmontó y se pesó la piedra', copy=False)
    nv_fis_laser = fields.Selection(LASER, 'Inscripción láser', copy=False)
    nv_fis_observaciones = fields.Text('Observaciones del examen', copy=False,
                                       help='Garras, soldaduras, reparaciones, desgaste real.')
    nv_reporte_diamane = fields.Char('Número ICERT', copy=False,
                                     help='Número del reporte del laboratorio DIAMANE (ICERT) con que se certifica la gema.')
    nv_fis_foto_1 = fields.Image('Foto de taller 1', max_width=1600, max_height=1600, copy=False)
    nv_fis_foto_2 = fields.Image('Foto de taller 2', max_width=1600, max_height=1600, copy=False)
    nv_fis_foto_3 = fields.Image('Foto de taller 3', max_width=1600, max_height=1600, copy=False)
    nv_fis_foto_4 = fields.Image('Foto de taller 4', max_width=1600, max_height=1600, copy=False)

    # ---------------- Lo que se calcula ----------------
    nv_av_confianza = fields.Selection(
        [('A', 'A'), ('B', 'B'), ('C', 'C')], 'Confianza', compute='_compute_nv_avaluo')
    nv_av_oro = fields.Monetary('Oro fino', compute='_compute_nv_avaluo', currency_field='currency_id')
    nv_av_hechura = fields.Monetary('Hechura', compute='_compute_nv_avaluo', currency_field='currency_id')
    nv_av_diamante = fields.Monetary('Diamante central', compute='_compute_nv_avaluo', currency_field='currency_id')
    nv_av_acentos = fields.Monetary('Acentos', compute='_compute_nv_avaluo', currency_field='currency_id')
    nv_avaluo_metal = fields.Monetary(
        'Avalúo · metal', compute='_compute_nv_avaluo', currency_field='currency_id')
    nv_avaluo_piedras = fields.Monetary(
        'Avalúo · piedras', compute='_compute_nv_avaluo', currency_field='currency_id')
    nv_avaluo = fields.Monetary(
        'Valor intrínseco', compute='_compute_nv_avaluo', currency_field='currency_id',
        help='Oro al precio del día + diamante a valor de reventa, con marca, '
             'desgaste y lo que acompaña a la pieza.')
    nv_av_piso = fields.Monetary('Piso', compute='_compute_nv_avaluo', currency_field='currency_id',
                                 help='Lo mínimo del rango del valor intrínseco. Protege al vendedor.')
    nv_av_piso_max = fields.Monetary('Valor intrínseco hasta', compute='_compute_nv_avaluo',
                                     currency_field='currency_id')
    nv_av_sugerido_min = fields.Monetary('Sugerido desde', compute='_compute_nv_avaluo',
                                         currency_field='currency_id')
    nv_av_sugerido_max = fields.Monetary('Sugerido hasta', compute='_compute_nv_avaluo',
                                         currency_field='currency_id')
    nv_av_nuevo_anello = fields.Monetary('Nuevo en Anello', compute='_compute_nv_avaluo',
                                         currency_field='currency_id')
    nv_av_techo = fields.Monetary('Techo', compute='_compute_nv_avaluo', currency_field='currency_id',
                                  help='El % configurado de lo más barato que cuesta nuevo. Protege al comprador.')
    nv_av_veredicto = fields.Selection(VEREDICTOS, 'Qué pasa con el precio', compute='_compute_nv_avaluo')
    nv_av_veredicto_texto = fields.Char('Resultado', compute='_compute_nv_avaluo')
    nv_avaluo_detalle = fields.Text('Cómo se calculó', compute='_compute_nv_avaluo')

    # Los acentos (`dmn_accent_ids`) y los campos de gema (`x_studio_*`) NO se
    # declaran como dependencias: los aportan otros módulos o Studio, y
    # declararlos rompe la carga si no existen. Se leen igual al calcular.
    @api.depends('nv_is_listing', 'list_price', 'nv_carats', 'nv_brand', 'nv_cert_number',
                 'x_studio_peso_joya', 'nv_peso_g', 'nv_desgaste', 'nv_acompanante_ids',
                 'nv_mercado_nuevo', 'nv_usado_min', 'nv_usado_max', 'nv_usado_tipo',
                 'nv_av_tipo', 'nv_fis_ley', 'nv_fis_origen', 'nv_fis_color', 'nv_fis_pureza',
                 'nv_fis_ct', 'nv_fis_laser', 'attribute_line_ids.value_ids')
    def _compute_nv_avaluo(self):
        vacio = dict(nv_av_confianza=False, nv_av_oro=0, nv_av_hechura=0, nv_av_diamante=0,
                     nv_av_acentos=0, nv_avaluo_metal=0, nv_avaluo_piedras=0, nv_avaluo=0,
                     nv_av_piso=0, nv_av_piso_max=0, nv_av_sugerido_min=0, nv_av_sugerido_max=0,
                     nv_av_nuevo_anello=0, nv_av_techo=0, nv_av_veredicto=False,
                     nv_av_veredicto_texto=False, nv_avaluo_detalle=False)
        for t in self:
            if not t.nv_is_listing:
                t.update(vacio)
                continue
            t.update(t._nv_valuar())

    # ------------------------------------------------------------------
    # Motor
    # ------------------------------------------------------------------
    def _nv_valuar(self):
        self.ensure_one()
        cfg = self.env['nv.avaluo.config']._nv_get()
        mxn = lambda v: '$' + format(round(v or 0), ',')
        pasos = []
        tc = self._nv_tipo_cambio()

        # --- Certificado, o lo que se vio en el taller ---
        p = self._nv_piedra(cfg)
        lab_nombre, est, confianza, calidad = p['lab'], p['estrellas'], p['confianza'], p['calidad']
        color, pureza, es_lab, ct = p['color'], p['pureza'], p['es_lab'], p['ct']

        # --- Metal ---
        estilo = self._nv_estilo(cfg)
        metal, kt, ley, nombre_metal = self._nv_metal(cfg)
        peso, origen_peso = self._nv_peso(estilo, metal, kt)
        if self.nv_peso_g:
            # La báscula pesa la pieza armada: las piedras no son metal.
            ct_piedras = ct + (sum(self.dmn_accent_ids.mapped('carats_total'))
                               if 'dmn_accent_ids' in self._fields else 0.0)
            peso = max(peso - ct_piedras * GRAMOS_POR_QUILATE, 0.0)
            if ct_piedras:
                origen_peso = '(báscula, sin %.2f ct de piedras)' % ct_piedras
        por_gramo = self._nv_cotizacion(metal, kt)
        oro = peso * ley * por_gramo
        hechura = oro * (cfg.montadura_pct / 100.0 - 1.0)
        pasos.append('Metal: %.2f g %s de %s × ley %.3f × %s/g = %s; hechura %s %%: %s' % (
            peso, origen_peso, nombre_metal, ley, mxn(por_gramo), mxn(oro), round(cfg.montadura_pct), mxn(hechura)))

        # --- Diamante central ---
        dudoso = ct >= cfg.dudoso_ct and est == 0 and not p['fisico']
        diamante = 0.0
        if p['simulante']:
            pasos.append('Piedra: el detector indica que no es diamante; no se valúa como diamante.')
        elif dudoso:
            pasos.append('Piedra: %.2f ct sin certificado verificable: dato dudoso, no se valúa.' % ct)
        elif not ct:
            pasos.append('Piedra: no dice cuántos quilates tiene, no se valúa.')
        elif es_lab:
            usd = cfg._nv_banda('lab', ct)
            diamante = ct * usd * tc
            pasos.append('Piedra %.2f ct de laboratorio: %s USD/ct × %.2f = %s' % (ct, round(usd), tc, mxn(diamante)))
        else:
            rap, _nota = self._nv_precio_rapaport(ct, color, pureza, self._nv_forma())
            pct = cfg._nv_banda('natural', ct)
            diamante = ct * rap * pct / 100.0 * tc
            cert = ('%s %s' % (lab_nombre, '★' * est)) if est else 'sin certificado verificable'
            pasos.append('Piedra %.2f ct natural, %s, %s / %s%s: Rapaport %s USD/ct × %s %% = %s' % (
                ct, cert, color, pureza, {'baja': ' (un grado abajo)', 'supuesta': ' (supuesta)',
                                          'taller': ' (graduada en taller)'}.get(calidad, ''),
                format(round(rap), ','), round(pct), mxn(diamante)))

        acentos = 0.0
        if 'dmn_accent_ids' in self._fields and self.dmn_accent_ids:
            ct_acentos = sum(self.dmn_accent_ids.mapped('carats_total'))
            usd = cfg.acento_lab_usd if es_lab else cfg.acento_natural_usd
            acentos = ct_acentos * usd * tc
            pasos.append('Acentos: %.3f ct × %s USD/ct = %s' % (ct_acentos, round(usd), mxn(acentos)))

        # --- Marca, desgaste, lo que acompaña ---
        marca = cfg._nv_marca(self.nv_brand)
        f_marca = marca.factor if marca else 1.0
        f_desgaste = cfg._nv_desgaste(self.nv_desgaste) / 100.0
        extra = min(sum(self.nv_acompanante_ids.mapped('pct')), cfg.acompanante_tope)
        base = (oro + hechura + diamante + acentos) * f_marca * f_desgaste * (1 + extra / 100.0)
        pasos.append('Marca %s × %.2f · desgaste %s × %s %% · lo que acompaña +%s %% → valor intrínseco %s' % (
            marca.name if marca else (self.nv_brand or 'sin marca'), f_marca,
            self.nv_desgaste or (cfg.desgaste_supuesto + ' supuesto'), round(f_desgaste * 100),
            round(extra, 2), mxn(base)))
        rango = cfg._nv_rango(confianza) / 100.0
        piso, piso_max = base * (1 - rango), base * (1 + rango)
        pasos.append('Piso (confianza %s, ±%s %%): %s – %s' % (confianza, round(rango * 100), mxn(piso), mxn(piso_max)))

        # --- Techo: lo más barato que cuesta nuevo ---
        nuevo_anello = 0.0 if (dudoso or not ct or p['simulante']) else self._nv_nuevo_anello(cfg, estilo, metal, kt, ct, es_lab, color, pureza, tc, pasos)
        refs = [v for v in (nuevo_anello, self.nv_mercado_nuevo) if v and v > 0]
        techo = min(refs) * cfg.techo_pct / 100.0 if refs else 0.0
        if techo:
            pasos.append('Techo: %s %% de %s (Anello %s, mercado %s) = %s' % (
                round(cfg.techo_pct), mxn(min(refs)), mxn(nuevo_anello) if nuevo_anello else '—',
                mxn(self.nv_mercado_nuevo) if self.nv_mercado_nuevo else '—', mxn(techo)))

        # --- Sugerido: mercado de usados ---
        sug_min = sug_max = 0.0
        if self.nv_usado_min or self.nv_usado_max:
            f = 1.0 if self.nv_usado_tipo == 'vendido' else 1 - cfg.descuento_pedido / 100.0
            sug_min = (self.nv_usado_min or self.nv_usado_max) * f
            sug_max = (self.nv_usado_max or self.nv_usado_min) * f
            if techo:
                sug_min, sug_max = min(sug_min, techo), min(sug_max, techo)
            pasos.append('Sugerido: usados %s %s – %s → %s – %s' % (
                'vendidos' if self.nv_usado_tipo == 'vendido' else 'pedidos (−%s %%)' % round(cfg.descuento_pedido),
                mxn(self.nv_usado_min), mxn(self.nv_usado_max), mxn(sug_min), mxn(sug_max)))

        # --- Qué pasa con lo que pide ---
        precio = self.list_price or 0.0
        if dudoso:
            v = 'dudoso'
        elif not precio:
            v = 'sin_precio'
        elif base and precio < piso * cfg.piso_alerta / 100.0:
            v = 'bajo'
        elif not ct:
            v = 'sin_ct'
        elif not techo:
            v = 'sin_nuevo'
        elif techo < piso:
            v = 'techo_bajo'
        elif precio > techo:
            v = 'bajar'
        elif precio < piso:
            v = 'bajo_piso'
        elif sug_max:
            v = 'rapido' if precio <= sug_max else 'tardar'
        else:
            v = 'publica'
        texto = dict(VEREDICTOS)[v]
        if v == 'bajar':
            texto = 'Debe bajar a %s' % mxn(techo)

        return dict(
            nv_av_confianza=confianza, nv_av_oro=oro, nv_av_hechura=hechura,
            nv_av_diamante=diamante, nv_av_acentos=acentos,
            nv_avaluo_metal=oro + hechura, nv_avaluo_piedras=diamante + acentos,
            nv_avaluo=base, nv_av_piso=piso, nv_av_piso_max=piso_max,
            nv_av_sugerido_min=sug_min, nv_av_sugerido_max=sug_max,
            nv_av_nuevo_anello=nuevo_anello, nv_av_techo=techo,
            nv_av_veredicto=v, nv_av_veredicto_texto=texto,
            nv_avaluo_detalle='\n'.join(pasos),
        )

    # ------------------------------------------------------------------
    # Datos de la pieza
    # ------------------------------------------------------------------
    def _nv_valor_atributo(self, nombre):
        """El valor (product.attribute.value) del atributo `nombre` de la pieza."""
        linea = self.attribute_line_ids.filtered(lambda l: l.attribute_id.name == nombre)
        return linea.value_ids[:1]

    @api.model
    def _nv_kilataje(self, metal):
        nombre = (metal.name or '') if metal else ''
        if 'platino' in nombre.lower():
            return 'PT'
        m = re.search(r'(\d+)\s*k', nombre, re.I)
        return (m.group(1) + 'K') if m else '10K'

    def _nv_estilo(self, cfg):
        valor = self._nv_valor_atributo('Estilo')
        texto = ' '.join(filter(None, [valor.name if valor else '', self.name or ''])).lower()
        for e in cfg.estilo_ids:
            if e.name.lower() in texto:
                return e
        return cfg.estilo_ids.filtered(lambda e: e.name == 'Otro')[:1] or cfg.estilo_ids[-1:]

    def _nv_peso(self, estilo, metal, kt):
        if self.nv_peso_g:
            return self.nv_peso_g, '(verificado)'
        m = re.match(r'^\s*(\d+(?:[.,]\d+)?)\s*(g|gr|grs|gramos)?\s*$', self.x_studio_peso_joya or '', re.I) \
            if 'x_studio_peso_joya' in self._fields else None
        if m:
            g = float(m.group(1).replace(',', '.'))
            if PESO_MIN <= g <= PESO_MAX:
                return g, '(dato del vendedor)'
        dens = getattr(metal, 'x_densidad', 0) if metal else 0
        rel = dens / DENSIDAD_14K if dens else DENS_KT.get(kt, 1.0)
        return (estilo.peso_14k or 3.0) * rel, '(estimado, %s)' % (estilo.name or 'otro').lower()

    def _nv_cotizacion(self, metal, kt):
        """Pesos por gramo de metal puro, del día."""
        if metal and hasattr(self, '_xb_cotizacion'):
            v = self._xb_cotizacion(metal)
            if v:
                return v
        divisa = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', 'XPT' if kt == 'PT' else 'XAU')], limit=1)
        return (1.0 / divisa.rate) if divisa and divisa.rate else 0.0

    def _nv_tipo_cambio(self):
        usd = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        return (1.0 / usd.rate) if usd and usd.rate else 0.0

    def _nv_laboratorio(self):
        """(nombre, estrellas) del mejor laboratorio del certificado, según la app Gemas."""
        if 'x_studio_certificados' not in self._fields:
            return '', 0
        mejor, est = '', 0
        for lab in self.x_studio_certificados:
            if lab.x_name in ('Ninguno', 'Otro'):
                continue
            try:
                e = int(getattr(lab, 'x_studio_pupularidad', 0) or 0)
            except (TypeError, ValueError):
                e = 0
            if e > est:
                mejor, est = lab.x_name, e
        return mejor, est

    def _nv_piedra(self, cfg):
        """Cómo se valúa la piedra central: con lo que dice su certificado o, si la
        pieza se examinó en el taller, con lo que se midió ahí."""
        lab_nombre, estrellas = self._nv_laboratorio()
        con_numero = bool(re.search(r'\d{6,}', self.nv_cert_number or ''))
        est = estrellas if con_numero else 0
        confianza, calidad = cfg._nv_regla(est)
        color, pureza = self._nv_calidad(calidad)
        es_lab = self._nv_es_laboratorio()
        ct = self.nv_carats or 0.0
        fisico = self.nv_av_tipo == 'fisico'
        simulante = False
        if fisico:
            if self.nv_fis_origen in ('natural', 'lab'):
                es_lab = self.nv_fis_origen == 'lab'
            simulante = self.nv_fis_origen == 'simulante'
            if self.nv_fis_color and self.nv_fis_pureza:
                color, pureza, calidad = self.nv_fis_color, self.nv_fis_pureza, 'taller'
            if not ct and self.nv_fis_ct:
                ct = self.nv_fis_ct
            # Confianza A: el origen se confirmó, la calidad se graduó aquí (o viene de un
            # laboratorio de 2-3 estrellas cuya inscripción coincide) y la pieza se pesó.
            # Si algo de eso falta, B: siempre sabemos más que con fotos.
            calidad_firme = calidad == 'taller' or (est >= 2 and self.nv_fis_laser == 'coincide')
            origen_firme = self.nv_fis_origen in ('natural', 'lab', 'simulante')
            confianza = 'A' if (origen_firme and calidad_firme and self.nv_peso_g) or (not ct and self.nv_peso_g) else 'B'
            if self.nv_fis_laser == 'no_coincide':
                confianza = 'C'
        return dict(lab=lab_nombre, estrellas=est, confianza=confianza, calidad=calidad,
                    color=color, pureza=pureza, es_lab=es_lab, ct=ct, fisico=fisico, simulante=simulante)

    def _nv_metal(self, cfg):
        """(metal, kilataje, ley, nombre) con que se valúa el metal. Si en el taller la
        prueba dio otra ley, manda la prueba y se cotiza como oro de esa ley."""
        metal = self._nv_valor_atributo('Metal')
        kt = self._nv_kilataje(metal)
        nombre = metal.name if metal else '%s (supuesto)' % kt
        if self.nv_av_tipo == 'fisico' and self.nv_fis_ley:
            if self.nv_fis_ley == 'menor':
                return False, '10K', 0.0, 'metal menor a 10K (comprobado)'
            if self.nv_fis_ley != kt:
                return False, self.nv_fis_ley, LEY_KT[self.nv_fis_ley], '%s (comprobado; se declaró %s)' % (
                    self.nv_fis_ley, metal.name if metal else 'otro')
            nombre = '%s (comprobado)' % nombre
        ley = getattr(metal, 'x_ley', 0) or LEY_KT.get(kt, LEY_KT['10K'])
        return metal, kt, ley, nombre

    def _nv_es_laboratorio(self):
        origen = (self.x_studio_origen_c or '') if 'x_studio_origen_c' in self._fields else ''
        return 'lab' in origen.lower() or 'ntétic' in origen

    def _nv_forma(self):
        forma = self.x_studio_forma.name if 'x_studio_forma' in self._fields and self.x_studio_forma else ''
        f = (forma or '').lower()
        return 'Round' if (not f or 'redond' in f or 'round' in f or 'brillante' in f) else 'Pear'

    def _nv_calidad(self, calidad):
        """Color y pureza con que se valúa la piedra, según la regla del laboratorio."""
        color = self.x_studio_color_real.x_name if 'x_studio_color_real' in self._fields and self.x_studio_color_real else None
        pureza = self.x_studio_pureza_real.x_name if 'x_studio_pureza_real' in self._fields and self.x_studio_pureza_real else None
        if calidad == 'supuesta':
            return COLOR_SUPUESTO, PUREZA_SUPUESTA
        if calidad == 'baja':
            color = COLORES[min(COLORES.index(color) + 1, len(COLORES) - 1)] if color in COLORES else None
            pureza = PUREZAS[min(PUREZAS.index(pureza) + 1, len(PUREZAS) - 1)] if pureza in PUREZAS else None
        return color or COLOR_SUPUESTO, pureza or PUREZA_SUPUESTA

    def _nv_nuevo_anello(self, cfg, estilo, metal, kt, ct, es_lab, color, pureza, tc, pasos):
        """Cuánto costaría NUEVA una pieza equivalente en Anello (con IVA), o 0 si no la vende."""
        mxn = lambda v: '$' + format(round(v or 0), ',')
        tope = cfg.anello_max_lab if es_lab else cfg.anello_max_natural
        if ct > tope:
            pasos.append('Nuevo en Anello: no vende piedras de %.2f ct (hasta %.2f).' % (ct, tope))
            return 0.0
        montadura, tmpl = self._nv_montadura_anello(cfg, estilo, metal, kt)
        if not montadura:
            pasos.append('Nuevo en Anello: no se encontró una montadura comparable.')
            return 0.0
        icp = self.env['ir.config_parameter'].sudo()
        if es_lab:
            usd_ct = float(icp.get_param('xb_gema_precio_rapaport.lab_usd_quilate', '180'))
            factor = float(icp.get_param('xb_gema_precio_rapaport.factor_lab', '3.88'))
            piedra = ct * usd_ct * factor * tc * 1.16
            detalle = '%.2f ct lab × %s USD × %.2f × IVA' % (ct, round(usd_ct), factor)
        else:
            rap, _nota = self._nv_precio_rapaport(ct, color, pureza, self._nv_forma())
            corte = 0.0
            if 'x_studio_corte' in self._fields and self.x_studio_corte:
                corte = (self.x_studio_corte.x_studio_sobretasa or 0.0) / 100.0
            cert = 0.0
            if cfg.lab_anello and 'x_laboratorios_gemolog' in self.env:
                lab = self.env['x_laboratorios_gemolog'].sudo().search([('x_name', '=', cfg.lab_anello)], limit=1)
                cert = (lab.x_studio_sobretasa or 0.0) / 100.0 if lab else 0.0
            piedra = ct * rap * (1 + corte + cert) * tc
            detalle = '%.2f ct %s / %s × Rapaport %s × (1 + corte %s %% + %s %s %%)' % (
                ct, color, pureza, format(round(rap), ','), round(corte * 100), cfg.lab_anello, round(cert * 100))
        total = montadura + piedra
        pasos.append('Nuevo en Anello: montadura %s %s + diamante %s (%s) = %s' % (
            tmpl.name, mxn(montadura), mxn(piedra), detalle, mxn(total)))
        return total

    def _nv_montadura_anello(self, cfg, estilo, metal, kt):
        """Precio con IVA de la montadura de referencia del estilo, en el mismo metal (o el
        mismo kilataje si Anello no maneja ese color), a la talla de referencia."""
        if not estilo or not cfg.pricelist_id or not hasattr(self, 'xb_pos_precio_combinacion'):
            return 0.0, None
        nombre_metal = (metal.name or '').strip().lower() if metal else ''
        candidatos = []
        for tmpl in estilo.montadura_ids:
            ptavs = tmpl.attribute_line_ids.product_template_value_ids
            for v in ptavs.filtered(lambda p: p.attribute_id.name == 'Metal'):
                n = v.name.strip().lower()
                if n == nombre_metal:
                    candidatos.insert(0, (tmpl, v))
                elif self._nv_kilataje(v) == kt:
                    candidatos.append((tmpl, v))
        for tmpl, v_metal in candidatos:
            ptavs = tmpl.attribute_line_ids.product_template_value_ids
            medida = ptavs.filtered(lambda p: p.attribute_id.name == 'Medida' and p.name == cfg.medida_ref)[:1]
            piedra = ptavs.filtered(lambda p: p.attribute_id.name == 'Piedra' and p.name == 'Diamante natural')[:1]
            combo = v_metal | medida | piedra
            res = self.env['product.template'].sudo().xb_pos_precio_combinacion(
                tmpl.id, combo.ids, cfg.pricelist_id.id)
            if res and res.get('con'):
                return res['con'], tmpl
        return 0.0, None

    def _nv_precio_rapaport(self, quilates, color=None, pureza=None, forma='Round'):
        """Precio por quilate de la tabla Rapaport, en dólares.

        El precio por quilate de un diamante crece muchísimo con el tamaño: una
        piedra de 1.80 ct vale ~9,400 usd/ct y una chispa de 0.01 vale ~680. Usar
        el precio de melee para valuar una central subvalúa la pieza catorce
        veces, que es justo lo que hace inservible un avalúo.

        La consulta se delega en `rapaport.lookup`, que es el mismo camino por
        el que se cotiza una gema del inventario: si mañana cambia la forma de
        buscar en la tabla, el avalúo y el precio de venta cambian juntos.
        Rapaport publica dos hojas: Round, y Pear para todas las demás formas.
        """
        c, p = (color or COLOR_SUPUESTO), (pureza or PUREZA_SUPUESTA)
        if 'rapaport.price.sheet' not in self.env:
            return 0.0, ''
        Sheet = self.env['rapaport.price.sheet'].sudo()
        h = Sheet.search([('shape', '=', forma),
                          ('size_from', '<=', quilates),
                          ('size_to', '>=', quilates)], order='date desc', limit=1)
        if not h:
            return 0.0, ''
        precio = 0.0
        if 'rapaport.lookup' in self.env:
            precio = self.env['rapaport.lookup'].sudo().get_price_per_carat(
                shape=forma, carat=round(quilates, 2), color=c, clarity=p) or 0.0
        if not precio:
            linea = self.env['rapaport.price.line'].sudo().search(
                [('sheet_id', '=', h.id), ('color', '=', c), ('clarity', '=', p)], limit=1)
            precio = linea.price if linea else 0.0
        return precio, '%s %s/%s' % (h.name, c, p)
