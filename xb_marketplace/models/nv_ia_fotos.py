import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_process

_logger = logging.getLogger(__name__)

MODELO = 'claude-opus-5-5'
LEIDA = '[Leída]'

TIPOS_FOTO = [
    ('certificado', 'Certificado del diamante'),
    ('factura', 'Factura o ticket'),
    ('kinto', 'Quintado'),
    ('bascula', 'Báscula'),
    ('detector', 'Detector de sintéticos'),
    ('laser', 'Inscripción láser'),
    ('calibrador', 'Calibrador'),
    ('pieza', 'Foto de la pieza'),
    ('otro', 'Otra'),
]
ACOMPANANTES_IA = [
    'estuche original', 'caja exterior', 'bolsa de compra', 'estuche de viaje', 'paño o accesorios',
    'garantía o tarjeta de autenticidad', 'folleto o manual', 'certificado impreso',
]
# Lo que la IA dice ver → el renglón de «Lo que acompaña» de la configuración.
ACOMPANANTE_CFG = {
    'estuche original': 'Estuche original del anillo',
    'caja exterior': 'Caja exterior o sobrecaja de la marca',
    'bolsa de compra': 'Bolsa de compra de la tienda',
    'estuche de viaje': 'Estuche o bolsita de viaje',
    'paño o accesorios': 'Paño de limpieza u otros accesorios de la marca',
    'garantía o tarjeta de autenticidad': 'Garantía o tarjeta de autenticidad de la marca',
    'folleto o manual': 'Folleto, manual de cuidados o libreta de la marca',
    'certificado impreso': 'Certificado del diamante original, impreso',
    'factura': 'Factura o ticket de compra',
}
LEYES_KINTO = {'10K': '10K', '14K': '14K', '18K': '18K', 'PT': 'PT'}

PROMPT = """Eres el asistente del taller de joyería NOVADIAM. El valuador examina un anillo y te pasa una foto (o un PDF). Lee SOLO lo que se ve con claridad; si un dato no se ve o no aplica, déjalo vacío ("" o 0). Nunca inventes ni deduzcas lo que no está escrito o visible.

Clasifica la foto en `tipo`:
- certificado: reporte de laboratorio del diamante (GIA, IGI, AGS, HRD, EGL…). Copia laboratorio, número de reporte, peso en quilates, forma, color, pureza, fluorescencia, medidas en mm tal como vienen ("6.41 - 6.44 x 3.96") y si dice que es diamante de laboratorio (lab-grown) o natural.
- factura: factura, ticket o nota de compra. Marca o joyería, fecha (AAAA-MM-DD), precio total y moneda.
- kinto: marca grabada dentro del aro (quintado). Copia el texto tal cual se lee en `quintado` ("14K", "585", "750 AN", "PT950"…) y pon la ley que indica: 10K (417), 14K (585), 18K (750), PT (platino 900/950).
- bascula: pantalla de una báscula con la pieza. Peso en gramos (si marca quilates, conviértelo: 1 ct = 0.2 g).
- detector: pantalla o luces de un detector de diamante sintético. natural (pasa / diamond / natural), lab (sintético / lab-grown / CVD / HPHT), referir (refer / further test), simulante (no es diamante / simulant / moissanite).
- laser: inscripción grabada en el filetín de la piedra vista al microscopio. Copia el texto completo.
- calibrador: calibrador o medidor junto a la piedra. Medidas en mm que se leen.
- pieza: foto general del anillo. Describe estado (A como nuevo, B uso normal, C rayones y garras gastadas, D necesita taller) y lo que acompaña a la pieza si aparece (estuche, caja, bolsa…).
- otro: nada de lo anterior.

`resumen`: una línea en español de lo que muestra la foto y lo que leíste.
`calidad_foto`: de 0 a 10, qué tan buena es para ilustrar un informe (enfoque, luz, fondo limpio, la pieza completa). Solo importa en tipo pieza.
`confianza`: alta si el texto se lee nítido; media si hay que adivinar algún carácter; baja si casi no se lee."""

ESQUEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'tipo': {'type': 'string', 'enum': [t for t, _n in TIPOS_FOTO]},
        'resumen': {'type': 'string'},
        'confianza': {'type': 'string', 'enum': ['alta', 'media', 'baja']},
        'calidad_foto': {'type': 'integer'},
        'laboratorio': {'type': 'string'},
        'numero_reporte': {'type': 'string'},
        'quilates': {'type': 'number'},
        'forma': {'type': 'string'},
        'color': {'type': 'string'},
        'pureza': {'type': 'string', 'enum': ['', 'FL', 'IF', 'VVS1', 'VVS2', 'VS1', 'VS2', 'SI1', 'SI2', 'I1', 'I2', 'I3']},
        'fluorescencia': {'type': 'string', 'enum': ['', 'none', 'faint', 'medium', 'strong', 'very_strong']},
        'origen_reporte': {'type': 'string', 'enum': ['', 'natural', 'lab']},
        'medidas_mm': {'type': 'string'},
        'marca': {'type': 'string'},
        'fecha_compra': {'type': 'string'},
        'precio_compra': {'type': 'number'},
        'moneda': {'type': 'string'},
        'quintado': {'type': 'string'},
        'ley_quintado': {'type': 'string', 'enum': ['', '10K', '14K', '18K', 'PT']},
        'peso_g': {'type': 'number'},
        'detector': {'type': 'string', 'enum': ['', 'natural', 'lab', 'referir', 'simulante']},
        'inscripcion': {'type': 'string'},
        'desgaste': {'type': 'string', 'enum': ['', 'A', 'B', 'C', 'D']},
        'acompanantes': {'type': 'array', 'items': {'type': 'string', 'enum': ACOMPANANTES_IA}},
    },
    'required': ['tipo', 'resumen', 'confianza', 'calidad_foto', 'laboratorio', 'numero_reporte', 'quilates',
                 'forma', 'color', 'pureza', 'fluorescencia', 'origen_reporte', 'medidas_mm', 'marca',
                 'fecha_compra', 'precio_compra', 'moneda', 'quintado', 'ley_quintado', 'peso_g', 'detector',
                 'inscripcion', 'desgaste', 'acompanantes'],
}


def _leer_con_claude(api_key, contenido):
    """Una foto → el JSON de ESQUEMA. Corre en un hilo: no toca el ORM."""
    import anthropic  # perezoso: el módulo carga aunque falte la librería
    client = anthropic.Anthropic(api_key=api_key, timeout=120, max_retries=2)
    resp = client.beta.messages.create(
        model=MODELO,
        max_tokens=4000,
        betas=['server-side-fallback-2026-07-01'],
        fallbacks='default',
        output_config={'format': {'type': 'json_schema', 'schema': ESQUEMA}},
        messages=[{'role': 'user', 'content': [contenido, {'type': 'text', 'text': PROMPT}]}],
    )
    if resp.stop_reason == 'refusal':
        raise UserError(_('La IA no quiso leer esta imagen.'))
    texto = next(b.text for b in resp.content if b.type == 'text')
    return json.loads(texto)


class NvAvaluoLectura(models.Model):
    _name = 'nv.avaluo.lectura'
    _description = 'Dato del avalúo leído de una foto'
    _order = 'confirmado, id'

    product_tmpl_id = fields.Many2one('product.template', required=True, ondelete='cascade', index=True)
    campo = fields.Char(required=True)
    name = fields.Char('Dato', required=True)
    valor = fields.Char('Lo que se leyó')
    foto_id = fields.Many2one('ir.attachment', 'De la foto', ondelete='set null')
    foto_tipo = fields.Selection(TIPOS_FOTO, 'Tipo de foto')
    nota = fields.Char('Ojo')
    clave = fields.Boolean('Dato clave', help='El informe no se imprime hasta confirmarlo.')
    confirmado = fields.Boolean('Confirmado')

    def action_confirmar(self):
        self.write({'confirmado': True})


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nv_ia_foto_ids = fields.Many2many(
        'ir.attachment', 'nv_ia_foto_rel', 'tmpl_id', 'attachment_id', 'Fotos para leer', copy=False,
        help='Certificado, factura, quintado, báscula, detector, inscripción láser, calibrador y fotos de la '
             'pieza. Al dar «Leer fotos», el sistema llena los campos y marca cada dato para que lo confirmes.')
    nv_lectura_ids = fields.One2many('nv.avaluo.lectura', 'product_tmpl_id', 'Datos leídos de fotos', copy=False)
    nv_lecturas_pendientes = fields.Integer('Datos por confirmar', compute='_compute_nv_lecturas_pendientes')
    nv_fotos_por_leer = fields.Integer('Fotos por leer', compute='_compute_nv_lecturas_pendientes')

    @api.depends('nv_lectura_ids.confirmado', 'nv_ia_foto_ids.description')
    def _compute_nv_lecturas_pendientes(self):
        for t in self:
            t.nv_lecturas_pendientes = len(t.nv_lectura_ids.filtered(lambda l: not l.confirmado))
            t.nv_fotos_por_leer = len(t.nv_ia_foto_ids.filtered(lambda a: not (a.description or '').startswith(LEIDA)))

    def write(self, vals):
        # Si el valuador corrige a mano un dato leído de una foto, ese dato ya es suyo.
        res = super().write(vals)
        if not self.env.context.get('nv_ia_llenando'):
            pendientes = self.nv_lectura_ids.filtered(lambda l: not l.confirmado and l.campo in vals)
            if pendientes:
                pendientes.write({'confirmado': True})
        return res

    # ------------------------------------------------------------------
    # Leer fotos
    # ------------------------------------------------------------------
    def action_nv_confirmar_lecturas(self):
        self.nv_lectura_ids.filtered(lambda l: not l.confirmado).action_confirmar()

    def _nv_api_key(self):
        icp = self.env['ir.config_parameter'].sudo()
        key = icp.get_param('xb_marketplace.anthropic_key') or icp.get_param('xb_self_order_assistant.anthropic_key')
        if not key:
            raise UserError(_('Falta la llave de Claude (parámetro xb_marketplace.anthropic_key).'))
        return key

    @api.model
    def _nv_contenido_ia(self, adjunto):
        """El bloque de imagen o PDF que se manda a Claude, en un tamaño que lee bien."""
        datos = base64.b64decode(adjunto.datas or b'')
        if adjunto.mimetype == 'application/pdf':
            return {'type': 'document', 'source': {'type': 'base64', 'media_type': 'application/pdf',
                                                   'data': base64.b64encode(datos).decode()}}
        if not (adjunto.mimetype or '').startswith('image/'):
            return None
        datos = image_process(datos, size=(1568, 1568), quality=88, output_format='JPEG')
        return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg',
                                            'data': base64.b64encode(datos).decode()}}

    def action_nv_leer_fotos(self):
        self.ensure_one()
        if self.nv_av_tipo != 'fisico':
            self.nv_av_tipo = 'fisico'
        if self.nv_cert_file and not self.nv_ia_foto_ids.filtered(lambda a: a.name == (self.nv_cert_filename or 'Certificado')):
            # El certificado que subió el vendedor también se lee.
            adj = self.env['ir.attachment'].search([
                ('res_model', '=', 'product.template'), ('res_id', '=', self.id), ('res_field', '=', 'nv_cert_file')], limit=1)
            if adj:
                copia = adj.copy({'res_field': False, 'name': self.nv_cert_filename or 'Certificado'})
                self.nv_ia_foto_ids = [(4, copia.id)]
        por_leer = self.nv_ia_foto_ids.filtered(lambda a: not (a.description or '').startswith(LEIDA))
        if not por_leer:
            raise UserError(_('No hay fotos nuevas por leer. Arrastra las fotos al recuadro «Fotos para leer».'))
        key = self._nv_api_key()
        trabajos = [(a, self._nv_contenido_ia(a)) for a in por_leer]
        trabajos = [(a, c) for a, c in trabajos if c]

        def leer(contenido):
            try:
                return _leer_con_claude(key, contenido), None
            except Exception as exc:  # una foto que falla no detiene a las demás
                _logger.exception('NV: no se pudo leer una foto')
                return None, str(exc)

        with ThreadPoolExecutor(max_workers=6) as pool:
            resultados = list(pool.map(leer, [c for _a, c in trabajos]))

        fallas = []
        leidas = []
        for (adjunto, _c), (dato, error) in zip(trabajos, resultados):
            if error:
                fallas.append(adjunto.name)
                continue
            adjunto.description = '%s %s · %s' % (LEIDA, dict(TIPOS_FOTO).get(dato['tipo']), dato.get('resumen') or '')
            leidas.append((adjunto, dato))
        # El certificado primero: la inscripción láser se coteja contra su número.
        orden = {t: i for i, (t, _n) in enumerate(TIPOS_FOTO)}
        for adjunto, dato in sorted(leidas, key=lambda x: orden.get(x[1]['tipo'], 99)):
            self.with_context(nv_ia_llenando=True)._nv_aplicar_lectura(adjunto, dato)
        self.with_context(nv_ia_llenando=True)._nv_fotos_para_informe(leidas)

        partes = [_('%s foto(s) leída(s).') % len(leidas)]
        if self.nv_lecturas_pendientes:
            partes.append(_('%s dato(s) por confirmar.') % self.nv_lecturas_pendientes)
        if fallas:
            partes.append(_('No se pudieron leer: %s.') % ', '.join(fallas))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Fotos leídas'), 'message': ' '.join(partes),
            'type': 'warning' if fallas else 'success', 'sticky': bool(fallas),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    # ------------------------------------------------------------------
    # Del JSON a los campos
    # ------------------------------------------------------------------
    def _nv_anotar(self, adjunto, dato, campo, etiqueta, valor_campo, texto, clave=True, nota=None):
        """Llena el campo y deja el renglón «leído de foto» que el valuador confirma."""
        if campo in self._fields:
            self.write({campo: valor_campo})
        if dato.get('confianza') == 'baja':
            nota = ', '.join(filter(None, [nota, _('se leyó con dificultad')]))
        self.nv_lectura_ids.filtered(lambda l: l.campo == campo and not l.confirmado).unlink()
        self.env['nv.avaluo.lectura'].create({
            'product_tmpl_id': self.id, 'campo': campo, 'name': etiqueta, 'valor': texto,
            'foto_id': adjunto.id, 'foto_tipo': dato['tipo'], 'nota': nota, 'clave': clave,
        })

    def _nv_por_nombre_ia(self, modelo, nombre):
        if not nombre or modelo not in self.env:
            return self.env['ir.model'].browse()  # vacío
        return self.env[modelo].sudo().search([('x_name', '=ilike', nombre.strip())], limit=1)

    def _nv_aplicar_lectura(self, adjunto, dato):
        tipo = dato['tipo']
        anotar = lambda *a, **k: self._nv_anotar(adjunto, dato, *a, **k)
        if tipo == 'certificado':
            lab = (dato.get('laboratorio') or '').strip()
            if lab:
                tipo_cert = {'GIA': 'gia', 'IGI': 'igi'}.get(lab.upper(), 'other')
                anotar('nv_cert_type', _('Certificado original'), tipo_cert, lab)
                lab_rec = self._nv_por_nombre_ia('x_laboratorios_gemolog', lab)
                if lab_rec and 'x_studio_certificados' in self._fields:
                    self.write({'x_studio_certificados': [(4, lab_rec.id)]})
            if dato.get('numero_reporte'):
                anotar('nv_cert_number', _('No. de certificado'), dato['numero_reporte'].strip(), dato['numero_reporte'])
            if dato.get('quilates'):
                antes = self.nv_carats
                nota = _('el vendedor declaró %.2f ct') % antes if antes and abs(antes - dato['quilates']) > 0.005 else None
                anotar('nv_carats', _('Quilates'), dato['quilates'], '%.2f ct' % dato['quilates'], nota=nota)
            color = (dato.get('color') or '').strip().upper()[:1]
            rec = self._nv_por_nombre_ia('x_color', color)
            if rec and 'x_studio_color_real' in self._fields:
                anotar('x_studio_color_real', _('Color (reporte)'), rec.id, color)
            rec = self._nv_por_nombre_ia('x_purezas', dato.get('pureza'))
            if rec and 'x_studio_pureza_real' in self._fields:
                anotar('x_studio_pureza_real', _('Pureza (reporte)'), rec.id, dato['pureza'])
            if dato.get('origen_reporte') and 'x_studio_origen_c' in self._fields:
                valor = 'Natural (mina)' if dato['origen_reporte'] == 'natural' else 'Sintético (laboratorio)'
                anotar('x_studio_origen_c', _('Origen (reporte)'), valor, valor)
            if dato.get('medidas_mm') and not self.nv_fis_medidas:
                anotar('nv_fis_medidas', _('Medidas de la piedra'), dato['medidas_mm'], dato['medidas_mm'],
                       nota=_('del reporte; mídelas para confirmar'))
                self._nv_ct_por_medidas(adjunto, dato, dato['medidas_mm'])
            if dato.get('fluorescencia') and not self.nv_fis_fluorescencia:
                anotar('nv_fis_fluorescencia', _('Fluorescencia'), dato['fluorescencia'],
                       dict(self._fields['nv_fis_fluorescencia'].selection).get(dato['fluorescencia']),
                       nota=_('del reporte; confírmala con la lámpara UV'))
            self._nv_acompanante(adjunto, dato, 'certificado impreso')
        elif tipo == 'factura':
            if dato.get('marca'):
                anotar('nv_brand', _('Marca'), dato['marca'].strip(), dato['marca'], clave=False)
            self._nv_acompanante(adjunto, dato, 'factura')
            compra = ' · '.join(filter(None, [dato.get('marca'), dato.get('fecha_compra'),
                                              dato.get('precio_compra') and '%s %s' % (format(dato['precio_compra'], ',.2f'), dato.get('moneda') or '')]))
            if compra:
                self._nv_nota_examen(_('Factura: %s') % compra)
        elif tipo == 'kinto':
            if dato.get('quintado'):
                anotar('nv_fis_quintado', _('Quintado leído'), dato['quintado'], dato['quintado'], clave=False)
            if dato.get('ley_quintado') in LEYES_KINTO:
                anotar('nv_fis_ley', _('Ley comprobada'), LEYES_KINTO[dato['ley_quintado']], dato['ley_quintado'],
                       nota=_('según el quintado; confírmala con ácido'))
        elif tipo == 'bascula' and dato.get('peso_g'):
            anotar('nv_peso_g', _('Peso en báscula'), dato['peso_g'], '%.2f g' % dato['peso_g'])
        elif tipo == 'detector' and dato.get('detector'):
            anotar('nv_fis_origen', _('Detector de sintéticos'), dato['detector'],
                   dict(self._fields['nv_fis_origen'].selection).get(dato['detector']))
        elif tipo == 'laser' and dato.get('inscripcion'):
            leido = re.sub(r'\D', '', dato['inscripcion'])
            reporte = re.sub(r'\D', '', self.nv_cert_number or '')
            if not reporte:
                self._nv_nota_examen(_('Inscripción láser: %s') % dato['inscripcion'])
            else:
                valor = 'coincide' if leido and (leido in reporte or reporte in leido) else 'no_coincide'
                anotar('nv_fis_laser', _('Inscripción láser'), valor, dato['inscripcion'],
                       nota=None if valor == 'coincide' else _('el reporte es %s') % self.nv_cert_number)
        elif tipo == 'calibrador' and dato.get('medidas_mm'):
            anotar('nv_fis_medidas', _('Medidas de la piedra'), dato['medidas_mm'], dato['medidas_mm'])
            self._nv_ct_por_medidas(adjunto, dato, dato['medidas_mm'])
        elif tipo == 'pieza':
            if dato.get('desgaste') and not self.nv_desgaste:
                anotar('nv_desgaste', _('Desgaste'), dato['desgaste'],
                       dict(self._fields['nv_desgaste'].selection).get(dato['desgaste']), clave=False)
            for a in dato.get('acompanantes') or []:
                self._nv_acompanante(adjunto, dato, a)

    def _nv_ct_por_medidas(self, adjunto, dato, medidas):
        """Peso estimado de una piedra redonda: diámetro promedio² × profundidad × 0.0061."""
        nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', medidas.replace(',', '.'))]
        if len(nums) == 3 and self._nv_forma() == 'Round':
            ct = round(((nums[0] + nums[1]) / 2) ** 2 * nums[2] * 0.0061, 2)
            if 0.05 <= ct <= 10:
                self._nv_anotar(adjunto, dato, 'nv_fis_ct', _('Peso estimado por medidas'), ct, '%.2f ct' % ct,
                                clave=False, nota=_('calculado de las medidas'))

    def _nv_acompanante(self, adjunto, dato, clave_ia):
        cfg = self.env['nv.avaluo.config']._nv_get()
        nombre = ACOMPANANTE_CFG.get(clave_ia)
        rec = cfg.acompanante_ids.filtered(lambda a: a.name == nombre)[:1]
        if rec and rec not in self.nv_acompanante_ids:
            self.write({'nv_acompanante_ids': [(4, rec.id)]})
            self.env['nv.avaluo.lectura'].create({
                'product_tmpl_id': self.id, 'campo': 'nv_acompanante_ids', 'name': _('Lo que acompaña'),
                'valor': rec.name, 'foto_id': adjunto.id, 'foto_tipo': dato['tipo'], 'clave': False,
            })

    def _nv_nota_examen(self, texto):
        actual = self.nv_fis_observaciones or ''
        if texto not in actual:
            self.nv_fis_observaciones = (actual + '\n' + texto).strip()

    def _nv_fotos_para_informe(self, leidas):
        """Las mejores fotos de la pieza pasan a las 4 del informe (solo a los lugares vacíos)."""
        libres = [f for f in ('nv_fis_foto_1', 'nv_fis_foto_2', 'nv_fis_foto_3', 'nv_fis_foto_4') if not self[f]]
        piezas = sorted((x for x in leidas if x[1]['tipo'] == 'pieza' and x[0].mimetype.startswith('image/')),
                        key=lambda x: -(x[1].get('calidad_foto') or 0))
        for campo, (adjunto, _d) in zip(libres, piezas):
            self[campo] = adjunto.datas

    def _nv_reporte(self):
        claves = self.nv_lectura_ids.filtered(lambda l: l.clave and not l.confirmado)
        if claves:
            raise UserError(_('Antes de imprimir confirma los datos leídos de fotos:\n%s') % '\n'.join(
                '• %s: %s' % (l.name, l.valor) for l in claves))
        return super()._nv_reporte()
