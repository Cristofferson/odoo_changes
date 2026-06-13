# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged("post_install", "-at_install")
class TestXbSaleOrderFromPosTour(TestPointOfSaleHttpCommon):

    def test_xb_create_order_flows(self):
        """Tour: create Quotation / Order / Layaway from the POS cart button."""
        # Enable the feature and all sub-options on the test POS, and configure a
        # down-payment product so the Layaway (advance) flow passes the guard.
        self.main_pos_config.write({
            "xb_enable_sale_order": True,
            "xb_allow_quotation": True,
            "xb_differentiate_order_layaway": True,
            "down_payment_product_id": self.wall_shelf.product_variant_id.id,
        })
        self.main_pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour("XbCreateOrderFlows", login="pos_user")

        # Backend assertion: three sale orders were created for the customer, with
        # the expected states (1 draft quotation + 2 confirmed orders).
        orders = self.env["sale.order"].search([
            ("partner_id", "=", self.partner_test_1.id),
        ])
        self.assertEqual(len(orders), 3, "Expected 3 sale orders created from POS")
        self.assertEqual(
            sorted(orders.mapped("state")),
            ["draft", "sale", "sale"],
            "Expected 1 quotation (draft) and 2 confirmed orders (sale)",
        )
