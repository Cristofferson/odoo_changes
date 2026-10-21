# -*- coding: utf-8 -*-
"""Public, token-protected catalogue feed for Meta Commerce Manager."""
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.tools import consteq


class XbMetaCatalog(http.Controller):

    @http.route(
        "/anello/catalogo/<string:token>/feed.xml",
        type="http", auth="public", csrf=False, sitemap=False,
    )
    def catalog_feed(self, token, **kw):
        """Serve the product feed.

        The secret lives in the path (same pattern already adopted for the MCP
        bridges). ``consteq`` avoids leaking the token through timing, and a
        wrong token returns 404 rather than 403 so the route is not
        discoverable by probing.
        """
        Product = request.env["product.template"].sudo()
        expected = Product._xb_meta_param("token", "")
        if not expected or not consteq(str(token), str(expected)):
            raise NotFound()

        xml = Product._xb_meta_catalog_xml()
        return request.make_response(xml, [
            ("Content-Type", "application/xml; charset=utf-8"),
            ("Cache-Control", "public, max-age=3600"),
        ])
