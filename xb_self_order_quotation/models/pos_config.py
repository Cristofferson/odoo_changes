# -*- coding: utf-8 -*-
from odoo import api, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    def _xb_kiosk_quotation_modes(self):
        """How this kiosk can hand over a quotation: printed and/or by WhatsApp."""
        self.ensure_one()
        config = self.sudo()
        if config.self_ordering_mode != "kiosk" or not config.xb_enable_sale_order:
            return {"print": False, "whatsapp": False}
        whatsapp = bool(self.env["pos.config"].sudo().search([
            ("company_id", "=", config.company_id.id),
            ("xb_quotation_wa_template_id.status", "=", "approved"),
        ], limit=1))
        return {
            "print": bool(config.other_devices and config.epson_printer_ip),
            "whatsapp": whatsapp,
        }

    @api.model
    def _load_pos_self_data_read(self, records, config):
        read_records = super()._load_pos_self_data_read(records, config)
        if read_records:
            read_records[0]["_xb_quotation"] = config._xb_kiosk_quotation_modes()
        return read_records
