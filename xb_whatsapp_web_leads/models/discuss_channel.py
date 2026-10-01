# -*- coding: utf-8 -*-
"""Prospecto en CRM para las conversaciones que vienen del sitio o de un anuncio.

Se engancha igual que xb_whatsapp_autoreply: en _notify_thread, solo con
``whatsapp_inbound_msg_uid`` (mensaje ENTRANTE), y dentro de try/except para
nunca romper la recepción.
"""
import logging
import re
from urllib.parse import urlparse

from markupsafe import Markup
from odoo import fields, models, tools

_logger = logging.getLogger(__name__)
SHOP_ID = re.compile(r'/shop/(?:[\w%-]*/)?[\w%-]*?-?(\d+)(?:[/?#]|$)')


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    xb_wa_source_lead_id = fields.Many2one('crm.lead', 'Prospecto (sitio/anuncio)', copy=False)

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        res = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        if kwargs.get('whatsapp_inbound_msg_uid'):
            for channel in self.filtered(lambda c: c.channel_type == 'whatsapp'):
                try:
                    channel._xb_wa_source_lead(message, None)   # anuncios: los procesa whatsapp.account
                except Exception:  # noqa: BLE001
                    _logger.exception('xb_whatsapp_web_leads: fallo en el canal %s', channel.id)
        return res

    def _xb_wa_source_lead(self, message, referral):
        self.ensure_one()
        text = tools.html2plaintext(message.body or '')
        websites = self.env['website'].sudo().search([('xb_wa_leads_enabled', '=', True)])
        website = origin = product = False
        detail = ''
        for ws in websites:
            host = urlparse(ws.domain or '').netloc.replace('www.', '')
            if host and host in text:
                website, origin = ws, 'web'
                m = SHOP_ID.search(text.split(host, 1)[1])
                if m:
                    product = self.env['product.template'].sudo().browse(int(m.group(1))).exists()
                break
        if referral:
            origin = 'ad'
            if not website:
                comps = self.wa_account_id.allowed_company_ids if 'allowed_company_ids' in self.wa_account_id._fields else self.env['res.company']
                website = websites.filtered(lambda w: w.company_id in comps)[:1] or websites[:1]
            detail = ' · '.join(filter(None, [referral.get('headline'), referral.get('source_type'),
                                              referral.get('source_url')]))
        if not origin or not website:
            return
        partner = self.whatsapp_partner_id
        lead = self.xb_wa_source_lead_id
        if not lead and partner:
            # solo se reutiliza un prospecto que también vino de WhatsApp (sitio/anuncio), abierto
            lead = self.env['crm.lead'].sudo().search([('partner_id', '=', partner.id), ('active', '=', True),
                                                       ('medium_id.name', '=', 'WhatsApp'),
                                                       ('date_closed', '=', False)], order='id desc', limit=1)
        nota = Markup('<p>Escribió por WhatsApp desde {}:</p><blockquote>{}</blockquote>').format(
            'un anuncio de Meta' + (' (%s)' % detail if detail else '') if origin == 'ad' else website.domain,
            text[:300])
        if lead:
            lead.message_post(body=nota, message_type='comment', subtype_xmlid='mail.mt_note',
                              author_id=self.env.ref('base.partner_root').id)
        else:
            utm = self.env['utm.medium'].sudo()
            medium = utm.search([('name', '=', 'WhatsApp')], limit=1) or utm.create({'name': 'WhatsApp'})
            src_name = 'Anuncio Meta' if origin == 'ad' else urlparse(website.domain).netloc
            source = self.env['utm.source'].sudo().search([('name', '=', src_name)], limit=1) \
                or self.env['utm.source'].sudo().create({'name': src_name})
            tag = website.xb_wa_lead_tag_ad_id if origin == 'ad' else website.xb_wa_lead_tag_web_id
            name = '%s — %s — %s' % ('Anuncio WhatsApp' if origin == 'ad' else 'Sitio web',
                                     product.name if product else (referral or {}).get('headline') or 'Consulta',
                                     partner.name or self.whatsapp_number)
            lead = self.env['crm.lead'].sudo().with_company(website.company_id).create({
                'name': name[:200], 'type': 'opportunity',
                'partner_id': partner.id or False, 'phone': self.whatsapp_number,
                'company_id': website.company_id.id,
                'user_id': website.xb_wa_lead_user_id.id or False,
                'tag_ids': [(4, tag.id)] if tag else False,
                'medium_id': medium.id, 'source_id': source.id,
                'description': text[:1000],
            })
            lead.message_post(body=nota, message_type='comment', subtype_xmlid='mail.mt_note',
                              author_id=self.env.ref('base.partner_root').id)
            _logger.info('xb_whatsapp_web_leads: prospecto %s (%s) desde el canal %s', lead.id, origin, self.id)
        if product and 'xb_wa_product_ids' in lead._fields:
            lead.xb_wa_product_ids = [(4, product.id)]
        self.sudo().xb_wa_source_lead_id = lead
