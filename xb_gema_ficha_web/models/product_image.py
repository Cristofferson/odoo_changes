# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models


class ProductImage(models.Model):
    _inherit = "product.image"

    # Campo de la gema que esta foto refleja; vacío = foto puesta a mano.
    xb_gema_field = fields.Char(readonly=True, copy=False)

    @api.depends("video_url", "xb_gema_field")
    def _compute_embed_code(self):
        super()._compute_embed_code()
        for image in self.filtered(lambda i: i.xb_gema_field == "x_studio_video"):
            image.embed_code = Markup(
                '<video class="w-100 h-100 bg-black" controls="controls" '
                'preload="metadata" playsinline="playsinline" '
                'poster="/web/image/product.image/%d/image_1024" '
                'src="/xb_gema_ficha_web/video/%d"></video>') % (image.id, image.product_tmpl_id.id)
