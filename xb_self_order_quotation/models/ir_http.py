# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        # The kiosk is a frontend page: its texts come from this module's .po.
        return super()._get_translation_frontend_modules_name() + ["xb_self_order_quotation"]
