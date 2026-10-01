# -*- coding: utf-8 -*-
from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    xb_wa_leads_enabled = fields.Boolean('Crear prospectos desde WhatsApp')
    xb_wa_lead_user_id = fields.Many2one('res.users', 'Responsable de los prospectos')
    xb_wa_lead_tag_web_id = fields.Many2one('crm.tag', 'Etiqueta: desde el sitio')
    xb_wa_lead_tag_ad_id = fields.Many2one('crm.tag', 'Etiqueta: desde anuncio')
    xb_wa_cart_enabled = fields.Boolean('Avisar carritos abandonados por WhatsApp')
    xb_wa_cart_template_id = fields.Many2one(
        'whatsapp.template', 'Plantilla de carrito abandonado',
        domain="[('model', '=', 'sale.order'), ('status', '=', 'approved')]")
    xb_wa_cart_delay_hours = fields.Integer('Horas sin moverse antes de avisar', default=3)
