import logging
from urllib.parse import quote

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

GEM_FIELD = "x_studio_id_gema"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    xb_gema_folder_done = fields.Boolean("Gem folder created", copy=False)

    def _xb_gema_wanted(self):
        """Gems created by a person: flagged category, serial, no ID yet.

        Products created by the system (accent stones made by scripts) are
        left alone.
        """
        if GEM_FIELD not in self._fields or self.env.su:
            return self.browse()
        return self.filtered(
            lambda t: t.categ_id.xb_gema_id and t.tracking == "serial" and not t[GEM_FIELD]
        )

    def _xb_gema_assign(self):
        gems = self._xb_gema_wanted()
        if not gems:
            return
        Sequence = self.env["ir.sequence"].sudo()
        Template = self.sudo().with_context(active_test=False)
        for gem in gems:
            # Skip numbers already typed by hand on another gem.
            while True:
                code = Sequence.next_by_code("xb_gema_id.gem")
                if not code or not Template.search_count([(GEM_FIELD, "=", code)], limit=1):
                    break
            if code:
                gem.sudo().write({GEM_FIELD: code, "xb_gema_folder_done": False})
        gems.sudo()._xb_gema_make_folders()

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._xb_gema_assign()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if "categ_id" in vals or "tracking" in vals:
            self._xb_gema_assign()
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if GEM_FIELD in self._fields and not (default or {}).get(GEM_FIELD):
            for template, vals in zip(self, vals_list):
                if template.categ_id.xb_gema_id:
                    vals[GEM_FIELD] = False
        return vals_list

    # Cloud folder ---------------------------------------------------------

    def _xb_gema_make_folders(self):
        """Create the folder of each gem. Never blocks saving the gem."""
        params = self.env["ir.config_parameter"].sudo()
        url = (params.get_param("xb_gema_id.webdav_url") or "").rstrip("/")
        user = params.get_param("xb_gema_id.webdav_user")
        password = params.get_param("xb_gema_id.webdav_password")
        if not (url and user and password):
            return
        for gem in self.filtered(lambda t: t[GEM_FIELD] and not t.xb_gema_folder_done):
            name = gem[GEM_FIELD].strip().replace("/", "-")
            try:
                response = requests.request(
                    "MKCOL", "%s/%s" % (url, quote(name)), auth=(user, password), timeout=10,
                )
            except requests.RequestException as error:
                _logger.warning("Gem %s: folder not created: %s", name, error)
                continue
            # 201 = created, 405 = it already exists.
            if response.status_code in (201, 405):
                gem.xb_gema_folder_done = True
            else:
                _logger.warning("Gem %s: folder not created (HTTP %s)", name, response.status_code)

    @api.model
    def _cron_xb_gema_folders(self):
        self.sudo().with_context(active_test=False).search([
            ("categ_id.xb_gema_id", "=", True),
            ("xb_gema_folder_done", "=", False),
            (GEM_FIELD, "!=", False),
            ("create_date", ">=", fields.Datetime.subtract(fields.Datetime.now(), days=30)),
        ])._xb_gema_make_folders()
