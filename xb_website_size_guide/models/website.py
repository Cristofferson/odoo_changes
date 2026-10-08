# -*- coding: utf-8 -*-
from odoo import fields, models

# Attribute names that are a ring size (compared in lower case).
SIZE_ATTRIBUTES = ("medida", "talla", "size", "ring size")


class Website(models.Model):
    _inherit = "website"

    xb_size_guide_url = fields.Char(
        string="Size guide",
        help="Page of this website that explains how to find the ring size. When set, the "
             "product page shows a link to it next to the size option.")

    def _xb_is_size_attribute(self, attribute):
        return (attribute.with_context(lang="en_US").name or "").strip().lower() in SIZE_ATTRIBUTES \
            or (attribute.name or "").strip().lower() in SIZE_ATTRIBUTES


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    xb_size_guide_url = fields.Char(related="website_id.xb_size_guide_url", readonly=False)
