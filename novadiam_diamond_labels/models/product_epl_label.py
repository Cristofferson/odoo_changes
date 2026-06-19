# -*- coding: utf-8 -*-
"""Generacion de etiquetas en EPL2 para la Zebra TLP 2844 (NO habla ZPL).

La TLP 2844 es nativa EPL2; el ZPL crudo lo descarta en silencio. Aqui
construimos el codigo EPL2 en Python (control exacto de bytes y saltos de
linea) y la plantilla QWeb solo hace t-out del resultado.

@203 DPI = 8 dots/mm.
  Diamond Papers: 3-1/8" x 2"  -> 634 x 406 dots
  Joyeria:        63 x 22 mm   -> 504 x 176 dots
"""
import base64
import io
import unicodedata
import markupsafe
import qrcode
from odoo import models

try:
    from PIL import Image, ImageChops
except ImportError:  # pragma: no cover
    Image = None


def _logo_as_lo(company, x, y, target_w, lum_cut=248, alpha_cut=120, max_h=90):
    """Rasteriza el logo de una compania (res.company.logo) a comandos EPL 'LO'.

    Misma tecnica firmware-/transporte-segura que el QR: ASCII puro, sin 'GW'
    binario (que el agente corromperia al mandarlo UTF-8->base64).

    Binariza con regla COMBINADA alfa+luminancia: tinta = pixel OPACO (alfa>=
    alpha_cut) Y no-casi-blanco (luminancia<lum_cut). Asi conserva iconos claros
    pero opacos (p.ej. el diamante gris del logo DIAMANE, que un umbral simple de
    luminancia borraba) y a la vez descarta fondos (transparentes -> blanco;
    blancos opacos -> luminancia 255). Luego AUTO-RECORTA al area con tinta.
    Devuelve (comandos, alto_en_dots) o (None,0) si no hay logo / PIL falta /
    nada sobrevive.
    """
    if Image is None or not company or not company.logo:
        return None, 0
    try:
        src = Image.open(io.BytesIO(base64.b64decode(company.logo))).convert('RGBA')
    except Exception:
        return None, 0
    h = max(1, round(src.height * target_w / src.width))
    src = src.resize((target_w, h), Image.LANCZOS)
    alpha = src.getchannel('A')
    lum = Image.alpha_composite(
        Image.new('RGBA', src.size, (255, 255, 255, 255)), src).convert('L')
    dark = lum.point(lambda p: 255 if p < lum_cut else 0, mode='L')
    opaque = alpha.point(lambda p: 255 if p >= alpha_cut else 0, mode='L')
    ink = ImageChops.multiply(dark, opaque)  # 255 donde hay tinta (AND)
    bw = ink.point(lambda p: 0 if p >= 128 else 255, mode='L').convert('1')
    # bbox del area NEGRA: invertir y getbbox (getbbox da bbox de lo no-cero)
    bbox = ImageChops.invert(bw.convert('L')).getbbox()
    if not bbox:
        return None, 0
    bw = bw.crop(bbox)
    if bw.height > max_h:  # cap de alto: reescala manteniendo proporcion
        nw = max(1, round(bw.width * max_h / bw.height))
        bw = bw.resize((nw, max_h), Image.LANCZOS).point(
            lambda p: 0 if p < 128 else 255, mode='L').convert('1')
    px = bw.load()
    w, hh = bw.size
    cmds = []
    for ry in range(hh):
        rx = 0
        while rx < w:
            if px[rx, ry] == 0:  # negro
                run = 1
                while rx + run < w and px[rx + run, ry] == 0:
                    run += 1
                cmds.append('LO%d,%d,%d,%d' % (x + rx, y + ry, run, 1))
                rx += run
            else:
                rx += 1
    return cmds, hh


def _qr_as_lo(data, x, y, mod=4, border=2):
    """Rasteriza un QR a comandos EPL 'LO' (cajas negras), uniendo modulos
    contiguos por fila (run-length) para reducir el numero de comandos.

    Esto NO depende del comando 'b' (QR nativo), que en la TLP 2844 solo
    existe en la version 'Asian' del firmware. Es ASCII puro -> seguro para
    el transporte de texto del agente y funciona en cualquier TLP 2844.
    @203 DPI: mod=4 dots/modulo da un QR comodo de escanear.
    """
    qr = qrcode.QRCode(border=border,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    cmds = []
    for r, row in enumerate(matrix):
        c = 0
        ncol = len(row)
        while c < ncol:
            if row[c]:
                run = 1
                while c + run < ncol and row[c + run]:
                    run += 1
                px = x + c * mod
                py = y + r * mod
                cmds.append('LO%d,%d,%d,%d' % (px, py, run * mod, mod))
                c += run
            else:
                c += 1
    return cmds


def _esc(value):
    """Limpia un valor para usarlo dentro de comillas en un comando EPL."""
    if value is None or value is False:
        return ''
    if not isinstance(value, str):
        value = str(value)
    # Transliterar a ASCII: la TLP 2844 imprime con code page de 1 byte, pero el
    # agente manda UTF-8 -> acentos/n~ saldrian corruptos. "Nina" > basura.
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    # EPL usa comillas dobles como delimitador; barra invertida es escape.
    return (value.replace('\\', '').replace('"', '')
                 .replace('\r', ' ').replace('\n', ' ').strip())


def _diamond_papers_epl(tpl):
    forma = tpl.x_studio_talla_o_forma.display_name or ''
    ct = ('%g' % tpl.x_studio_quilataje_c) if tpl.x_studio_quilataje_c else ''
    pureza = tpl.x_studio_pureza_real.display_name or ''
    color = tpl.x_studio_color_real.display_name or ''
    corte = tpl.x_studio_corte.display_name or ''
    pulido = tpl.x_studio_pulido.display_name or ''
    simetria = tpl.x_studio_simetria_calificacion_c.display_name or ''
    brillo = tpl.x_studio_brillo_c.display_name or ''
    fluor = tpl.x_studio_fluorescencia_intensidad.display_name or ''
    cert = tpl.x_studio_certificado_dia or ''
    clave = tpl.x_studio_id_gema or ''
    lot = tpl.env['stock.lot'].search(
        [('product_id.product_tmpl_id', '=', tpl.id)], order='id desc', limit=1)
    serie = lot.name or ''
    qr_url = 'https://diamane.mx/report-check/%s' % (clave or cert)
    header = ' '.join([v for v in [forma, ct, pureza, color, corte] if v])

    lines = [
        'N',
        'q634',
        'A20,18,0,4,2,2,N,"%s"' % _esc(header),
        'A210,80,0,3,1,1,N,"Cert DIA %s"' % _esc(cert),
        'A210,114,0,4,1,1,N,"CLAVE: %s"' % _esc(clave),
        'A210,152,0,3,1,1,N,"Fluor. %s"' % _esc(fluor),
        'A210,186,0,3,1,1,N,"Pulido. %s"' % _esc(pulido),
        'A210,220,0,3,1,1,N,"Simetria: %s"' % _esc(simetria),
        'A210,254,0,3,1,1,N,"Brillo %s"' % _esc(brillo),
    ]
    # QR rasterizado a cajas LO (no usa el comando 'b', firmware-independiente).
    lines += _qr_as_lo(qr_url, x=20, y=150, mod=4)
    # Logo de la compania DIAMANE (la marca de certificacion de esta etiqueta).
    # Resolvemos por nombre y caemos a la compania activa si no existe; asi el
    # branding es correcto sin importar la compania activa al imprimir.
    company = (tpl.env['res.company'].search([('name', '=', 'DIAMANE')], limit=1)
               or tpl.env.company)
    # Logo (diamante + wordmark) abajo-derecha. Es ~cuadrado, por eso queda
    # solo; el serial va abajo-izquierda (debajo del QR, zona libre).
    logo_cmds, _logo_h = _logo_as_lo(company, x=435, y=280, target_w=150, max_h=118)
    if logo_cmds:
        lines += logo_cmds
    else:
        # Fallback: wordmark de texto (comportamiento anterior).
        lines.append('A435,300,0,4,1,1,N,"DIAMANE"')
    # Serial / numero de plastico, abajo-izquierda bajo el QR.
    lines.append('A20,300,0,3,1,1,N,"No. %s"' % _esc(serie))
    lines.append('P1')
    return lines


def _jewelry_epl(product, price_included, barcode):
    # El SKU NO va en la linea de nombre: ya aparece como texto legible bajo el
    # codigo de barras. Asi el nombre dispone de mas ancho y no se trunca feo.
    pname = product.name or ''
    bc = barcode or product.default_code or ''
    # Font 4 @203dpi = 14 dots/char. Etiqueta 504 dots de ancho.
    # Con precio el nombre debe parar antes de la columna x=300 -> ~20 chars;
    # sin precio dispone de casi todo el ancho -> ~35 chars. (Evita el solape
    # nombre/precio que se veia en el preview con nombres largos.)
    name_max = 20 if price_included else 35
    lines = [
        'N',
        'q504',
        'A8,8,0,4,1,1,N,"%s"' % _esc(pname[:name_max]),
    ]
    if price_included:
        price = '$%s' % '{:,.0f}'.format(product.list_price or 0.0)
        lines.append('A300,12,0,3,1,1,N,"%s"' % _esc(price))
    if bc:
        lines.append('B8,60,0,1,2,4,80,B,"%s"' % _esc(bc))
    lines.append('P1')
    return lines


def _build_epl(product, template, price_included, barcode):
    """product puede ser product.product o product.template."""
    if template == 'diamond_papers':
        tpl = product if product._name == 'product.template' else product.product_tmpl_id
        lines = _diamond_papers_epl(tpl)
    else:
        # jewelry y cualquier otro caso por ahora -> etiqueta de joyeria EPL.
        lines = _jewelry_epl(product, price_included, barcode)
    # LF entre comandos + LF final. Markup para que QWeb no escape caracteres.
    return markupsafe.Markup('\n'.join(lines) + '\n')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def novadiam_epl_label(self, template, price_included=False, barcode=''):
        self.ensure_one()
        return _build_epl(self, template, price_included, barcode)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def novadiam_epl_label(self, template, price_included=False, barcode=''):
        self.ensure_one()
        return _build_epl(self, template, price_included, barcode)
