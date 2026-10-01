# anello.mx — rediseño estilo Blue Nile (website 1, BD novadiam-anello-diamane-xubax)

No es un módulo: son las vistas, el CSS y las imágenes que `aplicar.py` escribe en la BD
(vistas 4417 encabezado, 6542 pie, 6545 portada, 6546 Nosotros, 6543 Contacto, más
`anbn.*` para la tienda/ficha y las páginas `/icert` y `/grabado-laser`).

## Publicar
```
sudo cp -r anello_site/. /opt/odoo/anbn_tmp/ && sudo chown -R odoo /opt/odoo/anbn_tmp
cat anello_site/aplicar.py | sudo -u odoo /odoo/odoo-server/env/bin/python3 /odoo/odoo-server/odoo-bin \
    shell -c /etc/odoo-server.conf -d <BD> --no-http --log-level=warn
sudo systemctl restart odoo-server
```
- Idempotente. La 1.ª vez guarda respaldos en `/opt/odoo/anbn_tmp/respaldo_*` (no borrar esa carpeta).
- Escribe el arch en `en_US` **y** `es_MX` (el que pinta es `es_MX`).
- Crea las 2 citas nativas (presencial y virtual) y reescribe los `/contacto#cita` a `/appointment`.
- Probar siempre antes en `testanello`.

## WhatsApp
`configurar_wa.py` configura la cuenta 2 (Anello): aviso fuera de horario 8-21 (`xb_whatsapp_autoreply`),
prospectos desde el sitio/anuncios y la plantilla de carrito abandonado (`xb_whatsapp_web_leads`).
Solo en producción manda la plantilla a revisión de Meta. Requiere el módulo `xb_whatsapp_web_leads` instalado.
