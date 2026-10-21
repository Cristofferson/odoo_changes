# -*- coding: utf-8 -*-
from odoo import models

CATEG_GEMA = 71
ATRIBUTO_PIEDRA = "Piedra"
PIEDRA_NATURAL = "Diamante natural"
TIPO_DIAMANTE = "Diamante"
ORIGEN_NATURAL = "Natural (mina)"
# El corte con palabras («Corte EX» no le dice nada al cliente); N/A = la forma no se califica.
# Orden de las formas en el filtro: las más pedidas primero.
FORMAS = ["Redondo", "Princesa", "Oval", "Óvalo", "Esmeralda", "Cojín", "Pera", "Marquesa", "Corazón",
          "Radiante", "Asscher", "Baguette"]
CORTES = {"EX": "Excelente", "VG": "Muy bueno", "G": "Bueno", "F": "Regular", "P": "Malo"}


def ordenar_formas(formas):
    orden = {f: i for i, f in enumerate(FORMAS)}
    return sorted({f for f in formas if f}, key=lambda f: (orden.get(f, 99), f))


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _xb_diamantes_naturales_domain(self, website=None):
        """Diamantes naturales sueltos que se pueden elegir para un anillo: pieza única (serie),
        publicados en la tienda. La existencia se revisa aparte (depende del almacén de la tienda)."""
        dom = [
            ("categ_id", "=", CATEG_GEMA),
            ("tracking", "=", "serial"),
            ("is_published", "=", True),
            ("sale_ok", "=", True),
            ("x_studio_origen_c", "=", ORIGEN_NATURAL),
            ("x_studio_tipo_gema_c.x_name", "=", TIPO_DIAMANTE),
        ]
        if website:
            dom += website.website_domain()
        return dom

    def _xb_color_diamante(self):
        """Color D-Z, o el color fancy completo («Intenso Azul»), como en el nombre de la gema."""
        self.ensure_one()
        if self.x_studio_color_fancy:
            return " ".join(filter(None, [self._xb_gema_txt("x_studio_intensidad_color_fancy"),
                                          self._xb_gema_txt("x_studio_tonalidad_del_color_fancy"),
                                          self._xb_gema_txt("x_studio_color")]))
        return self._xb_gema_txt("x_studio_color_real")

    def _xb_datos_diamante(self, precio):
        """Lo que el selector muestra de un diamante (web y kiosco); ``precio`` con impuestos."""
        self.ensure_one()
        return {
            "id": self.product_variant_id.id,
            "tmpl_id": self.id,
            "nombre": self.name,
            "forma": self._xb_gema_txt("x_studio_talla_o_forma", "x_studio_nombre_de_la_forma").strip().capitalize(),
            "quilates": self.x_studio_quilataje_c or 0.0,
            "color": self._xb_color_diamante(),
            "pureza": self._xb_gema_txt("x_studio_pureza_real"),
            "corte": CORTES.get(self._xb_gema_txt("x_studio_corte"), ""),
            "certificado": ", ".join(self.x_studio_certificados.mapped("display_name")),
            "precio": precio,
            "imagen": "/web/image/product.template/%d/image_256" % self.id,
            "url": self.website_url,
        }

    def _xb_gemas(self, ptavs):
        texto, renglones = super()._xb_gemas(ptavs)
        if self._xb_ptav_natural(ptavs):
            renglones = [
                "Diamante central natural: el que elijas de nuestros diamantes certificados" if
                r.startswith("Diamante central natural:") else r
                for r in renglones
            ]
        return texto, renglones

    def _xb_ptav_natural(self, ptavs):
        """El valor «Piedra: Diamante natural» de la combinación (o vacío). En las argollas
        «Diamantes naturales» (en plural) son los acentos de la banda, no un diamante central."""
        if not self.xb_precio_por_metal:
            return ptavs.browse()
        return ptavs.filtered(
            lambda v: v.attribute_id.with_context(lang="es_MX").name == ATRIBUTO_PIEDRA
            and v.product_attribute_value_id.with_context(lang="es_MX").name == PIEDRA_NATURAL
        )


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _xb_es_anillo_natural(self):
        """Anillo cotizado por metal con «Diamante natural» como piedra central."""
        self.ensure_one()
        tmpl = self.product_tmpl_id
        return bool(tmpl.xb_precio_por_metal and tmpl._xb_ptav_natural(self.product_template_attribute_value_ids))

    def _xb_es_diamante_natural(self, website=None):
        self.ensure_one()
        tmpl = self.product_tmpl_id.sudo().with_context(lang="en_US")  # x_name del tipo de gema, en inglés
        return bool(self.active and tmpl.filtered_domain(tmpl._xb_diamantes_naturales_domain(website)))
