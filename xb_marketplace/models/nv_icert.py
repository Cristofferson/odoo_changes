import re
from urllib.parse import quote

from odoo import _, fields, models
from odoo.exceptions import UserError

# Detector de sintéticos → origen como lo guarda la ficha de la gema.
ORIGEN_GEMA = {'natural': 'Natural (mina)', 'lab': 'Sintético (laboratorio)'}
# Fluorescencia del examen → siglas de la app Gemas.
FLUORESCENCIA_GEMA = {'none': 'N', 'faint': 'F', 'medium': 'M', 'strong': 'S', 'very_strong': 'VS'}
# Reporte del vendedor que la ficha de la gema guarda en su propio campo.
REPORTE_LAB = {'GIA': 'x_studio_certificado_gia_c', 'IGI': 'x_studio_certificado_igi_c',
               'AGS': 'x_studio_certificado_ags_c', 'EGL': 'x_studio_certificado_egl_c',
               'HRD': 'x_studio_certificado_hrd_c'}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nv_plastico = fields.Char(
        'Plástico NFC', copy=False,
        help='Número del plástico que se le pone a la pieza al recibirla. Es lo que se '
             'escanea para abrir el visor; la joya y su gema lo comparten.')
    nv_joya_lot_id = fields.Many2one('stock.lot', 'Serie de la joya', copy=False, readonly=True)
    nv_gema_lot_id = fields.Many2one('stock.lot', 'Serie de la gema', copy=False, readonly=True)
    nv_visor_url = fields.Char('Visor', compute='_compute_nv_visor_url')

    def _compute_nv_visor_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for t in self:
            t.nv_visor_url = ('%s/stijid?id=%s' % (base, quote(t.nv_plastico, safe=''))) \
                if t.nv_plastico and t.nv_joya_lot_id else False

    def write(self, vals):
        res = super().write(vals)
        if vals.get('nv_dev_fecha'):
            for t in self.filtered('nv_joya_lot_id'):
                t._nv_evento(t.nv_joya_lot_id, 'delivered', _('Salió del taller de NOVADIAM: entregada a %s.') % (
                    t.nv_dev_persona or _('el vendedor')))
        return res

    # ------------------------------------------------------------------
    # Recepción: la pieza recibe su plástico y empieza su historia
    # ------------------------------------------------------------------
    def action_nv_recibir(self):
        """Da de alta la serie de la joya con su plástico, a nombre del vendedor.
        Desde aquí cada movimiento queda en la trazabilidad del visor."""
        Lot = self.env['stock.lot'].sudo()
        for t in self:
            plastico = (t.nv_plastico or '').strip()
            if not plastico:
                raise UserError(_('Escribe el número del plástico NFC que se le puso a la pieza.'))
            if 'x_studio_url_stij' in Lot._fields:
                otro = Lot.search([('x_studio_url_stij', '=', plastico),
                                   ('id', 'not in', (t.nv_joya_lot_id | t.nv_gema_lot_id).ids)], limit=1)
                if otro:
                    raise UserError(_('El plástico %s ya está en otra pieza (%s).') % (plastico, otro.display_name))
            variante = t.product_variant_ids[:1] or t._nv_crear_variante()
            if not variante:
                raise UserError(_('El anuncio no tiene una versión a la cual darle serie.'))
            vals = {'x_studio_url_stij': plastico}
            if t.nv_joya_lot_id:
                t.nv_joya_lot_id.write(t._nv_campos_lote(vals))
                if t.nv_gema_lot_id:
                    t.nv_gema_lot_id.write(t._nv_campos_lote(dict(vals)))
            else:
                vals.update({'name': plastico, 'product_id': variante.id,
                             'company_id': t.company_id.id or self.env.company.id,
                             'x_studio_estatus': 'Activo', 'x_studio_visor_activo': True,
                             'x_studio_informacion_general': True, 'x_studio_galeria': True})
                lote = Lot.with_context(stij_event_note=_('Recibida en el taller de NOVADIAM, folio %s.') % (
                    t.nv_rec_folio or '—')).create(t._nv_campos_lote(vals))
                if t.nv_seller_id.partner_id and 'x_studio_beneficiario' in Lot._fields:
                    # Al ponerle dueño, STIJ registra solo el evento de custodia.
                    lote.with_context(stij_event_note=_('Recibida en el taller de NOVADIAM, folio %s.') % (
                        t.nv_rec_folio or '—')).write({'x_studio_beneficiario': t.nv_seller_id.partner_id.id})
                t.nv_joya_lot_id = lote
            t.write({'nv_rec_fecha': t.nv_rec_fecha or fields.Datetime.now(),
                     'nv_rec_user_id': t.nv_rec_user_id.id or self.env.user.id})
        return True

    # ------------------------------------------------------------------
    # ICERT: la gema graduada en el taller, ligada a la joya
    # ------------------------------------------------------------------
    def action_nv_emitir_icert(self):
        for t in self:
            if t.nv_gema_lot_id:
                continue
            t._nv_validar_icert()
            gema = t._nv_crear_gema()
            t._nv_completar_joya()
            lote = t._nv_crear_lote_gema(gema)
            t.nv_joya_lot_id.sudo().write({'dmn_gem_lot_id': lote.id}
                                          if 'dmn_gem_lot_id' in t.nv_joya_lot_id._fields else {})
            nota = _('ICERT %s emitido con examen físico en el taller de NOVADIAM.') % t.nv_reporte_diamane
            for l in (t.nv_joya_lot_id, lote):
                t._nv_evento(l, 'label_printed', nota)
            t.nv_gema_lot_id = lote
            t.message_post(body=_('ICERT <b>%s</b> emitido. Gema %s ligada a la joya; el plástico %s abre el visor.') % (
                t.nv_reporte_diamane, gema.display_name, t.nv_plastico))
        return True

    def _nv_validar_icert(self):
        self.ensure_one()
        falta = []
        if self.nv_av_tipo != 'fisico':
            falta.append(_('marcar el avalúo «Con examen físico en taller»'))
        if not self.nv_joya_lot_id:
            falta.append(_('registrar la recepción con su plástico'))
        if not self.nv_reporte_diamane:
            falta.append(_('el número ICERT (campo «Reporte DIAMANE»)'))
        if self.nv_fis_origen not in ORIGEN_GEMA:
            falta.append(_('el resultado del detector (natural o laboratorio)'))
        if not (self.nv_fis_color and self.nv_fis_pureza):
            falta.append(_('el color y la pureza en taller'))
        if not (self.nv_carats or self.nv_fis_ct):
            falta.append(_('los quilates de la piedra'))
        if not self.nv_peso_g:
            falta.append(_('el peso en báscula'))
        if falta:
            raise UserError(_('Para emitir el ICERT falta:\n• %s') % '\n• '.join(falta))
        Tmpl = self.env['product.template'].sudo().with_context(active_test=False)
        if 'x_studio_certificado_dia' in Tmpl._fields:
            otra = Tmpl.search([('x_studio_certificado_dia', '=', self.nv_reporte_diamane)], limit=1)
            if otra:
                raise UserError(_('El ICERT %s ya pertenece a %s.') % (self.nv_reporte_diamane, otra.display_name))

    def _nv_por_nombre(self, modelo, nombre):
        if not nombre or modelo not in self.env:
            return False
        return self.env[modelo].sudo().search([('x_name', '=', nombre)], limit=1).id or False

    def _nv_inscripcion(self):
        """Lo que se leyó grabado en la piedra: si coincide con el reporte del
        vendedor, es el número de ese reporte."""
        if 'x_studio_laser_dia' in self._fields and self.x_studio_laser_dia:
            return self.x_studio_laser_dia
        if self.nv_fis_laser == 'coincide' and self.nv_cert_number:
            lab = self._nv_laboratorio()[0]
            return ('%s %s' % (lab, self.nv_cert_number)).strip()
        return self.nv_serial or ''

    def _nv_compania_diamane(self):
        """El ICERT lo emite el laboratorio DIAMANE: su gema lleva esa compañía."""
        return self.env['res.company'].sudo().search([('name', '=ilike', 'DIAMANE')], limit=1) or self.company_id

    def _nv_crear_gema(self):
        """La ficha de la gema con lo medido en el taller. No se vende: es la
        pieza de un tercero y solo existe para su certificado."""
        self.ensure_one()
        Tmpl = self.env['product.template'].sudo()
        categ = self.env['product.category'].sudo().search([('name', '=', 'Gema')], limit=1)
        ct = self.nv_carats or self.nv_fis_ct
        forma = self.x_studio_forma.name if 'x_studio_forma' in self._fields and self.x_studio_forma else ''
        vals = {
            'name': 'Diamante %s%.2f ct %s %s' % ((forma + ' ') if forma else '', ct, self.nv_fis_color, self.nv_fis_pureza),
            'categ_id': categ.id or self.categ_id.id,
            'is_storable': True, 'tracking': 'serial',
            'sale_ok': False, 'purchase_ok': False,
            'company_id': self._nv_compania_diamane().id,
            'x_studio_quilataje_c': ct,
            'x_studio_tipo_gema_c': self._nv_por_nombre('x_tipo_de_gema', 'Diamante'),
            'x_studio_color_real': self._nv_por_nombre('x_color', self.nv_fis_color),
            'x_studio_pureza_real': self._nv_por_nombre('x_purezas', self.nv_fis_pureza),
            'x_studio_fluorescencia_intensidad': self._nv_por_nombre(
                'x_fluorescencia_intens', FLUORESCENCIA_GEMA.get(self.nv_fis_fluorescencia)),
            'x_studio_origen_c': ORIGEN_GEMA[self.nv_fis_origen],
            'x_studio_certificado_dia': self.nv_reporte_diamane,
            'x_studio_fecha_reporte_dia': self.nv_examen_fecha or fields.Date.context_today(self),
            'x_studio_laser_dia': self._nv_inscripcion(),
        }
        # Las medidas de la gema son tres números (mínimo, máximo, profundidad);
        # la ficha arma con ellos el texto que muestra el visor.
        numeros = re.findall(r'\d+(?:[.,]\d+)?', self.nv_fis_medidas or '')
        if len(numeros) == 3:
            for i, n in enumerate(numeros, start=1):
                vals['x_studio_medida%d_c' % i] = float(n.replace(',', '.'))
        # Lo que el vendedor ya trae de su reporte y el taller no vuelve a medir.
        for campo in ('x_studio_forma', 'x_studio_talla_o_forma', 'x_studio_corte', 'x_studio_pulido',
                      'x_studio_simetria_calificacion_c'):
            if campo in self._fields and self[campo]:
                vals[campo] = self[campo].id
        labs = self.x_studio_certificados if 'x_studio_certificados' in self._fields else []
        diamane = self._nv_por_nombre('x_laboratorios_gemolog', 'DIAMANE')
        if 'x_studio_certificados' in Tmpl._fields:
            vals['x_studio_certificados'] = [(6, 0, list(set((labs.ids if labs else []) + ([diamane] if diamane else []))))]
        for lab in labs or []:
            campo = REPORTE_LAB.get(lab.x_name)
            if campo and self.nv_cert_number:
                vals[campo] = self.nv_cert_number
        if self.nv_fis_foto_4 or self.nv_fis_foto_1:
            vals['image_1920'] = self.nv_fis_foto_4 or self.nv_fis_foto_1
        gema = Tmpl.create({k: v for k, v in vals.items()
                            if k in Tmpl._fields and (isinstance(v, bool) or v not in (None, ''))})
        # El ID de gema (0446…) no se asigna a lo creado por el sistema: se pide como usuario.
        if hasattr(gema, '_xb_gema_assign'):
            usuario = self.env.user if not self.env.user._is_superuser() else self.env.ref('base.user_admin')
            gema.with_user(usuario)._xb_gema_assign()
        return gema

    def _nv_completar_joya(self):
        """Los datos de la joya que pinta el visor, ahora medidos."""
        self.ensure_one()
        Lot = self.env['stock.lot']
        metal = self._nv_valor_atributo('Metal')
        medida = self._nv_valor_atributo('Medida')
        vals = {
            'x_studio_tipo_joya': 'Anillo',
            'x_studio_kinto': self.nv_fis_quintado,
            'x_studio_peso_joya': '%.2f g' % self.nv_peso_g,
            'x_studio_medida_joya': medida.name if medida else self.nv_size,
        }
        if metal and hasattr(Lot, '_dmn_parse_metal'):
            info = Lot._dmn_parse_metal(metal.name)
            vals.update({'x_studio_metal_1': info['base'], 'x_studio_color_metal': info['color'],
                         'x_studio_kilataje_metal': info['kilataje'],
                         'x_studio_ley': ('%g' % info['ley']) if info['ley'] else ''})
        if 'x_studio_id_joya' in self._fields and not self.x_studio_id_joya:
            vals['x_studio_id_joya'] = self.env['ir.sequence'].sudo().next_by_code('dmn.stij.id_joya')
        if 'x_studio_descripcion' in self._fields and not self.x_studio_descripcion:
            vals['x_studio_descripcion'] = self.name
        self.sudo().write({k: v for k, v in vals.items() if k in self._fields and v})
        if 'x_studio_peso_exacto' in self.nv_joya_lot_id._fields:
            self.nv_joya_lot_id.sudo().x_studio_peso_exacto = self.nv_peso_g

    def _nv_crear_lote_gema(self, gema):
        """La serie de la gema comparte el plástico de la joya. Su nombre (el ID de
        gema, 0446…) ordena antes que el de la joya, así el plástico abre el visor
        ICERT completo: joya y reporte de la gema."""
        self.ensure_one()
        nombre = (gema.x_studio_id_gema if 'x_studio_id_gema' in gema._fields else '') or self.nv_reporte_diamane
        vals = {
            'name': nombre, 'product_id': gema.product_variant_id.id,
            'company_id': gema.company_id.id or self._nv_compania_diamane().id,
            'x_studio_url_stij': self.nv_plastico, 'x_studio_estatus': 'Activo',
            'x_studio_visor_activo': True, 'x_studio_informacion_general': True, 'x_studio_galeria': True,
        }
        Lot = self.env['stock.lot'].sudo()
        lote = Lot.create(self._nv_campos_lote(vals))
        if self.nv_seller_id.partner_id and 'x_studio_beneficiario' in Lot._fields:
            lote.with_context(stij_event_note=_('Gema de la pieza %s, certificada en el taller de NOVADIAM.') % (
                self.default_code or self.name)).write({'x_studio_beneficiario': self.nv_seller_id.partner_id.id})
        return lote

    def _nv_crear_variante(self):
        """Los anuncios no tienen versión: su Metal es un atributo dinámico, que
        Odoo no materializa solo. Se crea la de su combinación, sin tocar sus
        atributos (el avalúo los lee)."""
        self.ensure_one()
        self.env.flush_all()
        # Odoo pide un valor de CADA atributo (aun los que no crean versión) para
        # dar la combinación por válida; la versión solo guarda los que sí crean.
        combinacion = self.env['product.template.attribute.value'].concat(
            *[l.product_template_value_ids[:1] for l in self.attribute_line_ids])
        self.sudo()._create_product_variant(combinacion, log_warning=True)
        self.invalidate_recordset(['product_variant_id', 'product_variant_ids'])
        return self.product_variant_ids[:1]

    def _nv_campos_lote(self, vals):
        """Solo los campos que existen: los aporta STIJ, que puede no estar instalado."""
        Lot = self.env['stock.lot']
        return {k: v for k, v in vals.items() if k in Lot._fields}

    def _nv_evento(self, lote, tipo, nota):
        if 'stij.lot.event' in self.env and lote:
            self.env['stij.lot.event'].sudo()._record(
                lote, tipo, user_id=self.env.user.id, note=nota, source='backend',
                partner_id=self.nv_seller_id.partner_id.id or None)

    # ------------------------------------------------------------------
    # Venta: al liberar el pago la pieza pasa a nombre del comprador
    # ------------------------------------------------------------------
    def _nv_traspasar_al_comprador(self):
        """La venta queda firme al liberar el pago (pasó la inspección sin disputa).
        El comprador ya está identificado en la orden pagada, así que no hace falta
        el código de registro de las ventas de mostrador: se asigna directo a joya
        y gema, y su garantía corre desde hoy."""
        self.ensure_one()
        comprador = self.nv_sale_order_id.partner_id.commercial_partner_id
        Lot = self.env['stock.lot']
        lotes = (self.nv_joya_lot_id | self.nv_gema_lot_id).filtered(
            lambda l: l.x_studio_beneficiario != comprador) if 'x_studio_beneficiario' in Lot._fields else Lot
        if not comprador or not lotes:
            return
        nota = _('Comprada en NOVADIAM Marketplace, orden %(orden)s (vendía %(vendedor)s).',
                 orden=self.nv_sale_order_id.name, vendedor=self.nv_seller_id.partner_id.name or '-')
        lotes.sudo().with_context(stij_event_note=nota).write(self._nv_campos_lote({
            'x_studio_beneficiario': comprador.id,
            'dmn_claim_state': 'claimed',
            'dmn_claim_partner_id': comprador.id,
            'dmn_purchase_date': fields.Date.context_today(self),
        }))
        self.message_post(body=_('La pieza (plástico %(plastico)s) quedó a nombre de %(comprador)s.',
                                 plastico=self.nv_plastico, comprador=comprador.name))
