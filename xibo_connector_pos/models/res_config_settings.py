# -*- coding: utf-8 -*-
from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_xibo_server_id = fields.Many2one(related='pos_config_id.xibo_server_id', readonly=False)
    pos_xibo_time_from = fields.Float(related='pos_config_id.xibo_time_from', readonly=False)
    pos_xibo_time_to = fields.Float(related='pos_config_id.xibo_time_to', readonly=False)
    pos_xibo_display_ids = fields.Many2many(related='pos_config_id.xibo_display_ids', readonly=False)
    pos_xibo_display_group_ids = fields.Many2many(related='pos_config_id.xibo_display_group_ids', readonly=False)

    # ① AI Thank-You
    pos_xibo_thanks_enabled = fields.Boolean(related='pos_config_id.xibo_thanks_enabled', readonly=False)
    pos_xibo_thanks_layout_id = fields.Many2one(related='pos_config_id.xibo_thanks_layout_id', readonly=False)
    pos_xibo_thanks_dataset_id = fields.Many2one(related='pos_config_id.xibo_thanks_dataset_id', readonly=False)
    pos_xibo_thanks_duration = fields.Integer(related='pos_config_id.xibo_thanks_duration', readonly=False)
    pos_xibo_thanks_min_amount = fields.Float(related='pos_config_id.xibo_thanks_min_amount', readonly=False)
    pos_xibo_thanks_use_ai = fields.Boolean(related='pos_config_id.xibo_thanks_use_ai', readonly=False)
    pos_xibo_thanks_ai_agent_id = fields.Many2one(related='pos_config_id.xibo_thanks_ai_agent_id', readonly=False)
    pos_xibo_thanks_ai_prompt = fields.Text(related='pos_config_id.xibo_thanks_ai_prompt', readonly=False)
    pos_xibo_thanks_fallback_text = fields.Char(related='pos_config_id.xibo_thanks_fallback_text', readonly=False)
    pos_xibo_thanks_display_ids = fields.Many2many(related='pos_config_id.xibo_thanks_display_ids', readonly=False)
    pos_xibo_thanks_preset = fields.Selection(related='pos_config_id.xibo_thanks_preset', readonly=False)
    pos_xibo_thanks_custom_html = fields.Html(related='pos_config_id.xibo_thanks_custom_html', readonly=False, sanitize=False)
    pos_xibo_thanks_show_product_image = fields.Boolean(related='pos_config_id.xibo_thanks_show_product_image', readonly=False)
    pos_xibo_thanks_url = fields.Char(related='pos_config_id.xibo_thanks_url', readonly=True)
    pos_xibo_thanks_require_token = fields.Boolean(related='pos_config_id.xibo_thanks_require_token', readonly=False)

    # ④ Thank-You Audio (since v19.0.1.5.31)
    pos_xibo_thanks_audio_enabled = fields.Boolean(related='pos_config_id.xibo_thanks_audio_enabled', readonly=False)
    pos_xibo_thanks_audio_preset = fields.Selection(related='pos_config_id.xibo_thanks_audio_preset', readonly=False)
    pos_xibo_thanks_audio_custom_url = fields.Char(related='pos_config_id.xibo_thanks_audio_custom_url', readonly=False)
    pos_xibo_thanks_audio_volume = fields.Integer(related='pos_config_id.xibo_thanks_audio_volume', readonly=False)

    # ③ Customer Display Mirror (dynamic)
    pos_xibo_customer_display_enabled = fields.Boolean(related='pos_config_id.xibo_customer_display_enabled', readonly=False)
    pos_xibo_customer_display_display_id = fields.Many2one(related='pos_config_id.xibo_customer_display_display_id', readonly=False)
    pos_xibo_customer_display_url = fields.Char(related='pos_config_id.xibo_customer_display_url', readonly=True)
    pos_xibo_customer_display_layout_id = fields.Many2one(related='pos_config_id.xibo_customer_display_layout_id', readonly=True)
    pos_xibo_customer_display_duration = fields.Integer(related='pos_config_id.xibo_customer_display_duration', readonly=False)

    # ④ Recommendations
    pos_xibo_reco_enabled = fields.Boolean(related='pos_config_id.xibo_reco_enabled', readonly=False)
    pos_xibo_reco_duration = fields.Integer(related='pos_config_id.xibo_reco_duration', readonly=False)
    pos_xibo_reco_mode = fields.Selection(related='pos_config_id.xibo_reco_mode', readonly=False)
    pos_xibo_reco_priority = fields.Selection(related='pos_config_id.xibo_reco_priority', readonly=False)
    pos_xibo_reco_cooldown = fields.Integer(related='pos_config_id.xibo_reco_cooldown', readonly=False)
