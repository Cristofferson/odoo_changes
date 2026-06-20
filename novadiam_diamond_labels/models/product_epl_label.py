# -*- coding: utf-8 -*-
"""Generacion de etiquetas en EPL2 para la Zebra TLP 2844 (NO habla ZPL).

La TLP 2844 es nativa EPL2; el ZPL crudo lo descarta en silencio. Aqui
construimos el codigo EPL2 en Python (control exacto de bytes y saltos de
linea) y la plantilla QWeb solo hace t-out del resultado.

@203 DPI = 8 dots/mm.
  Diamond Papers: 78 x 34 mm   -> 624 x 272 dots
  Joyeria:        63 x 22 mm   -> 504 x 176 dots
"""
import base64
import io
import unicodedata
import markupsafe
import qrcode
from odoo import models

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None

# Fuente para rasterizar texto a cajas LO (p.ej. el numero de plastico, que debe
# tener EXACTAMENTE el ancho del wordmark "DIAMANE"; la fuente nativa EPL solo
# escala por multiplos enteros y no permite cuadrar ese ancho).
_TTF = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'


def _text_ink(text, font_px=48):
    """Renderiza `text` a una imagen 'L' (255=tinta) recortada al contenido, o
    None si no hay PIL/fuente. Se usa con _ink_to_lo para escalar el texto a un
    ancho objetivo (mismo ancho que DIAMANE)."""
    if Image is None or not text:
        return None
    try:
        font = ImageFont.truetype(_TTF, font_px)
    except Exception:
        return None
    bb = font.getbbox(text)
    w = max(1, bb[2] - bb[0]) + 4
    h = max(1, bb[3] - bb[1]) + 4
    img = Image.new('L', (w, h), 0)
    ImageDraw.Draw(img).text((2 - bb[0], 2 - bb[1]), text, fill=255, font=font)
    crop = img.getbbox()
    return img.crop(crop) if crop else None


def _scaled_size(ink, target_w, max_h=None):
    """Tamano (w,h) en dots que tendria `ink` reescalada a target_w (con cap
    opcional de alto), SIN dibujarla. Espeja la logica de _ink_to_lo para poder
    apilar/alinear elementos antes de colocarlos."""
    if ink is None:
        return 0, 0
    bb = ink.getbbox()
    if not bb:
        return 0, 0
    iw = bb[2] - bb[0]
    ih = bb[3] - bb[1]
    h = max(1, round(ih * target_w / iw))
    if max_h and h > max_h:
        target_w = max(1, round(target_w * max_h / h))
        h = max_h
    return target_w, h


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

    # Layout segun la etiqueta REAL (foto /tmp/diamond_paper2.jpg), pero a su
    # tamano FISICO correcto 78x34 mm = 624x272 dots @203dpi (antes se uso por
    # error 634x406 y todo desbordaba por abajo). Mismo arreglo visual, eje Y
    # comprimido para caber en 272 dots:
    #   - TITULO banner arriba (font 4; el font 5 de 48 dots no cabe ya)
    #   - QR GRANDE a la izquierda (mod=6 ~ 198-222 dots de alto)
    #   - Encabezado y bloque de datos a la DERECHA del QR
    #   - Icono del diamante derecha (debajo del No. de cert)
    #   - Wordmark "DIAMANE" (SIN tagline) + No. de plastico abajo-derecha
    WIDTH = 624
    DATA_X = 240   # columna de etiquetas, a la derecha del QR
    VAL_X = 366    # columna de valores
    # TITULO: banner superior centrado, fuente 5 (32x48, la mas grande de EPL)
    # para que abarque todo el renglon. El QR y los datos van DEBAJO.
    htext = _esc(header)
    hx = max(4, (WIDTH - len(htext) * 32) // 2)
    lines = [
        'N',
        'q624',
        'A%d,2,0,5,1,1,N,"%s"' % (hx, htext),
        'A%d,58,0,3,1,1,N,"Cert"' % DATA_X,
        'A%d,58,0,3,1,1,N,"DIA %s"' % (DATA_X + 84, _esc(cert)),
        'A%d,89,0,4,1,1,N,"CLAVE: %s"' % (DATA_X, _esc(clave)),
        'A%d,120,0,3,1,1,N,"Fluor."' % DATA_X,
        'A%d,120,0,3,1,1,N,"%s"' % (VAL_X, _esc(fluor)),
        'A%d,151,0,3,1,1,N,"Pulido."' % DATA_X,
        'A%d,151,0,3,1,1,N,"%s"' % (VAL_X, _esc(pulido)),
        'A%d,182,0,3,1,1,N,"Simetria:"' % DATA_X,
        'A%d,182,0,3,1,1,N,"%s"' % (VAL_X, _esc(simetria)),
        'A%d,213,0,3,1,1,N,"Brillo"' % DATA_X,
        'A%d,213,0,3,1,1,N,"%s"' % (VAL_X, _esc(brillo)),
    ]
    # QR rasterizado a cajas LO (firmware-independiente). El modulo se calcula
    # dinamicamente: el QR mas grande que quepa a la izquierda (debajo del
    # titulo) sin desbordar el alto 272 ni invadir la columna de datos. Asi una
    # clave corta da un QR mas grande y una larga (mas modulos) no desborda.
    _qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    _qr.add_data(qr_url)
    _qr.make(fit=True)
    n_mod = len(_qr.get_matrix())
    qr_y = 52
    # El QR vive en la columna izquierda: puede bajar hasta ~262 (no choca con
    # los datos, que estan a la derecha). Asi entra mod=6 (~198 dots) en vez de 5.
    qr_mod = max(4, min(7, (262 - qr_y) // n_mod, (DATA_X - 12 - 6) // n_mod))
    lines += _qr_as_lo(qr_url, x=12, y=qr_y, mod=qr_mod, border=2)
    # Logo de la compania DIAMANE (marca de certificacion). Se separa en bandas
    # para usar SOLO el icono (banda 0) y el wordmark "DIAMANE" (banda 1),
    # DESCARTANDO el tagline "Diamantes & Tecnologia" (banda 2).
    company = (tpl.env['res.company'].search([('name', '=', 'DIAMANE')], limit=1)
               or tpl.env.company)
    bands = _ink_bands(_logo_ink(company))
    icon_ink = bands[0] if len(bands) >= 1 else None
    word_ink = bands[1] if len(bands) >= 2 else None
    # Bloque-marca abajo-derecha, replicando el LOGO de DIAMANE (icono sobre la
    # palabra): icono CENTRADO arriba, "DIAMANE" en medio y el numero de plastico
    # (mismo ancho que la palabra) abajo, con su BASE al ras de "Brillo" (y=233).
    WORD_X = 432
    WORD_TW = 182
    BRILLO_BOT = 233          # base de "Brillo" (font 3 @ y=213 -> 213+20)
    word_cx = WORD_X + WORD_TW // 2
    eserie = _esc(serie)
    serie_ink = _text_ink(eserie)
    ww, wh = _scaled_size(word_ink, WORD_TW, 46)      # tamano real del wordmark
    if not ww:                                        # sin logo: caer a texto EPL
        ww, wh = 7 * 14, 24
    sw, sh = _scaled_size(serie_ink, ww)              # numero al ancho del wordmark
    if not sw:
        sw, sh = len(eserie) * 10, 16
    # Icono al MISMO escalado que la palabra: en el logo el diamante mide 56 de
    # ancho y "DIAMANE" 127 -> icono = WORD_TW * 56/127 (~80). Asi conserva la
    # proporcion icono:palabra del logo. Centrado sobre la palabra.
    icon_tw = round(WORD_TW * 56 / 127)
    iw, ih = _scaled_size(icon_ink, icon_tw, 130)
    # Apilado de abajo hacia arriba para fijar la base del numero en BRILLO_BOT.
    serie_y = BRILLO_BOT - sh
    word_y = serie_y - 6 - wh
    icon_y = word_y - 8 - ih
    icon_x = word_cx - iw // 2
    icon_cmds, _iw, _ih = _ink_to_lo(icon_ink, x=icon_x, y=icon_y, target_w=icon_tw, max_h=130)
    lines += icon_cmds
    word_cmds, _ww2, _wh2 = _ink_to_lo(word_ink, x=WORD_X, y=word_y, target_w=WORD_TW, max_h=46)
    if word_cmds:
        lines += word_cmds
    else:
        lines.append('A%d,%d,0,4,1,1,N,"DIAMANE"' % (WORD_X, word_y))
    serie_cmds, _sw2, _sh2 = _ink_to_lo(serie_ink, x=WORD_X, y=serie_y, target_w=ww)
    if serie_cmds:
        lines += serie_cmds
    else:  # fallback: texto EPL alineado a la derecha del wordmark
        lines.append('A%d,%d,0,2,1,1,N,"%s"' % (
            WORD_X + ww - len(eserie) * 10, serie_y, eserie))
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
