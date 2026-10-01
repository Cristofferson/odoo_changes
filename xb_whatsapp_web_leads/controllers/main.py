# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class XbWhatsappWebClick(http.Controller):

    @http.route('/xb_wa/click', type='http', auth='public', methods=['POST'], csrf=False, website=True, sitemap=False)
    def click(self, path='', product_tmpl_id=None, kind='float', **kw):
        """Recibe el sendBeacon del botón de WhatsApp. Nunca falla hacia el visitante."""
        try:
            tmpl = int(product_tmpl_id) if product_tmpl_id and str(product_tmpl_id).isdigit() else False
            request.env['xb.wa.click'].sudo().create({
                'website_id': request.website.id,
                'path': (path or '')[:250],
                'product_tmpl_id': tmpl or False,
                'kind': kind if kind in ('float', 'product') else 'float',
            })
        except Exception:  # noqa: BLE001
            pass
        return request.make_response('', status=204)
