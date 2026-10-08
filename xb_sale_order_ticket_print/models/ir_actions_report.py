# -*- coding: utf-8 -*-
import io

from PIL import Image

from odoo import models

# Paper width of a POS receipt printer, in millimetres.
XB_TICKET_PAPER_MM = 80
XB_TICKET_REPORT = "xb_sale_order_ticket_print.report_sale_order_ticket"


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """The "Ticket" print of a sale order is the very image the WhatsApp quotation
        is sent with, one PDF page per order, 80 mm wide and as tall as the ticket."""
        report = self._get_report(report_ref)
        if report.report_name != XB_TICKET_REPORT:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        orders = self.env["sale.order"].browse(res_ids)
        orders.check_access("read")
        pages = []
        for order in orders:
            image = Image.open(io.BytesIO(order._xb_quotation_image())).convert("RGB")
            pages.append(image)
        dpi = pages[0].width / (XB_TICKET_PAPER_MM / 25.4)
        stream = io.BytesIO()
        pages[0].save(stream, format="PDF", resolution=dpi, save_all=True, append_images=pages[1:])
        return stream.getvalue(), "pdf"
