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


def _logo_ink(company, lum_cut=248, alpha_cut=120):
    """Binariza res.company.logo a una imagen 'L' (255=tinta) en su resolucion
    nativa, o None.

    Regla COMBINADA alfa+luminancia: tinta = pixel OPACO (alfa>=alpha_cut) Y
    no-casi-blanco (luminancia<lum_cut). Asi conserva iconos claros pero opacos
    (p.ej. el diamante gris del logo DIAMANE, que un umbral simple de luminancia
    borraba) y descarta fondos (transparentes->blanco; blancos opacos->lum 255).
    """
    if Image is None or not company or not company.logo:
        return None
    try:
        src = Image.open(io.BytesIO(base64.b64decode(company.logo))).convert('RGBA')
    except Exception:
        return None
    alpha = src.getchannel('A')
    lum = Image.alpha_composite(
        Image.new('RGBA', src.size, (255, 255, 255, 255)), src).convert('L')
    dark = lum.point(lambda p: 255 if p < lum_cut else 0, mode='L')
    opaque = alpha.point(lambda p: 255 if p >= alpha_cut else 0, mode='L')
    return ImageChops.multiply(dark, opaque)  # 255 = tinta


def _split_icon_wordmark(ink):
    """Parte una imagen de tinta 'L' (255=tinta) en (icono_arriba, wordmark_abajo)
    cortando por la banda HORIZONTAL vacia mas grande del interior. Devuelve crops
    'L' (o None cada uno). Si no hay banda vacia interior, devuelve (None, todo).
    """
    bbox = ink.getbbox()
    if not bbox:
        return None, None
    ink = ink.crop(bbox)
    w, h = ink.size
    px = ink.load()
    row_has = [any(px[x, y] for x in range(w)) for y in range(h)]
    # buscar la banda mas larga de filas vacias ENTRE contenido (no en los bordes)
    best_lo = best_hi = None
    y = 0
    while y < h:
        if not row_has[y]:
            j = y
            while j < h and not row_has[j]:
                j += 1
            if y > 0 and j < h:  # banda interior
                if best_lo is None or (j - y) > (best_hi - best_lo):
                    best_lo, best_hi = y, j
            y = j
        else:
            y += 1
    if best_lo is None:
        return None, ink  # sin separacion: todo es wordmark
    cut = (best_lo + best_hi) // 2
    icon = ink.crop((0, 0, w, cut))
    word = ink.crop((0, cut, w, h))
    ib, wb = icon.getbbox(), word.getbbox()
    return (icon.crop(ib) if ib else None), (word.crop(wb) if wb else None)


def _ink_bands(ink, min_gap=3):
    """Parte una imagen de tinta 'L' (255=tinta) en BANDAS horizontales de
    contenido (separadas por >=min_gap filas vacias), de arriba a abajo. Para el
    logo DIAMANE devuelve [diamante, "DIAMANE", "Diamantes & Tecnologia"], asi se
    puede usar la banda 0 (icono) y la 1 (wordmark) y DESCARTAR el tagline.
    Gaps pequenos (<min_gap) se fusionan para no romper el icono/letras.
    """
    if ink is None:
        return []
    bbox = ink.getbbox()
    if not bbox:
        return []
    ink = ink.crop(bbox)
    w, h = ink.size
    px = ink.load()
    row_has = [any(px[x, y] for x in range(w)) for y in range(h)]
    bands = []
    y = 0
    while y < h:
        if not row_has[y]:
            y += 1
            continue
        start = y
        while y < h:
            if row_has[y]:
                y += 1
                continue
            g = y
            while g < h and not row_has[g]:
                g += 1
            if g >= h or (g - y) >= min_gap:
                break  # fin de banda (gap grande o borde)
            y = g      # gap chico: sigue la misma banda
        band = ink.crop((0, start, w, y))
        bb = band.getbbox()
        if bb:
            bands.append(band.crop(bb))
        while y < h and not row_has[y]:
            y += 1
    return bands


def _ink_to_lo(ink, x, y, target_w, max_h=None):
    """Coloca una imagen de tinta 'L' (255=tinta) como cajas EPL 'LO' en (x,y),
    reescalada a target_w (manteniendo proporcion, con cap opcional de alto).
    Devuelve (comandos, ancho, alto) en dots; ([],0,0) si vacia.
    """
    if ink is None:
        return [], 0, 0
    bb = ink.getbbox()
    if not bb:
        return [], 0, 0
    ink = ink.crop(bb)
    h = max(1, round(ink.height * target_w / ink.width))
    if max_h and h > max_h:
        target_w = max(1, round(target_w * max_h / h))
        h = max_h
    ink = ink.resize((target_w, h), Image.LANCZOS)
    px = ink.load()
    cmds = []
    for ry in range(h):
        rx = 0
        while rx < target_w:
            if px[rx, ry] >= 128:  # tinta
                run = 1
                while rx + run < target_w and px[rx + run, ry] >= 128:
                    run += 1
                cmds.append('LO%d,%d,%d,%d' % (x + rx, y + ry, run, 1))
                rx += run
            else:
                rx += 1
    return cmds, target_w, h


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

    # Layout segun la etiqueta REAL (foto /tmp/diamond_paper2.jpg):
    #   - QR GRANDE a la izquierda (ocupa ~1/3 del ancho y casi toda la altura)
    #   - Encabezado y bloque de datos a la DERECHA del QR
    #   - Icono del diamante centro-derecha (debajo del No. de cert)
    #   - Wordmark "DIAMANE" (SIN tagline) + No. de plastico abajo-derecha
    DATA_X = 262   # columna de etiquetas, a la derecha del QR
    VAL_X = 400    # columna de valores
    # TITULO: banner superior a todo lo ancho, fuente 5 (32x48, la mas grande
    # de EPL) centrado horizontalmente. El QR y los datos van DEBAJO.
    htext = _esc(header)
    hx = max(8, (634 - len(htext) * 32) // 2)
    lines = [
        'N',
        'q634',
        'A%d,14,0,5,1,1,N,"%s"' % (hx, htext),
        'A%d,92,0,3,1,1,N,"Cert"' % DATA_X,
        'A%d,92,0,3,1,1,N,"DIA %s"' % (VAL_X - 40, _esc(cert)),
        'A%d,132,0,4,1,1,N,"CLAVE: %s"' % (DATA_X, _esc(clave)),
        'A%d,180,0,3,1,1,N,"Fluor."' % DATA_X,
        'A%d,180,0,3,1,1,N,"%s"' % (VAL_X, _esc(fluor)),
        'A%d,218,0,3,1,1,N,"Pulido."' % DATA_X,
        'A%d,218,0,3,1,1,N,"%s"' % (VAL_X, _esc(pulido)),
        'A%d,256,0,3,1,1,N,"Simetria:"' % DATA_X,
        'A%d,256,0,3,1,1,N,"%s"' % (VAL_X, _esc(simetria)),
        'A%d,294,0,3,1,1,N,"Brillo"' % DATA_X,
        'A%d,294,0,3,1,1,N,"%s"' % (VAL_X, _esc(brillo)),
    ]
    # QR rasterizado a cajas LO (firmware-independiente). mod=7 -> ~231 dots.
    lines += _qr_as_lo(qr_url, x=16, y=82, mod=7)
    # Logo de la compania DIAMANE (marca de certificacion). Se separa en bandas
    # para usar SOLO el icono (banda 0) y el wordmark "DIAMANE" (banda 1),
    # DESCARTANDO el tagline "Diamantes & Tecnologia" (banda 2).
    company = (tpl.env['res.company'].search([('name', '=', 'DIAMANE')], limit=1)
               or tpl.env.company)
    bands = _ink_bands(_logo_ink(company))
    icon_ink = bands[0] if len(bands) >= 1 else None
    word_ink = bands[1] if len(bands) >= 2 else None
    # Icono del diamante: centro-derecha, debajo del No. de cert.
    icon_cmds, _iw, _ih = _ink_to_lo(icon_ink, x=478, y=150, target_w=95, max_h=120)
    lines += icon_cmds
    # Wordmark "DIAMANE" + numero de plastico, abajo-derecha. Subido para que la
    # BASE del numero quede al ras de la base del renglon "Brillo" (~y=314).
    word_cmds, _ww, word_h = _ink_to_lo(word_ink, x=445, y=264, target_w=175, max_h=46)
    if word_cmds:
        lines += word_cmds
        serie_y = 264 + word_h + 8
    else:
        lines.append('A445,268,0,4,1,1,N,"DIAMANE"')
        serie_y = 310
    # Numero de plastico (font2) abajo-derecha, SIN prefijo "No.".
    lines.append('A445,%d,0,2,1,1,N,"%s"' % (serie_y, _esc(serie)))
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
