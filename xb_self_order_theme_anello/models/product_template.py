# -*- coding: utf-8 -*-
from odoo import models

# Every playable copy of the video, best first (webm plays where H.264 is missing).
VIDEO_ORDER = ("video/webm", "video/mp4")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _load_pos_self_data_read(self, data, config):
        """Each product carries its gallery for the kiosk's product page: the extra photos
        and the published video (the same ones the website and the showroom wall use)."""
        res = super()._load_pos_self_data_read(data, config)
        ids = [r["id"] for r in res]
        if not ids:
            return res
        fotos = {}
        for img in self.env["product.image"].sudo().search(
            [("product_tmpl_id", "in", ids)], order="sequence, id"
        ):
            fotos.setdefault(img.product_tmpl_id.id, []).append(
                "/web/image/product.image/%s/image_1024" % img.id
            )
        videos = {}
        for att in self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "product.template"), ("res_id", "in", ids),
            ("mimetype", "in", VIDEO_ORDER), ("public", "=", True), ("res_field", "=", False),
        ], order="id desc"):
            fuentes = videos.setdefault(att.res_id, {})
            fuentes.setdefault(att.mimetype, "/web/content/%s" % att.id)
        for r in res:
            v = videos.get(r["id"], {})
            r["_xb_media"] = {
                "fotos": fotos.get(r["id"], []),
                "video": [{"url": v[m], "type": m} for m in VIDEO_ORDER if m in v],
            }
        return res
