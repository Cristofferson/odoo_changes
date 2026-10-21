# -*- coding: utf-8 -*-
"""Build the Meta/GMC catalogue items, one row per product MODEL."""
import html
import re

from odoo import api, models

PARAM_PREFIX = "xb_meta_catalog."


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _xb_meta_param(self, key, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(
            PARAM_PREFIX + key, default)

    @api.model
    def _xb_meta_catalog_domain(self):
        website_id = int(self._xb_meta_param("website_id", 1) or 1)
        website = self.env["website"].sudo().browse(website_id)
        return [
            ("is_published", "=", True),
            ("website_id", "in", (False, website.id)),
        ]

    def _xb_meta_image_ok(self, min_px):
        """True if the picture is big enough for Meta commerce.

        Meta rejects catalogue images under 500x500. Sending them anyway just
        fills the catalogue's "Issues" tab, so they are filtered out here and
        reported separately (see ``_xb_meta_catalog_report``).

        PIL only reads the header to answer ``.size``, so this stays cheap
        even over the whole catalogue.
        """
        self.ensure_one()
        # Se lee SOLO la foto de este producto: con ``self.image_1920`` el ORM
        # trae de golpe las fotos de todo el catálogo (prefetch) y el worker se
        # queda sin memoria (MemoryError → Meta recibía error 500 desde el 19-oct).
        att = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "product.template"), ("res_field", "=", "image_1920"),
            ("res_id", "=", self.id)], limit=1)
        if not att:
            return False
        try:
            import io

            from PIL import Image
            with Image.open(io.BytesIO(att.raw)) as im:
                return min(im.size) >= min_px
        except Exception:  # noqa: BLE001 - unreadable image = not shippable
            return False
        finally:
            att.invalidate_recordset(["raw", "datas"])

    @api.model
    def _xb_meta_catalog_products(self):
        """Published models that are safe to publish as a catalogue item."""
        try:
            floor = float(self._xb_meta_param("min_price", 1) or 1)
        except (TypeError, ValueError):
            floor = 1.0
        try:
            min_px = int(self._xb_meta_param("min_image_px", 500) or 500)
        except (TypeError, ValueError):
            min_px = 500
        products = self.sudo().search(self._xb_meta_catalog_domain())
        # The price floor is the whole point: 63 products sat published at
        # $0/$1 and were buyable on anello.mx. A catalogue entry is an offer,
        # so anything at or below the floor never leaves the building.
        return products.filtered(
            lambda p: p.list_price > floor and p._xb_meta_image_ok(min_px))

    @api.model
    def _xb_meta_catalog_report(self):
        """Which published models are NOT making it into the feed, and why.

        Silent exclusions read as "everything is covered" when it isn't, so
        this is what to check before blaming the catalogue.
        """
        try:
            floor = float(self._xb_meta_param("min_price", 1) or 1)
        except (TypeError, ValueError):
            floor = 1.0
        try:
            min_px = int(self._xb_meta_param("min_image_px", 500) or 500)
        except (TypeError, ValueError):
            min_px = 500
        out = {"precio": [], "sin_foto": [], "foto_chica": []}
        for p in self.sudo().search(self._xb_meta_catalog_domain()):
            if p.list_price <= floor:
                out["precio"].append((p.id, p.name, p.list_price))
            elif not self.env["ir.attachment"].sudo().search_count([
                    ("res_model", "=", "product.template"), ("res_field", "=", "image_1920"),
                    ("res_id", "=", p.id)]):
                out["sin_foto"].append((p.id, p.name))
            elif not p._xb_meta_image_ok(min_px):
                out["foto_chica"].append((p.id, p.name))
        return out

    def _xb_meta_item_vals(self, base_url, brand):
        """One GMC item per model."""
        self.ensure_one()
        raw_desc = self.description_sale or self.website_meta_description or ""
        desc = re.sub(r"<[^>]+>", " ", raw_desc)
        desc = re.sub(r"\s+", " ", desc).strip() or self.name
        url = self.website_url or "/shop"
        return {
            "id": str(self.id),
            "title": (self.name or "")[:200],
            "description": desc[:9000],
            "link": "%s%s" % (base_url, url),
            "image_link": "%s/web/image/product.template/%s/image_1920" % (
                base_url, self.id),
            "availability": "in stock",
            "condition": "new",
            # Rounded on purpose: the DB holds values like 8704.567386 and
            # Meta rejects prices with more than 2 decimals.
            "price": "%.2f %s" % (
                self.list_price, self.currency_id.name or "MXN"),
            "brand": brand,
        }

    @api.model
    def _xb_meta_catalog_xml(self):
        """Render the GMC-format XML feed accepted by Commerce Manager."""
        website_id = int(self._xb_meta_param("website_id", 1) or 1)
        website = self.env["website"].sudo().browse(website_id)
        base_url = (website.domain or "").rstrip("/") or \
            self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        base_url = base_url.rstrip("/")
        brand = self._xb_meta_param("brand", "Anello") or "Anello"

        rows = []
        for product in self._xb_meta_catalog_products():
            vals = product._xb_meta_item_vals(base_url, brand)
            fields_xml = "".join(
                "<g:%s>%s</g:%s>" % (k, html.escape(str(v)), k)
                for k, v in vals.items()
            )
            rows.append("<item>%s</item>" % fields_xml)

        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n'
            '<channel>\n'
            '<title>%s</title>\n'
            '<link>%s</link>\n'
            '<description>Catálogo de %s</description>\n'
            '%s\n'
            '</channel>\n</rss>\n'
        ) % (html.escape(brand), html.escape(base_url),
             html.escape(brand), "\n".join(rows))
