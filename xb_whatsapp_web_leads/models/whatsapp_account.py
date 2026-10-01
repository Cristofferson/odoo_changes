# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class WhatsappAccount(models.Model):
    _inherit = 'whatsapp.account'

    def _process_messages(self, value):
        """Los mensajes de un anuncio Click-to-WhatsApp traen ``referral`` (titular, liga,
        tipo). El módulo nativo lo ignora; aquí, una vez publicado el mensaje, se usa
        para crear el prospecto con el origen «anuncio»."""
        res = super()._process_messages(value)
        data = value.get('whatsapp_business_api_data', value) if isinstance(value, dict) else {}
        if not data.get('messages') and isinstance(value, dict) and value.get('messages'):
            data = value
        for m in data.get('messages', []):
            ref = m.get('referral')
            if not ref:
                continue
            try:
                wa_msg = self.env['mail.message'].sudo().search([('model', '=', 'discuss.channel'),
                                                                  ('wa_message_ids.msg_uid', '=', m.get('id'))], limit=1)
                channel = self.env['discuss.channel'].sudo().browse(wa_msg.res_id) if wa_msg else \
                    self._find_active_channel(m.get('from'), create_if_not_found=False)
                if channel and wa_msg:
                    channel._xb_wa_source_lead(wa_msg, ref)
            except Exception:  # noqa: BLE001
                _logger.exception('xb_whatsapp_web_leads: no se pudo registrar el anuncio del mensaje %s', m.get('id'))
        return res
