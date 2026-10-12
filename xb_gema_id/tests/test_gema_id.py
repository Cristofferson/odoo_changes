from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGemaId(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "x_studio_id_gema" not in cls.env["product.template"]._fields:
            cls.skipTest(cls, "No gem ID field in this database")
        cls.env["ir.config_parameter"].sudo().set_param("xb_gema_id.webdav_url", False)
        cls.categ = cls.env["product.category"].create({"name": "Test gems", "xb_gema_id": True})
        cls.sequence = cls.env.ref("xb_gema_id.seq_gem_id")
        cls.sequence.number_next_actual = 9001
        # A person (not the superuser) creates the gems.
        cls.Template = cls.env["product.template"].with_user(cls.env.ref("base.user_admin"))

    def _gem(self, **vals):
        return self.Template.create({
            "name": "Test gem", "categ_id": self.categ.id, "is_storable": True,
            "tracking": "serial", **vals,
        })

    def test_new_gems_are_numbered(self):
        first, second = self._gem(), self._gem()
        self.assertEqual(first.x_studio_id_gema, "9001")
        self.assertEqual(second.x_studio_id_gema, "9002")

    def test_typed_id_is_kept_and_skipped(self):
        typed = self._gem(x_studio_id_gema="9001")
        self.assertEqual(typed.x_studio_id_gema, "9001")
        self.assertEqual(self._gem().x_studio_id_gema, "9002")

    def test_copy_gets_a_new_number(self):
        gem = self._gem()
        self.assertEqual(gem.copy().x_studio_id_gema, "9002")

    def test_not_numbered(self):
        no_serial = self.Template.create({"name": "Accent stone", "categ_id": self.categ.id})
        self.assertFalse(no_serial.x_studio_id_gema)
        by_system = self.env["product.template"].sudo().create({
            "name": "Zirconia", "categ_id": self.categ.id, "is_storable": True, "tracking": "serial",
        })
        self.assertFalse(by_system.x_studio_id_gema)

    def test_categorized_later(self):
        gem = self.Template.create({"name": "Loose gem", "is_storable": True, "tracking": "serial"})
        self.assertFalse(gem.x_studio_id_gema)
        gem.categ_id = self.categ
        self.assertEqual(gem.x_studio_id_gema, "9001")
