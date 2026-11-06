"""Todas las piedras de un anillo para el avalúo: la central (diamante, piedra de
color o ninguna) y los grupos de piedras laterales y acentos.

Los grupos viven en `dmn.accent.line` (stij_diamane_plus), el mismo renglón que
usan la ficha de la gema y el visor: aquí solo se les agrega lo que el avalúo
necesita (posición, gema, color y pureza) y su valor.
"""
import re

from odoo import api, fields, models

from odoo.addons.stij_diamane_plus.models.dmn_accent_line import TABLA_MM_CT, quilates_de_mm

from .nv_avaluo import COLORES, PUREZAS, COLOR_SUPUESTO, PUREZA_SUPUESTA

# Formas de talla. Las redondas se miden por su diámetro; las demás, por largo y ancho.
FORMAS = [('redondo', 'Redonda'), ('princesa', 'Princesa'), ('baguette', 'Baguette'), ('oval', 'Oval'),
          ('pera', 'Pera'), ('marquesa', 'Marquesa'), ('esmeralda', 'Esmeralda'), ('cojin', 'Cojín'),
          ('corazon', 'Corazón'), ('radiante', 'Radiante'), ('asscher', 'Asscher'), ('trillon', 'Trillón'),
          ('otra', 'Otra')]
# Fórmulas del oficio para estimar el peso de un diamante con sus medidas:
# quilates = largo × ancho × alto × factor (en la redonda, diámetro promedio² × alto × 0.0061).
FACTOR_FORMA = {'redondo': 0.0061, 'oval': 0.0062, 'pera': 0.0059, 'marquesa': 0.0058, 'corazon': 0.0059,
                'esmeralda': 0.0080, 'asscher': 0.0080, 'princesa': 0.0083, 'cojin': 0.0081, 'radiante': 0.0081,
                'baguette': 0.00915, 'trillon': 0.0057, 'otra': 0.0062}
# Montada, el alto de una piedra chica no se puede medir: se supone el típico de su forma (alto / ancho).
ALTO_TIPICO = {'princesa': 0.75, 'baguette': 0.65, 'oval': 0.60, 'pera': 0.60, 'marquesa': 0.60,
               'esmeralda': 0.65, 'cojin': 0.65, 'corazon': 0.60, 'radiante': 0.65, 'asscher': 0.65,
               'trillon': 0.45, 'otra': 0.60}
# Cómo se escribe la forma en los reportes de laboratorio (GIA, IGI…) → la forma de aquí.
FORMA_DE_TEXTO = [('round', 'redondo'), ('redond', 'redondo'), ('brillante', 'redondo'), ('princess', 'princesa'),
                  ('princesa', 'princesa'), ('baguet', 'baguette'), ('oval', 'oval'), ('pear', 'pera'),
                  ('pera', 'pera'), ('marquise', 'marquesa'), ('marques', 'marquesa'), ('emerald', 'esmeralda'),
                  ('esmeralda', 'esmeralda'), ('cushion', 'cojin'), ('coj', 'cojin'), ('heart', 'corazon'),
                  ('coraz', 'corazon'), ('radiant', 'radiante'), ('asscher', 'asscher'), ('trilli', 'trillon'),
                  ('triang', 'trillon')]


def forma_de_texto(texto):
    t = (texto or '').lower()
    for clave, forma in FORMA_DE_TEXTO:
        if clave in t:
            return forma
    return 'otra' if t.strip() else False


def ct_por_medidas(forma, medidas):
    """Quilates estimados con las tres medidas de la piedra suelta o de la central montada.

    Redonda: «mínimo – máximo × alto». Las demás: «largo × ancho × alto». Devuelve 0 si
    no hay tres números."""
    nums = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', (medidas or '').replace(',', '.'))]
    if len(nums) != 3 or not all(nums):
        return 0.0
    forma = forma or 'redondo'
    if forma == 'redondo':
        return round(((nums[0] + nums[1]) / 2) ** 2 * nums[2] * FACTOR_FORMA['redondo'], 2)
    return round(nums[0] * nums[1] * nums[2] * FACTOR_FORMA.get(forma, FACTOR_FORMA['otra']), 2)


def ct_acento(forma, largo, ancho):
    """Quilates de UNA piedra montada. Redonda: con la tabla de diámetros del oficio.
    Otra forma: largo × ancho × alto típico × factor."""
    if not forma or forma == 'redondo':
        return quilates_de_mm(largo)
    if not (largo and ancho):
        return 0.0
    alto = ancho * ALTO_TIPICO.get(forma, ALTO_TIPICO['otra'])
    return round(largo * ancho * alto * FACTOR_FORMA.get(forma, FACTOR_FORMA['otra']), 4)


GEMAS = [('zafiro', 'Zafiro'), ('rubi', 'Rubí'), ('esmeralda', 'Esmeralda'), ('otra', 'Otra piedra de color')]
CENTROS = [('diamante', 'Diamante'), ('gema', 'Piedra de color'), ('sin', 'No lleva piedra central')]
POSICIONES = [('central', 'Central adicional'), ('lateral', 'Laterales'), ('halo', 'Halo'),
              ('aro', 'En el aro (pavé, canal)'), ('otra', 'Otra')]


def mm_de_quilates(ct):
    """Diámetro aproximado de un brillante redondo de esos quilates (inverso de la tabla)."""
    if not ct or ct <= 0:
        return 0.0
    if ct >= TABLA_MM_CT[-1][1]:
        return round(6.5 * ct ** (1 / 3.0), 2)
    for (m1, c1), (m2, c2) in zip(TABLA_MM_CT, TABLA_MM_CT[1:]):
        if c1 <= ct <= c2:
            t = (ct - c1) / (c2 - c1) if c2 != c1 else 0
            return round(m1 + t * (m2 - m1), 2)
    return TABLA_MM_CT[0][0]


class DmnAccentLine(models.Model):
    _inherit = 'dmn.accent.line'

    nv_posicion = fields.Selection(POSICIONES, 'Dónde van')
    nv_forma = fields.Selection(FORMAS, 'Forma', default='redondo',
                                help='Redonda: escribe su diámetro. Otra forma: su largo y su ancho.')
    nv_ancho_mm = fields.Float('Ancho (mm)', digits=(6, 2),
                               help='Solo para las que no son redondas. El largo va en la columna de medida.')
    nv_gema = fields.Selection(GEMAS, 'Piedra de color', help='Solo si el tipo es «Otra piedra».')
    nv_color = fields.Selection([(c, c) for c in COLORES], 'Color',
                                help='Para laterales con certificado. Vacío = el supuesto (%s).' % COLOR_SUPUESTO)
    nv_pureza = fields.Selection([(p, p) for p in PUREZAS], 'Pureza',
                                 help='Para laterales con certificado. Vacío = la supuesta (%s).' % PUREZA_SUPUESTA)
    nv_ia = fields.Boolean('Contadas por IA', help='Las propuso «Leer fotos». Revisa cantidad, tamaño y tipo.')
    currency_id = fields.Many2one(related='product_tmpl_id.currency_id')
    nv_valor = fields.Monetary('Valor', compute='_compute_nv_valor', currency_field='currency_id')
    nv_valor_nota = fields.Char('Cómo', compute='_compute_nv_valor')

    @api.depends('size_mm', 'nv_forma', 'nv_ancho_mm')
    def _compute_carats_each(self):
        # Reemplaza el de stij_diamane_plus, que solo sabe de piedras redondas.
        for l in self:
            l.carats_each = ct_acento(l.nv_forma, l.size_mm, l.nv_ancho_mm)

    @api.depends('qty', 'size_mm', 'carats_each', 'stone_type', 'nv_gema', 'nv_color', 'nv_pureza', 'nv_forma')
    def _compute_nv_valor(self):
        cfg = self.env['nv.avaluo.config']._nv_get() if self else None
        tc = None
        for l in self:
            tmpl = l.product_tmpl_id
            if not tmpl:
                l.nv_valor, l.nv_valor_nota = 0.0, ''
                continue
            if tc is None:
                tc = tmpl._nv_tipo_cambio()
            l.nv_valor, l.nv_valor_nota, _sup = tmpl._nv_valor_grupo(cfg, l, tc)

    def _nv_forma_rapaport(self):
        """Rapaport publica una lista para redondas y otra para todas las demás formas."""
        return 'Pear' if self.nv_forma and self.nv_forma != 'redondo' else 'Round'

    def _nv_texto_avaluo(self):
        """«14 de 1.50 mm · halo · diamante natural G/VS2»."""
        self.ensure_one()
        tipo = dict(self._fields['stone_type'].selection).get(self.stone_type, '').lower()
        if self.stone_type == 'otra' and self.nv_gema:
            tipo = dict(GEMAS)[self.nv_gema].lower()
        elif self.stone_type in ('diamante_nat', 'diamante_lab') and (self.nv_color or self.nv_pureza):
            tipo += ' %s/%s' % (self.nv_color or '?', self.nv_pureza or '?')
        if self.nv_forma and self.nv_forma != 'redondo':
            medida = ('%.2f × %.2f mm' % (self.size_mm, self.nv_ancho_mm)) if self.size_mm and self.nv_ancho_mm \
                else 'tamaño sin medir'
            partes = ['%s %s de %s' % (self.qty, dict(FORMAS)[self.nv_forma].lower(), medida)]
        else:
            partes = ['%s de %s' % (self.qty, ('%.2f mm' % self.size_mm) if self.size_mm else 'tamaño sin medir')]
        if self.nv_posicion:
            partes.append(dict(POSICIONES)[self.nv_posicion].lower())
        partes.append(tipo)
        return ' · '.join(filter(None, partes))


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    nv_centro = fields.Selection(
        CENTROS, 'Tipo de piedra central', default='diamante',
        help='Diamante: se valúa con sus quilates, color y pureza. Piedra de color: con el '
             'precio por quilate de la configuración. Sin piedra central: churumbela, '
             'eternidad o argolla; se valúan solo el metal y las piedras de la tabla.')
    nv_centro_gema = fields.Selection(GEMAS, 'Cuál piedra de color')
    nv_fis_forma = fields.Selection(
        FORMAS, 'Forma en taller', copy=False,
        help='La forma de la piedra central vista en el taller. Con ella se calculan los quilates '
             'por medidas y se elige la lista Rapaport (redonda o de las demás formas).')
    nv_fis_ct = fields.Float(
        compute='_compute_nv_fis_ct', store=True, readonly=False,
        help='Se calcula solo con la forma y las tres medidas; puedes corregirlo a mano.')

    @api.depends('nv_fis_medidas', 'nv_fis_forma')
    def _compute_nv_fis_ct(self):
        for t in self:
            ct = ct_por_medidas(t.nv_fis_forma or 'redondo', t.nv_fis_medidas)
            # Sin tres medidas no se toca: queda lo que se haya escrito a mano.
            t.nv_fis_ct = ct if 0.01 <= ct <= 30 else t.nv_fis_ct

    def _nv_forma(self):
        if self.nv_av_tipo == 'fisico' and self.nv_fis_forma:
            return 'Round' if self.nv_fis_forma == 'redondo' else 'Pear'
        return super()._nv_forma()

    def _nv_forma_texto(self):
        """La forma de la central para mostrar: la del taller, o la del anuncio."""
        if self.nv_av_tipo == 'fisico' and self.nv_fis_forma:
            return dict(FORMAS)[self.nv_fis_forma]
        return self.x_studio_forma.name if 'x_studio_forma' in self._fields and self.x_studio_forma else ''

    def _nv_usd_gema(self, cfg, gema):
        return {'zafiro': cfg.gema_zafiro_usd, 'rubi': cfg.gema_rubi_usd,
                'esmeralda': cfg.gema_esmeralda_usd}.get(gema, cfg.gema_otra_usd)

    def _nv_valor_grupo(self, cfg, l, tc):
        """(valor MXN, cómo se calculó, tamaño supuesto) de un grupo de piedras.

        Cada grupo se valúa con SU tipo, no con el de la central: una zirconia no
        suma, y un lateral de 0.30 ct no vale lo mismo por quilate que una chispa.
        """
        supuesto = not l.carats_each
        ct_c = l.carats_each or quilates_de_mm(cfg.acento_mm_supuesto)
        ct = ct_c * (l.qty or 0)
        txt_sup = ' (tamaño supuesto %.2f mm)' % cfg.acento_mm_supuesto if supuesto else ''
        if not l.qty:
            return 0.0, 'sin cantidad', False
        if l.stone_type == 'zirconia':
            return 0.0, 'zirconia: no suma valor', False
        if l.stone_type == 'otra':
            usd = self._nv_usd_gema(cfg, l.nv_gema)
            nombre = dict(GEMAS).get(l.nv_gema or 'otra').lower()
            return ct * usd * tc, '%.3f ct de %s × %s USD/ct%s' % (ct, nombre, round(usd), txt_sup), supuesto
        lab = l.stone_type == 'diamante_lab'
        if ct_c >= cfg.acento_umbral_ct:
            if lab:
                usd = cfg._nv_banda('lab', ct_c)
                return ct * usd * tc, '%s × %.2f ct de laboratorio a %s USD/ct' % (l.qty, ct_c, round(usd)), supuesto
            color, pureza = l.nv_color or COLOR_SUPUESTO, l.nv_pureza or PUREZA_SUPUESTA
            rap, _n = self._nv_precio_rapaport(ct_c, color, pureza, l._nv_forma_rapaport())
            if rap:
                pct = cfg._nv_banda('natural', ct_c)
                sup = '' if (l.nv_color and l.nv_pureza) else ' supuesto'
                return (ct * rap * pct / 100.0 * tc,
                        '%s × %.2f ct natural %s/%s%s: Rapaport %s USD/ct × %s %%' % (
                            l.qty, ct_c, color, pureza, sup, format(round(rap), ','), round(pct)), supuesto)
        usd = cfg.acento_lab_usd if lab else cfg.acento_natural_usd
        return (ct * usd * tc, '%.3f ct %s × %s USD/ct%s' % (ct, 'de laboratorio' if lab else 'naturales',
                                                              round(usd), txt_sup), supuesto)
