# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
import subprocess
import tempfile

from odoo import api, models

_logger = logging.getLogger(__name__)

GEM_CATEGORY_ID = 71

# Orden de la galería: fotos generales primero, luego las del laboratorio.
GEMA_GALERIA = [
    ("x_studio_imagen1_c", "Imagen 1"),
    ("x_studio_imagen2_c", "Imagen 2"),
    ("x_studio_imagen3_c", "Imagen 3"),
    ("x_studio_imagen4_c", "Imagen 4"),
    ("x_studio_imagen_medidas_c", "Medidas"),
    ("x_studio_ploteo_pureza", "Ploteo de pureza"),
    ("x_studio_imagen_corazones_c", "Corazones (H&A)"),
    ("x_studio_imagen_flechas_c", "Flechas (H&A)"),
    ("x_studio_imagen_aset2_c", "ASET"),
    ("x_studio_imagen_idealscope2_c", "IdealScope"),
    ("x_studio_imagen_fluorescencia_c", "Fluorescencia"),
    ("x_studio_imagen_color_c", "Comprobación de color"),
    ("x_studio_comprobacin_color_fancy", "Comprobación de color fancy"),
    ("x_studio_imagen_ct_c", "Comprobación de quilataje"),
    ("x_studio_imagen_origen2_c", "Comprobación de origen"),
]
GEMA_VIDEO = "x_studio_video"
# Imágenes de comprobación que se ven al abrir el «ⓘ» de cada casilla.
GEMA_IMAGENES_AYUDA = {
    "aset": [("x_studio_imagen_aset2_c", "Imagen ASET")],
    "idealscope": [("x_studio_imagen_idealscope2_c", "Imagen IdealScope")],
    "ha": [("x_studio_imagen_corazones_c", "Corazones"), ("x_studio_imagen_flechas_c", "Flechas")],
    "pureza": [("x_studio_ploteo_pureza", "Ploteo de pureza")],
    "fluorescencia": [("x_studio_imagen_fluorescencia_c", "Comprobación de fluorescencia")],
    "color": [("x_studio_imagen_color_c", "Comprobación de color"),
              ("x_studio_comprobacin_color_fancy", "Comprobación de color fancy")],
    "quilataje": [("x_studio_imagen_ct_c", "Comprobación de quilataje")],
    "origen": [("x_studio_imagen_origen2_c", "Comprobación de origen")],
}

# Nombre del laboratorio en «Certificado(s)» -> sus campos. Studio los nombró
# distinto en cada tanda, por eso no se pueden armar con un patrón.
LABORATORIOS = {
    "DIAMANE": dict(numero="x_studio_certificado_dia", fecha="x_studio_fecha_reporte_dia",
                    laser="x_studio_laser_dia", imagen="x_studio_imagen_inscripcion_dia",
                    comentarios="x_studio_comentarios_del_certificado_dia",
                    pdf="x_studio_pfd_certificado_dia", verificar="x_studio_verificacion_reporte_dia"),
    "GIA": dict(numero="x_studio_certificado_gia_c", fecha="x_studio_fecha_reporte_gia_c",
                laser="x_studio_laser_gia_c", imagen="x_studio_imagen_inscripcion_gia_c",
                comentarios="x_studio_comentarios_certificado_gia_c",
                pdf="x_studio_pdf_certificado_gia_c", verificar="x_studio_gia_report_check_c"),
    "IGI": dict(numero="x_studio_certificado_igi_c", fecha="x_studio_fecha_reporte_igi_c",
                laser="x_studio_laser_igi_c", imagen="x_studio_imagen_inscipcion_igi_c",
                comentarios="x_studio_comentarios_certificado_igi_c",
                pdf="x_studio_pdf_certificado_igi_c", verificar="x_studio_igi_report_check_c"),
    "AGS": dict(numero="x_studio_certificado_ags_c", fecha="x_studio_fecha_reporte_ags_c",
                laser="x_studio_laser_ags_c", imagen="x_studio_imagen_inscripcion_ags_c",
                comentarios="x_studio_comentarios_certificado_ags_c",
                pdf="x_studio_pdf_certificado_ags_c", verificar="x_studio_ags_report_check_c"),
    "EGL": dict(numero="x_studio_certificado_egl_c", fecha="x_studio_fecha_reporte_egl_c",
                laser="x_studio_laser_egl_c", imagen="x_studio_imagen_inscripcion_egl_c",
                comentarios="x_studio_comentarios_certificado_egl_c",
                pdf="x_studio_pdf_certificado_egl_c", verificar="x_studio_egl_report_check_c"),
    "HRD": dict(numero="x_studio_certificado_hrd_c", fecha="x_studio_fecha_reporte_hrd_c",
                laser="x_studio_laser_hrd_c", imagen="x_studio_imagen_inscripcion_hrd_c",
                comentarios="x_studio_comentarios_certificado_hrd_c",
                pdf="x_studio_pdf_certificado_hrd_c", verificar="x_studio_hrd_report_check_c"),
    "GRA": dict(numero="x_studio_certificado_gra", fecha="x_studio_fecha_del_reporte_gra",
                laser="x_studio_inscripcion_laser_gra", imagen="x_studio_imagen_de_la_inscripcion_gra",
                comentarios="x_studio_comentarios_del_certificado_gra",
                pdf="x_studio_pdf_certificado_gra", verificar="x_studio_verificacion_del_reporte_gra"),
    "GCAL": dict(numero="x_studio_certificado_gcal", fecha="x_studio_fecha_del_reporte_gcal",
                 laser="x_studio_inscripcion_laser_gcal", imagen="x_studio_imagen_de_la_inscripcion_gcal",
                 comentarios="x_studio_comentarios_certificado_gcal",
                 pdf="x_studio_pdf_certificado_gcal", verificar="x_studio_verificacion_del_reporte_gcal"),
    "GSI": dict(numero="x_studio_certificado_gsi", fecha="x_studio_fecha_del_reporte_gsi",
                laser="x_studio_inscripcion_laser_gsi", imagen="x_studio_imagen_de_la_inscripcion_gsi",
                comentarios="x_studio_comentarios_del_certificado_gsi",
                pdf="x_studio_pdf_certificado_gsi", verificar="x_studio_verificacion_del_reporte_gsi"),
}


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _xb_es_gema(self):
        """La misma condición que usaba la vista vieja de las tablas."""
        self.ensure_one()
        return bool(
            self.categ_id.id == GEM_CATEGORY_ID
            or ("x_studio_tipo_gema_c" in self._fields and self.x_studio_tipo_gema_c)
            or ("x_studio_id_gema" in self._fields and self.x_studio_id_gema)
            or ("x_studio_quilataje_c" in self._fields and self.x_studio_quilataje_c))

    def _xb_gema_imagenes(self):
        """{clave: [(campo, texto alterno)]} con las imágenes de laboratorio
        que esta gema SÍ tiene; van dentro del globo «ⓘ» de su casilla."""
        self.ensure_one()
        b = self.with_context(bin_size=True)
        return {clave: [(c, alt) for c, alt in campos if c in self._fields and b[c]]
                for clave, campos in GEMA_IMAGENES_AYUDA.items()}

    def _xb_gema_ayudas(self):
        """{clave: {"nombre", "texto"}} del botón «ⓘ» (modelo xb.gema.ayuda)."""
        return {a.clave: {"nombre": a.name, "texto": a.explicacion or ""}
                for a in self.env["xb.gema.ayuda"].sudo().search([])}

    def _xb_gema_txt(self, campo, campo_explicacion=None):
        """Valor en palabras para la tabla: la explicación que capturaron en la
        gema («Excelente (Excellent)» -> «Excelente») o, si no hay, el valor
        tal cual (código «EX», «Si» -> «Sí»). Vacío si no hay nada."""
        self.ensure_one()
        texto = ""
        if campo_explicacion and campo_explicacion in self._fields:
            texto = re.sub(r"\s*\([^)]*\)\s*$", "", self[campo_explicacion] or "").strip()
        if not texto and campo in self._fields and self[campo]:
            field = self._fields[campo]
            valor = self[campo]
            if field.type == "many2one":
                texto = valor.sudo().display_name
            elif field.type == "selection":
                texto = dict(field._description_selection(self.env)).get(valor, valor)
            else:
                texto = str(valor)
        return {"Si": "Sí", "SI": "Sí"}.get(texto, texto)

    def _xb_gema_escalas(self):
        """Las 4C para las barras de la ficha: [{clave, nombre, valor, texto,
        pasos: [{etiqueta, activo, banda}], izq, der}]. Una C cuyo valor no
        cae en su escala (corte «N/A», color fancy…) va con pasos=[] y la
        plantilla la pinta como fila normal. Vacía si no hay dato."""
        self.ensure_one()

        def escala(clave, nombre, valor, texto, pasos, activo, banda, izq, der):
            if not valor:
                return None
            return {"clave": clave, "nombre": nombre, "valor": valor, "texto": texto, "izq": izq, "der": der,
                    "pasos": [{"etiqueta": e, "activo": e == activo, "banda": i in banda}
                              for i, e in enumerate(pasos)] if activo else []}

        res = []
        ct = "x_studio_quilataje_c" in self._fields and self.x_studio_quilataje_c
        if ct:
            cortes = [0, 0.30, 0.50, 0.70, 0.90, 1.00, 1.50, 2.00, 3.00]
            etiquetas = ["<0.30", "0.30", "0.50", "0.70", "0.90", "1.00", "1.50", "2.00", "3.00+"]
            i = max(k for k, c in enumerate(cortes) if ct >= c - 0.005)
            res.append(escala("quilataje", "Quilates", "%.2f ct" % ct, "", etiquetas, etiquetas[i], set(),
                              "Más pequeño", "Más grande"))

        color = self._xb_gema_txt("x_studio_color_real").strip().upper()
        pasos = list("DEFGHIJKLM") + ["N–R", "S–Z"]
        activo = color if color in "DEFGHIJKLM" and len(color) == 1 else (
            "N–R" if color in list("NOPQR") else "S–Z" if color in list("STUVWXYZ") else None)
        grupos = {"D": "Incoloro", "E": "Incoloro", "F": "Incoloro", "G": "Casi incoloro", "H": "Casi incoloro",
                  "I": "Casi incoloro", "J": "Casi incoloro", "K": "Tono tenue", "L": "Tono tenue", "M": "Tono tenue",
                  "N–R": "Tono muy ligero", "S–Z": "Tono ligero"}
        res.append(escala("color", "Color", color, grupos.get(activo, ""), pasos, activo, {0, 1, 2},
                          "Incoloro", "Tono visible"))

        pureza = self._xb_gema_txt("x_studio_pureza_real").strip().upper()
        pasos = ["FL", "IF", "VVS1", "VVS2", "VS1", "VS2", "SI1", "SI2", "I1", "I2", "I3"]
        textos = {"FL": "Sin inclusiones", "IF": "Sin inclusiones internas", "VVS1": "Inclusiones muy, muy ligeras",
                  "VVS2": "Inclusiones muy, muy ligeras", "VS1": "Inclusiones muy ligeras", "VS2": "Inclusiones muy ligeras",
                  "SI1": "Inclusiones ligeras", "SI2": "Inclusiones ligeras", "I1": "Inclusiones visibles",
                  "I2": "Inclusiones visibles", "I3": "Inclusiones visibles"}
        res.append(escala("pureza", "Pureza", pureza, textos.get(pureza, ""), pasos,
                          pureza if pureza in pasos else None, {0, 1, 2, 3}, "Sin inclusiones", "Inclusiones visibles"))

        corte = self._xb_gema_txt("x_studio_corte").strip().upper()
        palabras = {"P": "Pobre", "F": "Regular", "G": "Bueno", "VG": "Muy bueno", "EX": "Excelente"}
        if corte != "N/A":
            res.append(escala("corte", "Corte", corte, palabras.get(corte, ""), list(palabras.values()),
                              palabras.get(corte), set(), "Pobre", "Excelente"))
        return [r for r in res if r]

    def _xb_gema_fluorescencia(self):
        """«Fuerte, azul»; sin el color cuando no hay fluorescencia (antes
        salía «Ninguna, ninguna»)."""
        self.ensure_one()
        intensidad = self._xb_gema_txt("x_studio_fluorescencia_intensidad", "x_studio_explicacin_de_la_fluorescencia")
        color = self._xb_gema_txt("x_studio_fluorescencia_color_c", "x_studio_fluorescencia_color_explicac_c").lower()
        if not intensidad or intensidad.strip().lower() in ("ninguna", "none", "n/a", "nula") or color in ("ninguna", "none", "n/a"):
            return intensidad
        return ", ".join(x for x in (intensidad, color) if x)

    def _xb_gema_certificados(self):
        """Un dict por laboratorio de «Certificado(s)» con sus datos; el campo
        de imagen va como nombre (la vista arma la URL, no incrusta el archivo)."""
        self.ensure_one()
        if "x_studio_certificados" not in self._fields:
            return []
        bin_self = self.with_context(bin_size=True)
        res = []
        # sudo: el visitante de la tienda no puede leer el modelo de laboratorios.
        for lab in self.sudo().x_studio_certificados:
            campos = LABORATORIOS.get((lab.display_name or "").strip().upper())
            if not campos:
                continue
            datos = {"laboratorio": lab.display_name,
                     "clave": "lab_" + (lab.display_name or "").strip().upper()}
            for clave, campo in campos.items():
                if campo not in self._fields:
                    datos[clave] = False
                elif clave == "imagen":
                    datos[clave] = campo if bin_self[campo] else False
                else:
                    datos[clave] = self[campo]
            res.append(datos)
        return res

    def _xb_sync_gema_galeria(self):
        """Refleja las fotos y el video de la gema como «Medios extra» del
        producto, que es lo que pinta la galería de la tienda (cuadrícula o
        carrusel). Solo toca las fotos que él mismo creó (xb_gema_field)."""
        Image = self.env["product.image"].sudo()
        for template in self:
            # Sin esto, leer una foto precarga ESA foto de todas las gemas del
            # lote (cientos de MB en el post_init_hook).
            template = template.with_prefetch(template._ids)
            existentes = {i.xb_gema_field: i for i in template.product_template_image_ids
                          if i.xb_gema_field}
            if not template._xb_es_gema():
                existentes and Image.browse([i.id for i in existentes.values()]).unlink()
                continue
            nombre = template.x_studio_id_gema if "x_studio_id_gema" in template._fields else False
            nombre = "Gema %s" % nombre if nombre else template.name
            primera = False
            for seq, (campo, etiqueta) in enumerate(GEMA_GALERIA + [(GEMA_VIDEO, "Video")]):
                if campo not in template._fields:
                    continue
                actual = existentes.pop(campo, None)
                if campo == GEMA_VIDEO:
                    tiene = bool(template.with_context(bin_size=True)[campo])
                    # Portada del video: la primera foto de la gema o la principal.
                    datos = primera or template.image_1920
                else:
                    datos = template[campo]
                    # Suele ser la misma foto que la principal: no repetirla.
                    tiene = bool(datos) and datos != template.image_1920
                    primera = primera or datos
                if not tiene:
                    actual and actual.unlink()
                    continue
                vals = {"name": "%s · %s" % (nombre, etiqueta), "sequence": 1000 + seq,
                        "image_1920": datos}
                if actual:
                    actual.write(vals)
                else:
                    Image.create(dict(vals, product_tmpl_id=template.id, xb_gema_field=campo))
            if existentes:
                Image.browse([i.id for i in existentes.values()]).unlink()

    @api.model
    def _xb_video_sin_audio(self, valor):
        """Quita la pista de audio a un video en base64 (lo que llega en
        vals). Copia el video tal cual, sin recomprimir (`-c copy`). Si no
        trae audio, o ffmpeg falla, devuelve el valor original: nunca se
        pierde un video por esto."""
        if not valor:
            return valor
        try:
            datos = base64.b64decode(valor)
        except Exception:
            return valor
        with tempfile.TemporaryDirectory(prefix="xb_gema_video_") as tmp:
            entrada = os.path.join(tmp, "entrada")
            salida = os.path.join(tmp, "salida.mp4")
            with open(entrada, "wb") as f:
                f.write(datos)
            try:
                audio = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                     "stream=index", "-of", "csv=p=0", entrada],
                    capture_output=True, text=True, timeout=60).stdout.strip()
                if not audio:
                    return valor
                subprocess.run(
                    ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", entrada, "-map", "0:v",
                     "-c", "copy", "-movflags", "+faststart", "-f", "mp4", salida],
                    check=True, capture_output=True, timeout=300)
                with open(salida, "rb") as f:
                    nuevo = f.read()
            except Exception as e:  # ffmpeg ausente, formato raro, tiempo agotado…
                _logger.warning("No se pudo quitar el audio al video de la gema: %s", e)
                return valor
        if not nuevo:
            return valor
        return base64.b64encode(nuevo)

    def _xb_vals_sin_audio(self, vals):
        if vals.get(GEMA_VIDEO) and not self.env.context.get("bin_size"):
            vals = dict(vals, **{GEMA_VIDEO: self._xb_video_sin_audio(vals[GEMA_VIDEO])})
        return vals

    def _xb_sync_categoria_diamantes(self):
        """Pone (o quita) la categoría de tienda «Diamantes» según la gema sea
        de tipo Diamante. Las demás categorías de tienda no se tocan."""
        categ = self.env.ref("xb_gema_ficha_web.categ_diamantes", raise_if_not_found=False)
        if not categ or "x_studio_tipo_gema_c" not in self._fields:
            return
        for t in self:
            es = t.categ_id.id == GEM_CATEGORY_ID and (t.x_studio_tipo_gema_c.display_name or "").strip().lower() == "diamante"
            tiene = categ in t.public_categ_ids
            if es and not tiene:
                t.sudo().public_categ_ids = [(4, categ.id)]
            elif tiene and not es:
                t.sudo().public_categ_ids = [(3, categ.id)]

    _XB_CAMPOS_SYNC = {c for c, _e in GEMA_GALERIA} | {
        GEMA_VIDEO, "image_1920", "categ_id", "x_studio_id_gema", "x_studio_tipo_gema_c",
        "x_studio_quilataje_c"}

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._xb_vals_sin_audio(vals) for vals in vals_list]
        templates = super().create(vals_list)
        templates._xb_sync_categoria_diamantes()
        if any(self._XB_CAMPOS_SYNC.intersection(vals) for vals in vals_list):
            templates._xb_sync_gema_galeria()
        return templates

    def write(self, vals):
        vals = self._xb_vals_sin_audio(vals)
        res = super().write(vals)
        if {"categ_id", "x_studio_tipo_gema_c"}.intersection(vals):
            self._xb_sync_categoria_diamantes()
        if self._XB_CAMPOS_SYNC.intersection(vals):
            self._xb_sync_gema_galeria()
        return res
