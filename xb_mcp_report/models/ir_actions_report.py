import base64

from odoo import api, models
from odoo.exceptions import UserError

# tope duro del PDF resultante; el bridge aplica además su propio límite
MAX_RENDER_BYTES = 8 * 1024 * 1024


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def mcp_render_pdf(self, report_ref, res_ids=None, data=None):
        """Renderiza un reporte QWeb-PDF y lo regresa en base64.

        Público (sin guion bajo) a propósito: es el punto de entrada RPC del
        bridge MCP, que conecta como un usuario real. La seguridad es la del
        propio usuario: se valida acceso de lectura a los registros destino
        antes de renderizar.
        """
        report = self._get_report(report_ref)
        res_ids = [int(i) for i in (res_ids or [])]
        if report.report_type not in ('qweb-pdf', 'qweb-text'):
            raise UserError(
                'El reporte %s es de tipo %s; solo se soporta qweb-pdf.'
                % (report_ref, report.report_type))
        if report.model and res_ids:
            self.env[report.model].browse(res_ids).check_access('read')
        pdf, _rtype = self._render_qweb_pdf(
            report_ref, res_ids or None, data=dict(data) if data else None)
        if len(pdf) > MAX_RENDER_BYTES:
            raise UserError(
                'El PDF resultante excede el límite (%d > %d bytes).'
                % (len(pdf), MAX_RENDER_BYTES))
        return {
            'report_ref': report_ref,
            'report_name': report.name,
            'model': report.model or False,
            'res_ids': res_ids,
            'filename': '%s.pdf' % (report.name or report_ref).replace('/', '-'),
            'mimetype': 'application/pdf',
            'size': len(pdf),
            'content_base64': base64.b64encode(pdf).decode('ascii'),
        }
