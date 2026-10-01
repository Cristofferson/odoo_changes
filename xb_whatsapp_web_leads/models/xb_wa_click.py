# -*- coding: utf-8 -*-
from odoo import fields, models


class XbWaClick(models.Model):
    _name = 'xb.wa.click'
    _description = 'Clic al botón de WhatsApp del sitio'
    _order = 'id desc'

    create_date = fields.Datetime('Fecha', readonly=True)
    website_id = fields.Many2one('website', 'Sitio web', index=True)
    path = fields.Char('Página')
    product_tmpl_id = fields.Many2one('product.template', 'Producto', index=True)
    kind = fields.Selection([('float', 'Botón flotante'), ('product', 'Botón de la ficha')], 'Botón', default='float')
