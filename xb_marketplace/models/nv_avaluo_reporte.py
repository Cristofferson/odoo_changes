import re
from datetime import timedelta

from odoo import fields, models

from .nv_avaluo_config import CALIDAD_TEXTO


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _nv_campo(self, nombre, decimales=2):
        """El valor de un campo como texto para el informe, o '' si el campo no existe
        o está vacío. Los campos de gema los aporta Studio (ICERT): no todas las
        bases los tienen, y el informe no debe tronar por eso."""
        self.ensure_one()
        if nombre not in self._fields:
            return ''
        campo, valor = self._fields[nombre], self[nombre]
        if not valor:
            return ''
        if campo.type == 'many2one':
            return getattr(valor, 'x_name', False) or valor.display_name or ''
        if campo.type == 'many2many':
            return ', '.join(getattr(v, 'x_name', False) or v.display_name for v in valor)
        if campo.type == 'selection':
            return dict(campo._description_selection(self.env)).get(valor, valor)
        if campo.type == 'float':
            return ('%.' + str(decimales) + 'f') % valor
        if campo.type == 'date':
            return valor.strftime('%d-%m-%Y')
        texto = str(valor).strip()
        # Studio deja restos como « - x» cuando las medidas están vacías.
        return texto if re.search(r'[0-9A-Za-zÁÉÍÓÚáéíóúñÑ]{2,}|\d', texto) else ''

    def _nv_fecha_hora(self, valor):
        return fields.Datetime.context_timestamp(self, valor).strftime('%d-%m-%Y %H:%M') if valor else ''

    def _nv_sel(self, nombre):
        """La etiqueta de un campo de selección propio, o ''."""
        return dict(self._fields[nombre]._description_selection(self.env)).get(self[nombre], '') if self[nombre] else ''

    def _nv_pruebas(self, cfg, peso_txt):
        """Las pruebas del examen físico: qué se midió, con qué equipo y qué dio."""
        s = self._nv_sel
        filas = [
            ('bascula', 'Peso de la pieza', peso_txt if self.nv_peso_g else ''),
            ('acido', 'Ley del metal', ' · '.join(filter(None, [
                s('nv_fis_ley'), self.nv_fis_quintado and 'quintado «%s»' % self.nv_fis_quintado]))),
            ('detector', 'Natural o de laboratorio', s('nv_fis_origen')),
            ('patron', 'Color', self.nv_fis_color or ''),
            ('lupa', 'Pureza e inscripción', ' · '.join(filter(None, [
                self.nv_fis_pureza, s('nv_fis_laser') and 'inscripción: %s' % s('nv_fis_laser').lower()]))),
            ('uv', 'Fluorescencia', s('nv_fis_fluorescencia')),
            ('calibrador', 'Medidas de la piedra', ' · '.join(filter(None, [
                self.nv_fis_medidas and '%s mm' % self.nv_fis_medidas,
                self.nv_fis_ct and '%.2f ct estimados por medidas' % self.nv_fis_ct]))),
        ]
        pruebas = []
        for tipo, que, resultado in filas:
            equipo = cfg._nv_equipo(tipo)
            if not equipo and not resultado:
                continue
            nombre = equipo.name if equipo else 'Sin equipo registrado'
            if equipo and equipo.detalle:
                nombre += ' (%s)' % equipo.detalle
            if equipo and equipo.calibracion:
                nombre += ', revisado el %s' % equipo.calibracion.strftime('%d-%m-%Y')
            pruebas.append((que, nombre, resultado or 'No realizada'))
        return pruebas

    def _nv_dinero(self, valor):
        return '$' + format(round(valor or 0, 2), ',.2f')

    def _nv_reporte(self):
        """Todo lo que lleva el informe de avalúo, ya en texto."""
        self.ensure_one()
        cfg = self.env['nv.avaluo.config']._nv_get()
        hoy = fields.Date.context_today(self)
        c = self._nv_campo
        d = self._nv_valuar()
        examen = self.nv_av_tipo == 'fisico'

        metal_decl = self._nv_valor_atributo('Metal')
        medida = self._nv_valor_atributo('Medida')
        estilo = self._nv_estilo(cfg)
        metal, kt, ley, nombre_metal = self._nv_metal(cfg)
        peso, origen_peso = self._nv_peso(estilo, metal, kt)
        p = self._nv_piedra(cfg)
        lab_nombre, estrellas, calidad = p['lab'], p['estrellas'], p['calidad']
        color, pureza, es_lab = p['color'], p['pureza'], p['es_lab']
        marca = cfg._nv_marca(self.nv_brand)
        desgastes = dict(self._fields['nv_desgaste']._description_selection(self.env))

        probado = examen and self.nv_fis_ley
        peso_txt = '%.2f g %s' % (peso, origen_peso)
        if self.nv_peso_g:
            peso_txt = '%.2f g en báscula' % self.nv_peso_g
        pieza = [
            ('Tipo de pieza', 'Anillo, %s' % (estilo.name.lower() if estilo else 'otro')),
            ('Marca', self.nv_brand or 'Sin marca declarada'),
            ('Metal', nombre_metal if examen else (metal_decl.name if metal_decl else 'No declarado')),
            ('Ley', ('%.3f · %s' % (ley, kt)) if ley else kt),
            ('Prueba del metal', 'Ácidos y piedra de toque en taller' if probado else (
                'Probado en taller' if self.nv_metal_probado else 'No probado: ley declarada')),
            ('Quintado (registro de calidad)', (examen and self.nv_fis_quintado) or c('x_studio_kinto') or 'No verificado'),
            ('Peso total', peso_txt),
            ('Talla', (medida.name if medida else self.nv_size) or 'No declarada'),
            ('Estado', desgastes.get(self.nv_desgaste) or ('%s (supuesto)' % desgastes.get(cfg.desgaste_supuesto, ''))),
            ('Lo que acompaña', ', '.join(self.nv_acompanante_ids.mapped('name')) or 'Nada declarado'),
        ]
        if examen and self.nv_fis_observaciones:
            pieza.append(('Observaciones del examen', self.nv_fis_observaciones))
        cert_num = self.nv_cert_number or c('x_studio_certificado_dia')
        diamante = []
        if p['ct']:
            # Con examen: lo medido en taller, y al lado lo que dice el reporte.
            def taller(valor, del_reporte, vacio):
                if examen and valor:
                    return '%s en taller%s' % (valor, (' · reporte: %s' % del_reporte) if del_reporte else '')
                return del_reporte or vacio
            if examen and self.nv_fis_origen:
                ident = '%s · detector de sintéticos' % self._nv_sel('nv_fis_origen')
            else:
                ident = 'Diamante de laboratorio' if es_lab else 'Diamante natural (declarado)'
            if examen and self.nv_fis_desmontada:
                peso_ct = '%.2f ct · pesado desmontado' % p['ct']
            elif self.nv_carats:
                peso_ct = '%.2f ct · %s%s' % (self.nv_carats, 'del reporte' if lab_nombre else 'declarado',
                                             ('; %.2f ct estimados por medidas' % self.nv_fis_ct) if examen and self.nv_fis_ct
                                             else '; estimado mientras esté montado')
            else:
                peso_ct = '%.2f ct · estimado por medidas' % p['ct']
            diamante = [
                ('Identificación', ident),
                ('Forma y talla', c('x_studio_forma') or c('x_studio_talla_o_forma') or 'Redonda brillante (supuesta)'),
                ('Peso', peso_ct),
                ('Medidas', (examen and self.nv_fis_medidas and '%s mm (calibrador)' % self.nv_fis_medidas)
                 or c('x_studio_medidas_totales') or 'No medidas'),
                ('Color', taller(self.nv_fis_color, c('x_studio_color_real'), 'No declarado')),
                ('Pureza', taller(self.nv_fis_pureza, c('x_studio_pureza_real'), 'No declarada')),
                ('Corte', c('x_studio_corte') or 'No declarado'),
                ('Pulido / simetría', ' / '.join(filter(None, [c('x_studio_pulido'), c('x_studio_simetria_calificacion_c')])) or 'No declarados'),
                ('Fluorescencia', taller(self._nv_sel('nv_fis_fluorescencia'), c('x_studio_fluorescencia_intensidad'), 'No declarada')),
                ('Tratamientos', c('x_studio_tratamientos') or 'No detectados ni declarados'),
                ('Reporte de laboratorio', ('%s %s · %s' % (lab_nombre, '★' * estrellas, cert_num or 'sin número')) if lab_nombre
                 else (cert_num and 'Número %s, laboratorio no reconocido' % cert_num or 'Sin reporte')),
                ('Reporte verificado en línea', 'Sí' if self.nv_cert_verificado else 'No'),
                ('Inscripción láser', ' · '.join(filter(None, [
                    c('x_studio_laser_dia'), examen and self._nv_sel('nv_fis_laser')])) or 'No revisada'),
                ('Calidad con que se valúa', '%s / %s · %s' % (color, pureza, CALIDAD_TEXTO.get(calidad, ''))),
            ]
            if self.nv_reporte_diamane and self.nv_gema_lot_id:
                diamante.insert(-1, ('Certificado ICERT', '%s · laboratorio DIAMANE' % self.nv_reporte_diamane))
        acentos = []
        if 'dmn_accent_ids' in self._fields and self.dmn_accent_ids:
            for l in self.dmn_accent_ids:
                acentos.append(('%s piedras' % l.qty, '%.3f ct en total (estimado)' % (l.carats_total or 0)))

        # Supuestos extraordinarios: lo que se dio por cierto sin comprobarlo.
        supuestos = []
        if not examen:
            supuestos.append('La información, fotografías y documentos del vendedor son verdaderos y corresponden a esta pieza.')
        if p['ct'] and not es_lab and calidad in ('baja', 'supuesta'):
            supuestos.append('Sin reporte de un laboratorio de confianza, se supone una calidad de %s / %s para el diamante.' % (color, pureza))
        if p['ct'] and not es_lab and not (examen and self.nv_fis_origen in ('natural', 'lab')):
            supuestos.append('El diamante es natural, como lo declara el vendedor; %s' % (
                'el detector lo refirió a laboratorio y el origen no está confirmado.' if examen and self.nv_fis_origen == 'referir'
                else 'con fotografías no se puede distinguir de uno de laboratorio.'))
        if cert_num and not self.nv_cert_verificado and not (examen and self.nv_fis_laser == 'coincide'):
            supuestos.append('El reporte de laboratorio %s corresponde a esta piedra; aún no se ha cotejado su inscripción ni sus medidas.' % cert_num)
        if examen and self.nv_fis_laser == 'no_coincide':
            supuestos.append('La inscripción láser NO coincide con el reporte %s: no se toma como reporte de esta piedra.' % (cert_num or ''))
        if examen and p['ct'] and not self.nv_fis_desmontada:
            supuestos.append('La piedra no se desmontó: su peso es el %s.' % (
                'del reporte' if self.nv_carats and lab_nombre else 'declarado o estimado por medidas'))
        if 'estimado' in origen_peso:
            supuestos.append('El peso del metal es el típico de un anillo %s; no se ha pesado la pieza.' % (estilo.name.lower() if estilo else ''))
        if not self.nv_metal_probado and not probado:
            supuestos.append('La ley del metal es la declarada (%s); no se ha probado.' % nombre_metal)
        if not self.nv_desgaste:
            supuestos.append('El estado de la pieza es «%s», sin fotografía del interior del aro ni de las garras.' % desgastes.get(cfg.desgaste_supuesto, ''))

        tc = self._nv_tipo_cambio()
        hoja = self.env['rapaport.price.sheet'].sudo().search([], order='date desc', limit=1) \
            if 'rapaport.price.sheet' in self.env else False
        metodo = [
            ('Enfoques', 'Costo (valor intrínseco de los materiales a precio de reventa) y comparación de mercado '
                         '(piezas usadas parecidas y precio de una pieza equivalente nueva). No se usó el enfoque '
                         'de ingresos: la pieza no genera rentas.'),
            ('Mercado', 'Mercado secundario de joyería usada en México, entre particulares, a través de NOVADIAM.'),
            ('Metal', 'Peso × ley × cotización del %s: %s por gramo de metal fino, más %s %% por estar armado.' % (
                hoy.strftime('%d-%m-%Y'), self._nv_dinero(self._nv_cotizacion(metal, kt)), round(cfg.montadura_pct - 100))),
            ('Diamante natural', 'Lista Rapaport%s por forma, tamaño, color y pureza, al porcentaje que paga un comprador '
                                 'de segunda mano. Rapaport se usa como referencia, no como única fuente.' % (
                                     (' del %s' % hoja.date.strftime('%d-%m-%Y')) if hoja and hoja.date else '')),
            ('Diamante de laboratorio', 'Valor de reventa en dólares por quilate según tamaño.'),
            ('Tipo de cambio', '%.4f pesos por dólar.' % tc),
            ('Pieza nueva equivalente', 'La más barata entre Anello (lista vigente, talla %s) y el mercado.' % cfg.medida_ref),
        ]
        nuevo = min([v for v in (d['nv_av_nuevo_anello'], self.nv_mercado_nuevo) if v] or [0])
        resultados = [
            ('Valor intrínseco', '%s – %s' % (self._nv_dinero(d['nv_av_piso']), self._nv_dinero(d['nv_av_piso_max']))),
            ('Mercado de piezas usadas', ('%s – %s' % (self._nv_dinero(d['nv_av_sugerido_min']), self._nv_dinero(d['nv_av_sugerido_max'])))
             if d['nv_av_sugerido_max'] else 'Sin comparables suficientes'),
            ('Pieza equivalente nueva', self._nv_dinero(nuevo) if nuevo else 'Sin pieza comparable'),
        ]
        techo = d['nv_av_techo'] or 10 ** 12
        if d['nv_av_sugerido_max']:
            lo, hi = max(d['nv_av_piso'], d['nv_av_sugerido_min']), max(d['nv_av_piso_max'], d['nv_av_sugerido_max'])
        else:
            lo, hi = d['nv_av_piso'], d['nv_av_piso_max']
        lo, hi = min(lo, techo), min(hi, techo)
        desglose = [('Metal fino', d['nv_av_oro']), ('Hechura', d['nv_av_hechura']),
                    ('Diamante central', d['nv_av_diamante']), ('Piedras de acento', d['nv_av_acentos'])]
        factores = 'Marca %s × %.2f · estado × %s %% · lo que acompaña +%s %%' % (
            marca.name if marca else (self.nv_brand or 'sin marca'), marca.factor if marca else 1.0,
            round(cfg._nv_desgaste(self.nv_desgaste)),
            round(min(sum(self.nv_acompanante_ids.mapped('pct')), cfg.acompanante_tope), 2))

        fotos_taller = [f for f in (self.nv_fis_foto_1, self.nv_fis_foto_2, self.nv_fis_foto_3, self.nv_fis_foto_4) if f] \
            if examen else []
        # Con examen van las fotos del taller; si no se tomaron, las del vendedor.
        fotos = list(fotos_taller)
        if not fotos:
            if self.image_1920:
                fotos.append(self.image_1024)
            if 'product_template_image_ids' in self._fields:
                fotos += [i.image_1024 for i in self.product_template_image_ids if i.image_1920]
        website = self.env['website'].sudo().search([('nv_is_marketplace', '=', True)], limit=1)

        recepcion = []
        if examen:
            recepcion = [x for x in [
                ('Folio de recepción', self.nv_rec_folio),
                ('Recibida', ' · '.join(filter(None, [self._nv_fecha_hora(self.nv_rec_fecha), self.nv_rec_user_id.name]))),
                ('Estado al recibirla', self.nv_rec_estado),
                ('Examinó', ' · '.join(filter(None, [self.nv_examen_user_id.name,
                                                    self.nv_examen_fecha and self.nv_examen_fecha.strftime('%d-%m-%Y')]))),
                ('Devuelta o entregada', ' · '.join(filter(None, [self._nv_fecha_hora(self.nv_dev_fecha), self.nv_dev_persona]))
                 or 'Bajo resguardo de NOVADIAM'),
            ] if x[1]]
        equipo_usado = ', '.join(e.name.lower() for e in cfg.equipo_ids.filtered(lambda e: e.tipo != 'otro'))

        return {
            'folio': 'AV-%s-%s' % ((self.default_code or str(self.id)).replace(' ', ''), hoy.strftime('%Y%m%d')),
            'fecha': hoy.strftime('%d-%m-%Y'),
            'vigencia': (hoy + timedelta(days=cfg.vigencia_dias)).strftime('%d-%m-%Y'),
            'examen': self.nv_examen_fecha.strftime('%d-%m-%Y') if self.nv_examen_fecha else (
                'En taller' if examen else 'Sin examen físico'),
            'examen_fisico': examen,
            'titulo': 'Avalúo con examen físico · uso comercial' if examen else 'Estimación de valor de reventa · uso comercial',
            'icert': self.nv_reporte_diamane if self.nv_gema_lot_id else '',
            'plastico': self.nv_plastico if self.nv_joya_lot_id else '',
            'visor_url': self.nv_visor_url or '',
            'pruebas': self._nv_pruebas(cfg, peso_txt) if examen else [],
            'recepcion': recepcion,
            'fotos_taller': bool(fotos_taller),
            'proposito': cfg.reporte_proposito,
            'tipo_valor': cfg.reporte_tipo_valor,
            'alcance': (('Examen físico de la pieza en el taller de NOVADIAM (%s), más los documentos del vendedor. '
                         'Sin análisis de metal por rayos X.' % equipo_usado) if examen else
                        'Documental a distancia: fotografías, documentos y declaraciones del vendedor. La pieza no se ha '
                        'examinado en mano, el metal no se ha probado y el diamante no se ha medido ni graduado.'),
            'derecho': 'Propiedad plena de la pieza, libre de gravámenes (según declara el vendedor).',
            'solicitante': self.nv_seller_id.name or 'Vendedor del marketplace',
            'usuarios': 'El vendedor y los compradores de la publicación en NOVADIAM.',
            'confianza': d['nv_av_confianza'],
            'pieza': pieza, 'diamante': diamante, 'acentos': acentos, 'supuestos': supuestos,
            'metodo': metodo, 'resultados': resultados,
            'conclusion': '%s – %s' % (self._nv_dinero(lo), self._nv_dinero(hi)),
            'techo': self._nv_dinero(d['nv_av_techo']) if d['nv_av_techo'] else 'Por definir',
            'techo_pct': round(cfg.techo_pct),
            'desglose': [(n, self._nv_dinero(v)) for n, v in desglose if v],
            'intrinseco': self._nv_dinero(d['nv_avaluo']),
            'factores': factores,
            'pasos': [p for p in (d['nv_avaluo_detalle'] or '').split('\n') if p],
            'fotos': fotos[:6],
            'logo': website.logo if website else False,
            'marca_web': website.name if website else 'NOVADIAM',
            'condiciones': cfg.reporte_condiciones_fisico if examen else cfg.reporte_condiciones,
            'valuador': cfg.valuador_nombre or self.env.user.name,
            'valuador_cargo': cfg.valuador_cargo,
            'firma': cfg.valuador_firma,
        }
