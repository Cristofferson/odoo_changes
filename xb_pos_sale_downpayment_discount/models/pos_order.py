# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.tools import format_amount


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def sync_from_ui(self, orders):
        data = super().sync_from_ui(orders)
        if orders:
            self.browse([o["id"] for o in data["pos.order"]])._xb_carry_downpayment_discounts()
        return data

    def _xb_carry_downpayment_discounts(self):
        """A discount the cashier gives on a down payment only lowers what the ticket
        charges: the sale order keeps its full price, so it shows a balance the customer
        never owed (and the WhatsApp notices quote it). Give the order the same discount,
        as a fixed-amount line of Odoo's own discount wizard, once per POS line."""
        done = self.env["sale.order.line"].sudo().search([
            ("xb_pos_discount_line_id", "in", self.lines.ids),
        ]).xb_pos_discount_line_id
        for pos_order in self.filtered(lambda o: o.state in ("paid", "done", "invoiced")):
            down_payment_product = pos_order.config_id.down_payment_product_id
            lines = pos_order.lines.filtered(lambda line: (
                line not in done
                and line.product_id == down_payment_product
                and line.sale_order_origin_id
                and line.qty > 0
                and line.discount > 0
            ))
            for line in lines:
                sale_order = line.sale_order_origin_id.sudo()
                if sale_order.state == "cancel":
                    continue
                full_price = line.tax_ids.compute_all(
                    line.price_unit, pos_order.currency_id, line.qty,
                    product=line.product_id, partner=pos_order.partner_id,
                )["total_included"]
                amount = sale_order.currency_id.round(full_price - line.price_subtotal_incl)
                if sale_order.currency_id.is_zero(amount):
                    continue
                pos_order._xb_add_sale_order_discount(sale_order, line, amount)

    def _xb_add_sale_order_discount(self, sale_order, pos_line, amount):
        self.ensure_one()
        before = sale_order.order_line
        wizard = self.env["sale.order.discount"].sudo().with_company(sale_order.company_id).create({
            "sale_order_id": sale_order.id,
            "discount_type": "amount",
            "discount_amount": amount,
        })
        wizard._create_discount_lines()
        env = sale_order.with_context(lang=sale_order._get_lang()).env
        new_lines = sale_order.order_line - before
        new_lines.write({
            "xb_pos_discount_line_id": pos_line.id,
            "name": env._("POS discount (ticket %(ticket)s)", ticket=self.name),
        })
        sale_order.message_post(body=env._(
            "The cashier gave a %(percent)s%% discount (%(amount)s) on the down payment of "
            "ticket %(ticket)s: added to the order so its balance matches what the customer "
            "paid.",
            percent=f"{pos_line.discount:g}",
            amount=format_amount(env, amount, sale_order.currency_id),
            ticket=self.name,
        ))
