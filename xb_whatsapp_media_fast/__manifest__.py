# -*- coding: utf-8 -*-
{
    "name": "XB WhatsApp — descarga rápida de archivos",
    "version": "19.0.1.1.0",
    "summary": "Baja rápido los archivos de WhatsApp y convierte videos .MOV y fotos .HEIC del iPhone para poder mandarlos",
    "description": """
El nativo (``WhatsAppApi.__api_requests``) intenta leer como JSON cada respuesta
de menos de 10 MB, también el archivo. Como Meta no manda ``charset``,
``requests`` adivina la codificación con ``chardet`` sobre TODO el binario:
~6 s por MB de CPU. Un video de 4 MB tardaba 23 s; Meta no recibía respuesta a
tiempo, reenviaba el webhook y cada reenvío ocupaba otro worker al 100 %.

Aquí el archivo se baja directo, sin esa revisión. La consulta de la liga (que
sí es JSON) sigue por el camino nativo.

Al MANDAR: WhatsApp solo acepta video MP4 (H.264, ≤ 16 MB) y fotos JPEG/PNG
(≤ 5 MB). Los videos .MOV del iPhone (o pesados) se convierten con ``ffmpeg`` a
MP4 720p que quepa, y las fotos .HEIC/.WEBP a JPG. Requiere ``ffmpeg`` en el
servidor y ``pillow-heif`` en el entorno de Python (para HEIC).
""",
    "category": "Productivity/WhatsApp",
    "author": "XUBAX",
    "website": "https://www.xubax.com",
    "license": "OPL-1",
    "depends": ["whatsapp"],
    "external_dependencies": {"bin": ["ffmpeg", "ffprobe"]},
    "installable": True,
    "application": False,
}
