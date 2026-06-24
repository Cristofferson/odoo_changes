# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_xibo_showcase_enabled = fields.Boolean(related='pos_config_id.xibo_showcase_enabled', readonly=False)
    pos_xibo_showcase_url = fields.Char(related='pos_config_id.xibo_showcase_url', readonly=False)
    pos_xibo_showcase_category_id = fields.Many2one(related='pos_config_id.xibo_showcase_category_id', readonly=False)
    pos_xibo_showcase_count = fields.Integer(related='pos_config_id.xibo_showcase_count', readonly=False)
    pos_xibo_showcase_interval = fields.Integer(related='pos_config_id.xibo_showcase_interval', readonly=False)
    pos_xibo_showcase_heading = fields.Char(related='pos_config_id.xibo_showcase_heading', readonly=False)
    pos_xibo_showcase_order = fields.Selection(related='pos_config_id.xibo_showcase_order', readonly=False)
    pos_xibo_showcase_widget_url = fields.Char(related='pos_config_id.xibo_showcase_widget_url', readonly=True)
