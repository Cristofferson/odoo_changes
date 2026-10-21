# -*- coding: utf-8 -*-
from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    xb_b2b_category_id = fields.Many2one(
        "res.partner.category", string="Tienda solo para contactos con la etiqueta",
        help="Si se llena, la tienda solo se abre a usuarios internos y a contactos (o su empresa) con esta etiqueta.")
    xb_b2b_denied_url = fields.Char(
        "A dónde mandar a quien no está verificado", default="/contactus",
        help="Liga a la que se manda a un usuario con sesión que todavía no tiene la etiqueta (p. ej. el WhatsApp de la tienda).")

    def _xb_b2b_blocked(self):
        """¿El usuario con sesión no puede entrar a la tienda por no estar verificado?"""
        self.ensure_one()
        user = self.env.user
        if not self.xb_b2b_category_id or user._is_public() or user._is_internal():
            return False
        partner = user.partner_id.sudo()
        return not (self.xb_b2b_category_id & (partner.category_id | partner.commercial_partner_id.category_id))

    def has_ecommerce_access(self):
        return super().has_ecommerce_access() and not self._xb_b2b_blocked()
