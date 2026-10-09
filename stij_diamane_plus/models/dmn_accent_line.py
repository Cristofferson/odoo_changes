from odoo import api, fields, models

# Peso de un brillante redondo según su diámetro. NO se calcula con la ley del
# cubo: una piedra chica no es un brillante de un quilate encogido, lleva
# proporcionalmente más fondo y cinta, así que pesa más de lo que predice el
# cubo. A 1.3 mm el cubo da 0.008 ct y la piedra real pesa 0.010; a 1.0 mm el
# error llega al 28%. Ésta es la tabla que usa el oficio.
TABLA_MM_CT = [
    (0.80, 0.0025), (0.90, 0.0035), (1.00, 0.005), (1.10, 0.0065),
    (1.20, 0.008), (1.30, 0.010), (1.40, 0.0125), (1.50, 0.015),
    (1.60, 0.018), (1.70, 0.020), (1.80, 0.025), (1.90, 0.028),
    (2.00, 0.030), (2.20, 0.040), (2.40, 0.050), (2.50, 0.060),
    (2.75, 0.080), (3.00, 0.100), (3.25, 0.130), (3.50, 0.160),
    (3.75, 0.200), (4.00, 0.250), (4.25, 0.280), (4.50, 0.330),
    (4.75, 0.400), (5.00, 0.500), (5.25, 0.560), (5.50, 0.650),
    (5.75, 0.750), (6.00, 0.800), (6.25, 0.900), (6.50, 1.000),
]


def quilates_de_mm(mm):
    """Quilates de un brillante redondo de ese diámetro.

    Interpola dentro de la tabla; por arriba de 6.5 mm el cubo ya es fiel,
    porque las piedras grandes sí guardan proporción.
    """
    if not mm or mm <= 0:
        return 0.0
    if mm >= TABLA_MM_CT[-1][0]:
        return round((mm / 6.5) ** 3, 3)
    if mm <= TABLA_MM_CT[0][0]:
        return TABLA_MM_CT[0][1]
    for (m1, c1), (m2, c2) in zip(TABLA_MM_CT, TABLA_MM_CT[1:]):
        if m1 <= mm <= m2:
            t = (mm - m1) / (m2 - m1) if m2 != m1 else 0
            return round(c1 + t * (c2 - c1), 4)
    return 0.0


class DmnAccentLine(models.Model):
    _name = "dmn.accent.line"
    _description = "Grupo de piedras de acento de una joya"
    _order = "size_mm desc, id"

    product_tmpl_id = fields.Many2one(
        "product.template", string="Joya", required=True,
        ondelete="cascade", index=True,
    )
    qty = fields.Integer(string="Cantidad", required=True, default=1)
    size_mm = fields.Float(string="Tamaño (mm)", digits=(6, 2))
    stone_type = fields.Selection(
        [("zirconia", "Zirconia"),
         ("diamante_lab", "Diamante de laboratorio"),
         ("diamante_nat", "Diamante natural"),
         ("otra", "Otra piedra")],
        string="Tipo", required=True, default="zirconia",
    )
    carats_each = fields.Float(
        string="Quilates c/u", digits=(10, 3),
        compute="_compute_carats_each", store=True, readonly=False,
        help="Se estima del diámetro con la tabla del oficio y se puede "
             "corregir a mano. Ojo: la ley del cubo se queda corta hasta un "
             "28% en piedras de menos de 1.5 mm.",
    )
    carats_total = fields.Float(
        string="Quilates del grupo", digits=(10, 3),
        compute="_compute_carats_total", store=True,
    )

    @api.depends("size_mm")
    def _compute_carats_each(self):
        for l in self:
            l.carats_each = quilates_de_mm(l.size_mm)

    @api.depends("qty", "carats_each")
    def _compute_carats_total(self):
        for l in self:
            l.carats_total = round((l.qty or 0) * (l.carats_each or 0.0), 4)

    def _texto(self, material=None):
        """«12 de 1.50 mm (zirconia, 0.150 ct)» — como se lee en el certificado.

        El material lo elige el cliente al configurar el anillo, así que cuando
        se conoce la variante se pasa por `material` y manda sobre el tipo
        guardado en el grupo, que sólo sirve de valor por omisión.
        """
        self.ensure_one()
        etiquetas = dict(self._fields["stone_type"].selection)
        partes = ["%d" % self.qty]
        if self.size_mm:
            partes.append("de %.2f mm" % self.size_mm)
        detalle = material or etiquetas.get(self.stone_type, "")
        if self.carats_total:
            detalle += ", %.3f ct" % self.carats_total
        return "%s (%s)" % (" ".join(partes), detalle.lower())
