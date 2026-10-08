# -*- coding: utf-8 -*-
import base64
import logging
import re

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class KioskQuotation(http.Controller):

    @staticmethod
    def _xb_digits(phone):
        """The customer's 10-digit Mexican mobile number, or ''."""
        digits = re.sub(r"\D", "", phone or "")
        if len(digits) == 12 and digits.startswith("52"):
            digits = digits[2:]
        if len(digits) == 13 and digits.startswith("521"):
            digits = digits[3:]
        return digits if len(digits) == 10 else ""

    def _xb_partner(self, env, name, digits):
        """The contact with this mobile number, created if there is none (without a
        company, as the POS creates its customers)."""
        Partner = env["res.partner"].sudo()
        partner = Partner.search([("phone_sanitized", "=", "+52" + digits)], limit=1)
        if not partner:
            partner = Partner.search([("phone", "ilike", "%%%s" % digits[-8:])], limit=1)
            if partner and self._xb_digits(partner.phone) != digits:
                partner = Partner.browse()
        if not partner:
            partner = Partner.create({
                "name": name,
                "phone": "+52 %s %s %s" % (digits[:3], digits[3:6], digits[6:]),
                "country_id": env.ref("base.mx").id,
            })
        return partner

    def _xb_line(self, env, config, pricelist, raw):
        """One quotation line from a kiosk cart line: the variant for the chosen
        options (created when the attribute is dynamic) and its price, the same one
        the kiosk showed."""
        template = env["product.template"].sudo().browse(int(raw.get("template_id") or 0)).exists()
        if not template or not template.sale_ok or not template.available_in_pos:
            raise UserError(_("One of the pieces is no longer available."))
        # The kiosk sends the values of the line's variant first and the customer's
        # choices after: with dynamic attributes that variant may carry another size or
        # metal, so the last value of each attribute (the customer's) wins.
        por_atributo = {}
        for v in env["product.template.attribute.value"].sudo().browse(
                [int(i) for i in raw.get("ptav_ids") or []]).exists():
            if v.product_tmpl_id == template:
                por_atributo[v.attribute_line_id.id] = v
        ptavs = env["product.template.attribute.value"].sudo().browse(
            [v.id for v in por_atributo.values()])
        sin_variante = ptavs.filtered(lambda v: v.attribute_id.create_variant == "no_variant")
        product = template._get_variant_for_combination(ptavs - sin_variante) if ptavs else template.product_variant_id
        if not product and ptavs:
            product = template._create_product_variant(ptavs - sin_variante)
        product = product or template.product_variant_id
        if not product:
            raise UserError(_("One of the pieces is no longer available."))
        precio = False
        if getattr(template, "xb_precio_por_metal", False) and hasattr(template, "xb_pos_precio_combinacion"):
            res = env["product.template"].sudo().with_company(config.company_id).xb_pos_precio_combinacion(
                template.id, ptavs.ids, pricelist.id)
            precio = res and res.get("sin")
        if not precio:
            precio = pricelist._get_product_price(product, 1.0) if pricelist else product.lst_price
        taxes = product.taxes_id._filter_taxes_by_company(config.company_id)
        return {
            "product_id": product.id,
            "qty": max(float(raw.get("qty") or 1), 1.0),
            "price_unit": precio,
            "discount": 0.0,
            "tax_ids": taxes.ids,
        }, sin_variante

    @http.route("/xb_kiosk/quotation", type="jsonrpc", auth="public", website=True)
    def kiosk_quotation(self, access_token=None, name=None, phone=None, lines=None,
                        send_whatsapp=False, **kw):
        """The customer asks the kiosk for a quotation of the cart: printed and/or by
        WhatsApp. Created exactly as the POS creates its quotations (same function,
        same validity and terms), for the customer identified by their mobile."""
        config = request.env["pos.config"].sudo().search([("access_token", "=", access_token or "x")], limit=1)
        if not config or not config.has_active_session:
            return {"error": _("The kiosk cannot make quotations right now.")}
        modes = config._xb_kiosk_quotation_modes()
        if not (modes["print"] or modes["whatsapp"]):
            return {"error": _("The kiosk cannot make quotations right now.")}
        name = (name or "").strip()
        digits = self._xb_digits(phone)
        if len(name) < 2:
            return {"error": _("Write your name.")}
        if not digits:
            return {"error": _("Write your 10-digit mobile number.")}
        if not lines:
            return {"error": _("Your cart is empty.")}
        user = config.self_ordering_default_user_id or request.env.ref("base.user_admin")
        env = request.env(user=user.id, context=dict(request.env.context, allowed_company_ids=config.company_id.ids))
        config = config.with_env(env)
        pricelist = config.pricelist_id
        try:
            partner = self._xb_partner(env, name, digits)
            cart, sin_variante = [], []
            for raw in lines:
                line, extra = self._xb_line(env, config, pricelist, raw)
                cart.append(line)
                sin_variante.append(extra)
            result = env["sale.order"].xb_create_order_from_pos({
                "pos_config_id": config.id,
                "partner_id": partner.id,
                "pricelist_id": pricelist.id or False,
                "type": "quotation",
                "lines": cart,
            })
            order = env["sale.order"].sudo().browse(result["sale_order_id"])
            for so_line, extra in zip(order.order_line, sin_variante):
                if extra:
                    so_line.product_no_variant_attribute_value_ids = [(6, 0, extra.ids)]
            # Nobody sold it yet: the ticket must not say «served by» the kiosk's user.
            order.write({"user_id": False, "origin": config.name})
        except UserError as e:
            request.env.cr.rollback()
            return {"error": str(e)}
        whatsapp = None
        if send_whatsapp:
            try:
                order.with_env(env)._xb_send_wa_quotation(phone="+52" + digits)
                whatsapp = True
            except Exception as e:  # noqa: BLE001 - the quotation exists even if WhatsApp fails
                _logger.warning("Kiosk quotation %s: WhatsApp failed: %s", order.name, e)
                whatsapp = str(e)
        image = order._xb_quotation_image(as_base64=True)
        return {
            "ok": True,
            "name": order.name,
            "customer": partner.name,
            "whatsapp": whatsapp,
            "image": image.decode() if isinstance(image, bytes) else image,
        }
