"""Todas las piedras de un anillo para el avalúo: la central (diamante, piedra de
color o ninguna) y los grupos de piedras laterales y acentos.

Los grupos viven en `dmn.accent.line` (stij_diamane_plus), el mismo renglón que
usan la ficha de la gema y el visor: aquí solo se les agrega lo que el avalúo
necesita (posición, gema, color y pureza) y su valor.
"""
from odoo import api, fields, models

from odoo.addons.stij_diamane_plus.models.dmn_accent_line import TABLA_MM_CT, quilates_de_mm

from .nv_avaluo import COLORES, PUREZAS, COLOR_SUPUESTO, PUREZA_SUPUESTA

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
    nv_gema = fields.Selection(GEMAS, 'Piedra de color', help='Solo si el tipo es «Otra piedra».')
    nv_color = fields.Selection([(c, c) for c in COLORES], 'Color',
                                help='Para laterales con certificado. Vacío = el supuesto (%s).' % COLOR_SUPUESTO)
    nv_pureza = fields.Selection([(p, p) for p in PUREZAS], 'Pureza',
                                 help='Para laterales con certificado. Vacío = la supuesta (%s).' % PUREZA_SUPUESTA)
    nv_ia = fields.Boolean('Contadas por IA', help='Las propuso «Leer fotos». Revisa cantidad, tamaño y tipo.')
    currency_id = fields.Many2one(related='product_tmpl_id.currency_id')
    nv_valor = fields.Monetary('Valor', compute='_compute_nv_valor', currency_field='currency_id')
    nv_valor_nota = fields.Char('Cómo', compute='_compute_nv_valor')

    @api.depends('qty', 'size_mm', 'carats_each', 'stone_type', 'nv_gema', 'nv_color', 'nv_pureza')
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

    def _nv_texto_avaluo(self):
        """«14 de 1.50 mm · halo · diamante natural G/VS2»."""
        self.ensure_one()
        tipo = dict(self._fields['stone_type'].selection).get(self.stone_type, '').lower()
        if self.stone_type == 'otra' and self.nv_gema:
            tipo = dict(GEMAS)[self.nv_gema].lower()
        elif self.stone_type in ('diamante_nat', 'diamante_lab') and (self.nv_color or self.nv_pureza):
            tipo += ' %s/%s' % (self.nv_color or '?', self.nv_pureza or '?')
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
            rap, _n = self._nv_precio_rapaport(ct_c, color, pureza)
            if rap:
                pct = cfg._nv_banda('natural', ct_c)
                sup = '' if (l.nv_color and l.nv_pureza) else ' supuesto'
                return (ct * rap * pct / 100.0 * tc,
                        '%s × %.2f ct natural %s/%s%s: Rapaport %s USD/ct × %s %%' % (
                            l.qty, ct_c, color, pureza, sup, format(round(rap), ','), round(pct)), supuesto)
        usd = cfg.acento_lab_usd if lab else cfg.acento_natural_usd
        return (ct * usd * tc, '%.3f ct %s × %s USD/ct%s' % (ct, 'de laboratorio' if lab else 'naturales',
                                                              round(usd), txt_sup), supuesto)
