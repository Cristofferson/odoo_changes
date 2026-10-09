from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Las piedras de acento viven en el PRODUCTO y no en el lote porque las tres
    # salidas las necesitan: el alta rápida crea producto + lote, el marketplace
    # crea sólo producto, y el PDF del certificado es un reporte sobre
    # product.template. La piedra CENTRAL sigue ligada por lote
    # (stock.lot.dmn_gem_lot_id): ésa sí se certifica una por una.
    dmn_accent_ids = fields.One2many(
        "dmn.accent.line", "product_tmpl_id", string="Piedras de acento",
        copy=True,
    )
    dmn_accent_qty = fields.Integer(
        string="Total de piedras de acento",
        compute="_compute_dmn_accent_totals", store=True,
    )
    dmn_accent_carats = fields.Float(
        string="Quilates de acento", digits=(10, 3),
        compute="_compute_dmn_accent_totals", store=True,
    )
    dmn_stones_summary = fields.Char(
        string="Piedras que lleva", compute="_compute_dmn_stones_summary",
        help="La frase que muestran el visor y el certificado.",
    )

    @api.depends("dmn_accent_ids.qty", "dmn_accent_ids.carats_total")
    def _compute_dmn_accent_totals(self):
        for t in self:
            t.dmn_accent_qty = sum(t.dmn_accent_ids.mapped("qty"))
            t.dmn_accent_carats = round(sum(t.dmn_accent_ids.mapped("carats_total")), 3)

    def _compute_dmn_stones_summary(self):
        for t in self:
            t.dmn_stones_summary = t._dmn_stones_text()

    def _dmn_stones_text(self, variante=None):
        """Qué piedras lleva la joya, en una frase.

        Si se pasa una VARIANTE, las líneas de la lista de materiales se filtran
        por lo que esa combinación eligió: una montadura ofrece la misma piedra
        en zirconia, laboratorio y natural, y sin filtrar el certificado diría
        que lleva las tres.

        Tres orígenes, según qué sea la pieza: la central va ligada al lote y se
        identifica por su número; los grupos de acento se capturan al dar de
        alta; y si es un modelo de catálogo con lista de materiales, ahí ya
        están las piedras del diseño. Se lee lo que haya y se junta.
        """
        self.ensure_one()
        partes = []

        # La central, si el lote de esta pieza tiene una gema ligada.
        lote = self.env["stock.lot"].sudo().search(
            [("product_id", "in", self.product_variant_ids.ids),
             ("dmn_gem_lot_id", "!=", False)], limit=1)
        if lote:
            gema = lote.dmn_gem_lot_id
            tipo = (gema.product_id.categ_id.name or "gema").lower()
            partes.append("1 %s central (%s)" % (tipo, gema.name))

        # Qué piedra eligió esta combinación. Manda sobre el tipo guardado en
        # el grupo: el material es decisión del cliente, no del diseño.
        material = None
        if variante is not None:
            pv = variante.product_template_attribute_value_ids.filtered(
                lambda v: v.attribute_id.name in ("Piedra", "Stone"))[:1]
            if pv:
                material = pv.name
        for linea in self.dmn_accent_ids:
            partes.append(linea._texto(material=material))

        # `mrp` no es dependencia de este módulo: si no está, no hay lista.
        if not self.dmn_accent_ids and "mrp.bom" in self.env:
            objetivo = variante or self.product_variant_ids[:1]
            bom = self.env["mrp.bom"].sudo()._bom_find(objetivo).get(objetivo)
            for l in (bom.bom_line_ids if bom else []):
                if variante is not None and l._skip_bom_line(variante):
                    continue
                n = int(l.product_qty or 0)
                if n > 0:
                    partes.append("%d × %s" % (n, l.product_id.name))

        return " · ".join(partes)


class ProductProduct(models.Model):
    _inherit = "product.product"

    # El visor y el certificado a veces reciben la plantilla y a veces la
    # variante. Exponerlo en ambas evita tener que adivinar en las plantillas.
    dmn_stones_summary = fields.Char(
        string="Piedras que lleva", compute="_compute_dmn_stones_summary",
    )

    def _compute_dmn_stones_summary(self):
        # En la variante sí se sabe qué piedra eligió el cliente, así que se
        # calcula filtrando la lista de materiales por esa combinación.
        for p in self:
            p.dmn_stones_summary = p.product_tmpl_id._dmn_stones_text(variante=p)
