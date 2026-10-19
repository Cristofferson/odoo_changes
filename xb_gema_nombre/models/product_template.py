# -*- coding: utf-8 -*-
from decimal import ROUND_FLOOR, Decimal

from odoo import api, fields, models

CATEG_GEMA = 71
# Palabras que no aportan al nombre.
VACIOS = {"", "n/a", "na", "otro", "ninguno", "none"}
# Si cambia alguno, el nombre se vuelve a armar.
CAMPOS_NOMBRE = {
    "categ_id", "tracking", "xb_nombre_fijo", "x_studio_tipo_gema_c", "x_studio_origen_c",
    "x_studio_talla_o_forma", "x_studio_quilataje_c", "x_studio_pureza_real", "x_studio_color_real",
    "x_studio_corte", "x_studio_certificados", "x_studio_color_fancy", "x_studio_color",
    "x_studio_intensidad_color_fancy", "x_studio_tonalidad_del_color_fancy",
}


def quilates_gia(q):
    """2 decimales con la regla GIA: se corta al centésimo y solo sube si la
    tercera cifra es 9. 0.899 → '0.90', 0.898 → '0.89', 1.028 → '1.02'."""
    if not q:
        return ""
    milesimas = Decimal(str(q)).quantize(Decimal("0.001"), rounding=ROUND_FLOOR)
    centesimas = milesimas.quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    if int(milesimas * 1000) % 10 == 9:
        centesimas += Decimal("0.01")
    if not centesimas:  # menos de un centésimo: no hay forma GIA de escribirlo
        return ("%f" % q).rstrip("0").rstrip(".")
    return "%.2f" % centesimas


class ProductTemplate(models.Model):
    _inherit = "product.template"

    xb_nombre_fijo = fields.Boolean(
        "Nombre fijo",
        help="Si está marcada, el nombre de la gema no se calcula a partir de sus datos.")

    def _xb_nombre_aplica(self):
        self.ensure_one()
        return (self.categ_id.id == CATEG_GEMA and self.tracking == "serial" and not self.xb_nombre_fijo
                and "x_studio_tipo_gema_c" in self._fields)

    def _xb_nombre_automatico(self):
        self.ensure_one()
        t = self.with_context(lang="es_MX")

        def v(campo):
            if campo not in t._fields:
                return ""
            valor = t[campo]
            if t._fields[campo].type == "many2one":
                return valor.display_name or ""
            if t._fields[campo].type == "selection":
                return dict(t._fields[campo]._description_selection(t.env)).get(valor, valor) or ""
            return valor or ""

        tipo = v("x_studio_tipo_gema_c")
        if not tipo:
            return False  # sin tipo no se puede armar un nombre que sirva
        lab = "LAB" if v("x_studio_origen_c").lower().startswith("sint") else ""
        if t.x_studio_color_fancy:
            color = " ".join(filter(None, [v("x_studio_intensidad_color_fancy"),
                                           v("x_studio_tonalidad_del_color_fancy"), v("x_studio_color")]))
        else:
            color = v("x_studio_color_real")
        certs = ", ".join(c for c in t.x_studio_certificados.mapped("display_name") if c.strip().lower() not in VACIOS)
        partes = [tipo, lab, v("x_studio_talla_o_forma"), quilates_gia(t.x_studio_quilataje_c),
                  v("x_studio_pureza_real"), color, v("x_studio_corte"), certs]
        return " ".join(str(p).strip() for p in partes if str(p).strip().lower() not in VACIOS)

    def _xb_aplicar_nombre(self):
        cambiadas = self.browse()
        for t in self:
            if not t._xb_nombre_aplica():
                continue
            nombre = t._xb_nombre_automatico()
            if nombre and nombre != t.with_context(lang="es_MX").name:
                # el nombre se traduce: se escribe igual en los dos idiomas para
                # que la tienda (es_MX) y el respaldo (en_US) no difieran
                for lang in ("en_US", "es_MX"):
                    t.with_context(lang=lang, xb_nombre_gema=True).write({"name": nombre})
                cambiadas |= t
        return cambiadas

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        if not self.env.context.get("xb_nombre_gema"):
            templates._xb_aplicar_nombre()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("xb_nombre_gema") and CAMPOS_NOMBRE.intersection(vals):
            self._xb_aplicar_nombre()
        return res
