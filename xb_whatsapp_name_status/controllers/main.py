# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.whatsapp.controller.main import Webhook

_logger = logging.getLogger(__name__)


class XbNameStatusWebhook(Webhook):

    @http.route('/whatsapp/webhook/', methods=['POST'], type="jsonrpc", auth="public")
    def webhookpost(self):
        # El nativo valida la firma (si no, lanza Forbidden) y procesa lo suyo; después,
        # lo que ignora: la decisión de Meta sobre el nombre visible.
        res = super().webhookpost()
        try:
            data = json.loads(request.httprequest.data)
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('field') == 'phone_number_name_update':
                        request.env['whatsapp.account'].sudo()._xb_name_update(entry.get('id'), change.get('value') or {})
        except Exception:  # noqa: BLE001 - nunca romper la recepción de mensajes
            _logger.exception("xb_whatsapp_name_status: no se pudo procesar el aviso del nombre")
        return res
