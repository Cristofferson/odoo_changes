# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.http import request


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    xb_ocultar_web = fields.Boolean(
        'Ocultar en el sitio web',
        help='No se muestra ni se puede elegir en la tienda en línea. '
             'Sigue disponible en la caja, Ventas y el backend.')
    xb_aleacion_id = fields.Many2one(
        'product.product', 'Aleación que se consume',
        help='Para el atributo Metal: el producto (en gramos) que la orden de fabricación descuenta del '
             'inventario, por el peso proyectado de la pieza. Puede ser una aleación con su propia lista de '
             'materiales (metal fino + liga) o el metal fino directamente.')


    def _xb_para_filtro(self, category=None):
        """Valores que vale la pena ofrecer en el filtro de la tienda: no ocultos en la web y
        usados (activos) por al menos un producto publicado DE LA CATEGORÍA que se está viendo
        (con sus subcategorías). Sin categoría, cualquier producto publicado."""
        visibles = self.filtered(lambda v: not v.xb_ocultar_web)
        if not visibles:
            return visibles
        sql = """
            SELECT DISTINCT v.product_attribute_value_id
              FROM product_template_attribute_value v
              JOIN product_template t ON t.id = v.product_tmpl_id
             WHERE v.ptav_active AND t.active AND t.is_published
               AND v.product_attribute_value_id = ANY(%s)"""
        params = [visibles.ids]
        if category:
            categs = self.env['product.public.category'].sudo().search([('id', 'child_of', category.id)])
            sql += """
               AND t.id IN (SELECT product_template_id FROM product_public_category_product_template_rel
                             WHERE product_public_category_id = ANY(%s))"""
            params.append(categs.ids)
        self.env.cr.execute(sql, params)
        usados = {r[0] for r in self.env.cr.fetchall()}
        return visibles.filtered(lambda v: v.id in usados)


class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'

    xb_secuencia = fields.Integer(related='product_attribute_value_id.sequence', string='Orden del valor')

    def _load_pos_data_fields(self, config):
        res = super()._load_pos_data_fields(config)
        if res and 'xb_secuencia' not in res:
            res.append('xb_secuencia')
        return res

    def _only_active(self):
        res = super()._only_active()
        # Solo en la tienda en línea (petición de frontend): la caja y el backend no pasan por aquí.
        if request and getattr(request, 'is_frontend', False):
            res = res.filtered(lambda v: not v.product_attribute_value_id.xb_ocultar_web)
        return res
