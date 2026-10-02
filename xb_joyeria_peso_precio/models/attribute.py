# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.http import request


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    xb_ocultar_web = fields.Boolean(
        'Ocultar en el sitio web',
        help='No se muestra ni se puede elegir en la tienda en línea. '
             'Sigue disponible en la caja, Ventas y el backend.')


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    def _only_active(self):
        res = super()._only_active()
        # Solo en la tienda en línea (petición de frontend): la caja y el backend no pasan por aquí.
        if request and getattr(request, 'is_frontend', False):
            res = res.filtered(lambda v: not v.product_attribute_value_id.xb_ocultar_web)
        return res
