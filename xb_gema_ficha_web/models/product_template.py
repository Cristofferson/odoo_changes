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

    _XB_CAMPOS_SYNC = {c for c, _e in GEMA_GALERIA} | {
        GEMA_VIDEO, "image_1920", "categ_id", "x_studio_id_gema", "x_studio_tipo_gema_c",
        "x_studio_quilataje_c"}

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._xb_vals_sin_audio(vals) for vals in vals_list]
        templates = super().create(vals_list)
        if any(self._XB_CAMPOS_SYNC.intersection(vals) for vals in vals_list):
            templates._xb_sync_gema_galeria()
        return templates

    def write(self, vals):
        vals = self._xb_vals_sin_audio(vals)
        res = super().write(vals)
        if self._XB_CAMPOS_SYNC.intersection(vals):
            self._xb_sync_gema_galeria()
        return res
