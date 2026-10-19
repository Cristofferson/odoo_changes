# -*- coding: utf-8 -*-
from odoo import http
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_sale.controllers.main import WebsiteSale


class GemaWebsiteSale(WebsiteSale):

    def _get_shop_domain(self, search, category, attribute_value_dict, search_in_description=True):
        """«Joyería» (/shop sin categoría ni búsqueda) no muestra diamantes:
        se ven en su menú «Diamantes» y en el buscador."""
        domain = super()._get_shop_domain(search, category, attribute_value_dict, search_in_description)
        if not category and not search:
            diamantes = request.env.ref("xb_gema_ficha_web.categ_diamantes", raise_if_not_found=False)
            if diamantes:
                domain = Domain.AND([domain, Domain("public_categ_ids", "not in", diamantes.ids)])
        return domain


class GemaFichaWeb(http.Controller):

    @http.route("/xb_gema_ficha_web/video/<int:template_id>", type="http",
                auth="public", website=True, sitemap=False)
    def gema_video(self, template_id, **kw):
        """Video de la gema. /web/content no sirve: muchos videos se subieron
        como application/octet-stream y el navegador no los reproduce, y las
        gemas sin publicar se las niega a quien navega la tienda con sesión
        de portal. Stream de Odoo para que soporte Range (adelantar/reanudar)."""
        template = request.env["product.template"].sudo().browse(template_id).exists()
        if (not template or "x_studio_video" not in template._fields
                or not (template.is_published or request.env.user._is_internal())
                or not template.with_context(bin_size=True).x_studio_video):
            return request.not_found()
        stream = request.env["ir.binary"]._get_stream_from(
            template, "x_studio_video",
            filename="gema-%s.mp4" % (template.x_studio_id_gema or template.id),
            mimetype="video/mp4")
        return stream.get_response()
