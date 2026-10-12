# -*- coding: utf-8 -*-
"""Antes de mandar un archivo por WhatsApp, lo vuelve compatible.

WhatsApp solo acepta de un sistema (Cloud API): video MP4 (H.264 + AAC) de hasta
16 MB y fotos JPEG/PNG de hasta 5 MB. El iPhone graba en .MOV (HEVC) y toma las
fotos en .HEIC: el nativo los rechaza con «Attachment mimetype is not supported».
Aquí se convierten en el adjunto mismo, así en la plática queda lo que se mandó.
"""
import io
import json
import logging
import os
import subprocess
import tempfile

from PIL import Image

from odoo import api, models

_logger = logging.getLogger(__name__)

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:  # sin la librería, las fotos HEIC siguen sin poder mandarse
    pillow_heif = None

MB = 1024 * 1024
VIDEO_MAX = 16 * MB
VIDEO_TARGET = 15 * MB          # margen para el contenedor
IMAGE_MAX = 5 * MB
VIDEO_LADO = 1280               # lado mayor (720p)
FOTO_LADO = 2048
FFMPEG_TIMEOUT = 300            # el worker tiene limit_time_real = 600
EXT_VIDEO = (".mov", ".m4v", ".3gp", ".avi", ".mkv", ".webm", ".mp4", ".hevc")
EXT_FOTO_CONVERTIR = (".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def _ext(name):
    return os.path.splitext(name or "")[1].lower()


def _probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name:format=duration",
         "-of", "json", path], capture_output=True, timeout=60, check=True).stdout
    data = json.loads(out or b"{}")
    codecs = {s.get("codec_type"): s.get("codec_name") for s in data.get("streams", [])}
    return codecs, float(data.get("format", {}).get("duration") or 0)


def _ffmpeg(origen, destino, video_args):
    escala = (f"scale='if(gt(iw,ih),min({VIDEO_LADO},iw),-2)':"
              f"'if(gt(iw,ih),-2,min({VIDEO_LADO},ih))'")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", origen, "-map", "0:v:0", "-map", "0:a:0?",
           "-vf", escala, "-c:v", "libx264", "-preset", "veryfast", *video_args,
           "-pix_fmt", "yuv420p", "-profile:v", "main", "-threads", "2",
           "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-movflags", "+faststart", destino]
    subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT, check=True)
    return os.path.getsize(destino)


def video_compatible(raw, name):
    """Devuelve el MP4 listo para WhatsApp, o None si ya lo era."""
    with tempfile.TemporaryDirectory(prefix="xb_wa_") as tmp:
        origen = os.path.join(tmp, "origen" + (_ext(name) or ".bin"))
        destino = os.path.join(tmp, "salida.mp4")
        with open(origen, "wb") as f:
            f.write(raw)
        codecs, duracion = _probe(origen)
        if (_ext(name) == ".mp4" and len(raw) <= VIDEO_MAX and codecs.get("video") == "h264"
                and codecs.get("audio") in (None, "aac")):
            return None
        tam = _ffmpeg(origen, destino, ["-crf", "26"])
        if tam > VIDEO_MAX and duracion:
            # Bitrate fijo para que quepa: (15 MB en bits / segundos) menos el audio.
            kbps = max(int(VIDEO_TARGET * 8 / duracion / 1000) - 128, 150)
            tam = _ffmpeg(origen, destino, ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k",
                                            "-bufsize", f"{kbps * 2}k"])
        if tam > VIDEO_MAX:
            raise ValueError("El video es demasiado largo para WhatsApp aun comprimido (máx. 16 MB).")
        with open(destino, "rb") as f:
            return f.read()


def foto_compatible(raw):
    img = Image.open(io.BytesIO(raw))
    img.load()
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001 - la orientación es lo de menos
        pass
    img = img.convert("RGB")
    for lado, calidad in ((FOTO_LADO, 88), (1600, 82), (1280, 75)):
        copia = img.copy()
        copia.thumbnail((lado, lado))
        buf = io.BytesIO()
        copia.save(buf, "JPEG", quality=calidad, optimize=True)
        if buf.tell() <= IMAGE_MAX:
            return buf.getvalue()
    return buf.getvalue()


class WhatsAppMessage(models.Model):
    _inherit = "whatsapp.message"

    @api.model
    def _prepare_attachment_vals(self, attachment, wa_account_id):
        try:
            self._xb_wa_make_compatible(attachment)
        except Exception:  # noqa: BLE001 - si no se pudo, el nativo avisa como siempre
            _logger.exception("xb_whatsapp_media_fast: no se pudo convertir el adjunto %s", attachment.id)
        return super()._prepare_attachment_vals(attachment, wa_account_id)

    @api.model
    def _xb_wa_make_compatible(self, attachment):
        attachment = attachment.sudo()
        mime = attachment.mimetype or ""
        ext = _ext(attachment.name)
        base = os.path.splitext(attachment.name or "archivo")[0]
        if mime.startswith("video/") or ext in EXT_VIDEO:
            raw = video_compatible(attachment.raw, attachment.name)
            if raw is None:
                return
            antes = attachment.file_size
            attachment.write({"raw": raw, "name": base + ".mp4", "mimetype": "video/mp4"})
            _logger.info("xb_whatsapp_media_fast: video %s convertido a MP4 (%s → %s bytes)",
                         attachment.id, antes, len(raw))
        elif (mime in ("image/heic", "image/heif", "image/webp", "image/gif", "image/bmp", "image/tiff")
              or ext in EXT_FOTO_CONVERTIR
              or (mime in ("image/jpeg", "image/png") and attachment.file_size > IMAGE_MAX)):
            if ext in (".heic", ".heif") and pillow_heif is None:
                return
            antes = attachment.file_size
            raw = foto_compatible(attachment.raw)
            attachment.write({"raw": raw, "name": base + ".jpg", "mimetype": "image/jpeg"})
            _logger.info("xb_whatsapp_media_fast: foto %s convertida a JPG (%s → %s bytes)",
                         attachment.id, antes, len(raw))
