# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    xb_sa_backup_notified = fields.Boolean("Respaldo de ventas avisado", copy=False)
    xb_sa_paused_channel_ids = fields.Many2many(
        "discuss.channel", compute="_compute_xb_sa_paused_channel_ids",
        string="Pláticas de WhatsApp atendidas por una persona")

    def _compute_xb_sa_paused_channel_ids(self):
        canales = self.env["discuss.channel"].sudo().search([
            ("xb_sa_lead_id", "in", self.ids), ("xb_sa_is_paused", "=", True)])
        for lead in self:
            lead.xb_sa_paused_channel_ids = canales.filtered(lambda c: c.xb_sa_lead_id == lead)

    def action_xb_sa_resume(self):
        self.xb_sa_paused_channel_ids.action_xb_sa_resume()
        return True
