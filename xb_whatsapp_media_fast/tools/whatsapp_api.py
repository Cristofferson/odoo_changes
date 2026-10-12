# -*- coding: utf-8 -*-
"""Descarga directa del archivo de un mensaje entrante.

El parche vive en la clase ``WhatsAppApi`` (no es un modelo), así que alcanza a
todas las bases que corre el mismo proceso: solo toma el camino rápido en las
bases que tienen ESTE módulo instalado; las demás siguen con el nativo.
"""
import logging

import requests

from odoo.addons.whatsapp.tools.whatsapp_api import WhatsAppApi
from odoo.addons.whatsapp.tools.whatsapp_exception import WhatsAppError

_logger = logging.getLogger(__name__)

MODULE = "xb_whatsapp_media_fast"
_nativo = WhatsAppApi._get_whatsapp_document


def _get_whatsapp_document(self, document_id):
    if MODULE not in self.wa_account_id.env.registry._init_modules:
        return _nativo(self, document_id)
    _logger.info("Get document url for document uid %s from account %s [%s]",
                 document_id, self.wa_account_id.name, self.wa_account_id.id)
    # La liga sí es JSON: camino nativo (revisa errores y la bitácora de depuración).
    file_url = self._WhatsAppApi__api_requests("GET", f"/{document_id}", auth_type="bearer").json().get("url")
    if not file_url:
        raise WhatsAppError(failure_type="unknown")
    self._check_allow_requests()
    try:
        res = requests.get(file_url, headers={"Authorization": f"Bearer {self.token}"}, timeout=(10, 60))
    except requests.exceptions.RequestException:
        raise WhatsAppError(failure_type="network")
    if not res.ok or res.headers.get("Content-Type", "").startswith("application/json"):
        _logger.warning("xb_whatsapp_media_fast: Meta no entregó el archivo %s (%s)", document_id, res.status_code)
        raise WhatsAppError(failure_type="network")
    _logger.info("Get document from url for account %s [%s]: %s bytes",
                 self.wa_account_id.name, self.wa_account_id.id, len(res.content))
    return res.content


WhatsAppApi._get_whatsapp_document = _get_whatsapp_document
