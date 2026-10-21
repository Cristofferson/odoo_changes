# -*- coding: utf-8 -*-
import logging
import re

from odoo import api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

CATEG_GEMA = 71
# El «Precio público» ya trae el IVA; la tienda se lo suma al precio de
# venta, así que se guarda sin él.
IVA = 0.16
# Campos de los que depende x_studio_precio_publico (compute de Studio) y
# la cotización de rapaport_pricing, que escribe x_studio_precio_rapnet_qt.
CAMPOS_PRECIO = {
    "categ_id", "tracking", "x_studio_precio_rapnet_qt", "x_studio_quilataje_c", "x_studio_corte",
    "x_studio_triple_excelente_c", "x_studio_ha_c", "x_studio_certificados",
    "x_studio_origen_c",
}
TIPO_DIAMANTE = "Diamante"
# Diamante de laboratorio: el costo es un precio fijo en dólares por quilate,
# sin importar sus características (19-oct-2026), y su precio es ese costo por
# un margen propio: suelto (acento) y dentro de las joyas (xb_joyeria_peso_precio).
PARAM_USD_QUILATE = "xb_gema_precio_rapaport.lab_usd_quilate"
PARAM_FACTOR_LAB = "xb_gema_precio_rapaport.factor_lab"
# Lista de precios de DIAMANE (venta a joyeros, 21-oct-2026): un precio fijo por
# diamante que se recalcula cada semana con el dólar del día.
#   Natural: Rapaport (USD) × dólar, menos un descuento según el tamaño.
#   Laboratorio: costo (USD por quilate × quilates × dólar) × factor propio.
PARAM_DIAMANE_LISTA = "xb_gema_precio_rapaport.diamane_pricelist_id"
PARAM_DIAMANE_FACTOR_LAB = "xb_gema_precio_rapaport.diamane_factor_lab"
PARAM_DIAMANE_ESCALONES = "xb_gema_precio_rapaport.diamane_escalones"
# «hasta N quilates: X % menos que Rapaport»; lo que pase del último tope lleva el último %.
ESCALONES_DIAMANE = "0.099:20,0.50:18,1.00:15,1.50:13,1.999:10,999:5"
ORIGEN_LAB = "Sintético (laboratorio)"
# Acentos naturales (sin serie): su costo × este factor (21-oct-2026: costo + 20 %). Su costo
# capturado sale arriba de Rapaport, así que no se cotizan con Rapaport.
PARAM_DIAMANE_ACENTOS_NAT = "xb_gema_precio_rapaport.diamane_acentos_nat"
PARAM_DIAMANE_FACTOR_ACENTO_NAT = "xb_gema_precio_rapaport.diamane_factor_acento_nat"
QUILATES_NOMBRE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Qts?|ct)\b", re.I)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    xb_costo_lab_quilate = fields.Boolean(
        "Costo LAB por quilate",
        help="Diamante de laboratorio: el costo se calcula cada semana con el precio en dólares por "
             "quilate (parámetro %s) y el dólar del día. Se vende a ese costo por el factor %s: "
             "suelto si es un acento (sin número de serie) y dentro de las joyas." % (PARAM_USD_QUILATE, PARAM_FACTOR_LAB))

    def _xb_es_acento(self):
        """Diamante de acento: gema sin número de serie. Solo se vende en la caja y en Ventas."""
        self.ensure_one()
        return (self.categ_id.id == CATEG_GEMA and self.tracking != "serial"
                and "x_studio_tipo_gema_c" in self._fields
                and self.with_context(lang="en_US").x_studio_tipo_gema_c.x_name == TIPO_DIAMANTE)

    def _xb_ocultar_acentos(self):
        # Ni la tienda en línea, ni el kiosco (y su vendedor virtual), ni el
        # agente de la tienda, que ofrece solo lo publicado.
        for t in self.filtered(lambda t: t._xb_es_acento()):
            vals = {}
            if "is_published" in t._fields and t.is_published:
                vals["is_published"] = False
            if "self_order_available" in t._fields and t.self_order_available:
                vals["self_order_available"] = False
            if vals:
                t.with_context(xb_precio_rapaport=True).write(vals)

    def _xb_quilates(self):
        self.ensure_one()
        if "x_studio_quilataje_c" in self._fields and self.x_studio_quilataje_c:
            return self.x_studio_quilataje_c
        m = QUILATES_NOMBRE.search(self.with_context(lang="en_US").name or "")
        return float(m.group(1)) if m else 0.0

    def _xb_aplicar_costo_lab(self, tasa=None):
        lab = self.filtered(lambda t: t.xb_costo_lab_quilate and t._xb_quilates())
        if not lab:
            return 0
        icp = self.env["ir.config_parameter"].sudo()
        usd_quilate = float(icp.get_param(PARAM_USD_QUILATE, "180"))
        factor = float(icp.get_param(PARAM_FACTOR_LAB, "3.88"))
        tasa = tasa or self._xb_tasa_usd_mxn()
        # El costo es por compañía: el de la pieza, o el de la tienda.
        compania_tienda = self.env.ref("website.default_website").company_id
        cambiadas = 0
        for t in lab:
            costo = round(usd_quilate * t._xb_quilates() * tasa, 2)
            compania = t.company_id or compania_tienda
            variantes = t.product_variant_ids.with_company(compania)
            if any(float_compare(v.standard_price, costo, precision_digits=2) for v in variantes):
                variantes.write({"standard_price": costo})
                cambiadas += 1
            if t.tracking != "serial":
                precio = round(costo * factor, 2)
                if float_compare(t.list_price, precio, precision_digits=2):
                    t.with_context(xb_precio_rapaport=True).write({"list_price": precio})
        return cambiadas

    def _xb_tasa_usd_mxn(self):
        """Pesos por dólar de hoy, de la compañía que lleva tasas de USD (en
        esta BD solo la principal; Anello no tiene tasas propias)."""
        usd = self.env.ref("base.USD")
        mxn = self.env.ref("base.MXN")
        tasa = self.env["res.currency.rate"].sudo().search(
            [("currency_id", "=", usd.id)], order="name desc", limit=1)
        compania = tasa.company_id or self.env.company
        return usd._convert(1.0, mxn, compania, fields.Date.context_today(self), round=False)

    def _xb_aplicar_precio_rapaport(self, tasa=None):
        # Solo piezas únicas (con número de serie): los diamantes de acento no
        # llevan serie, tienen precio a mano y los anillos calculan su precio
        # con ellos.
        gemas = self.filtered(lambda t: t.categ_id.id == CATEG_GEMA
                              and t.tracking == "serial"
                              and "x_studio_precio_publico" in t._fields
                              and t.x_studio_precio_publico > 0)
        if not gemas:
            return 0
        tasa = tasa or self._xb_tasa_usd_mxn()
        cambiadas = 0
        for gema in gemas:
            precio = round(gema.x_studio_precio_publico * tasa / (1 + IVA), 2)
            if float_compare(gema.list_price, precio, precision_digits=2):
                gema.with_context(xb_precio_rapaport=True).write({"list_price": precio})
                cambiadas += 1
        return cambiadas

    # ------------------------------------------------------------------
    # Lista de precios DIAMANE
    # ------------------------------------------------------------------
    def _xb_es_diamante(self):
        self.ensure_one()
        return (self.categ_id.id == CATEG_GEMA and "x_studio_tipo_gema_c" in self._fields
                and self.with_context(lang="en_US").x_studio_tipo_gema_c.x_name == TIPO_DIAMANTE)

    def _xb_es_lab(self):
        self.ensure_one()
        origen = self.x_studio_origen_c if "x_studio_origen_c" in self._fields else False
        if origen:
            return origen == ORIGEN_LAB
        return bool(re.search(r"\bLAB\b", self.with_context(lang="en_US").name or ""))

    def _xb_descuento_diamane(self, quilates):
        icp = self.env["ir.config_parameter"].sudo()
        escalones = []
        for parte in (icp.get_param(PARAM_DIAMANE_ESCALONES) or ESCALONES_DIAMANE).split(","):
            tope, _, pct = parte.partition(":")
            escalones.append((float(tope), float(pct)))
        for tope, pct in sorted(escalones):
            if quilates <= tope:
                return pct
        return sorted(escalones)[-1][1]

    def _xb_precio_diamane(self, tasa):
        """Precio sin IVA de este diamante en la lista de DIAMANE, o None si no aplica."""
        self.ensure_one()
        if not self._xb_es_diamante():
            return None
        quilates = self._xb_quilates()
        if not quilates:
            return None
        icp = self.env["ir.config_parameter"].sudo()
        if self._xb_es_lab():
            costo = float(icp.get_param(PARAM_USD_QUILATE, "180")) * quilates * tasa
            return round(costo * float(icp.get_param(PARAM_DIAMANE_FACTOR_LAB, "1.48")), 2)
        if self.tracking != "serial":
            if icp.get_param(PARAM_DIAMANE_ACENTOS_NAT, "0") != "1":
                return None
            # El costo vive en la compañía de la pieza o en la de la tienda (Anello).
            compania = self.company_id or self.env.ref("website.default_website").company_id
            costo = self.with_company(compania).standard_price
            if not costo:
                return None
            return round(costo * float(icp.get_param(PARAM_DIAMANE_FACTOR_ACENTO_NAT, "1.20")), 2)
        rapaport = self.x_studio_precio_rapnet_st if "x_studio_precio_rapnet_st" in self._fields else 0
        if not rapaport or rapaport <= 0:
            return None
        return round(rapaport * tasa * (1 - self._xb_descuento_diamane(quilates) / 100), 2)

    @api.model
    def _xb_lista_diamane(self):
        lista_id = int(self.env["ir.config_parameter"].sudo().get_param(PARAM_DIAMANE_LISTA, "0") or 0)
        return self.env["product.pricelist"].sudo().browse(lista_id).exists()

    @api.model
    def _xb_sincronizar_lista_diamane(self, gemas=None, tasa=None):
        """Un precio fijo por diamante en la lista de DIAMANE. Sin `gemas`, revisa todos
        y quita de la lista los que ya no tengan precio. Devuelve (puestos, quitados)."""
        lista = self._xb_lista_diamane()
        if not lista:
            return 0, 0
        todas = gemas is None
        if todas:
            gemas = self.with_context(active_test=False).search([("categ_id", "=", CATEG_GEMA)])
        tasa = tasa or self._xb_tasa_usd_mxn()
        Item = self.env["product.pricelist.item"].sudo()
        existentes = {i.product_tmpl_id.id: i for i in Item.search([
            ("pricelist_id", "=", lista.id), ("applied_on", "=", "1_product"),
            ("product_tmpl_id", "in", gemas.ids)])}
        puestos = quitados = 0
        nuevos = []
        for gema in gemas:
            # Las piezas de otra compañía (p. ej. los acentos de Anello) no se venden en DIAMANE.
            propia = not gema.company_id or gema.company_id == lista.company_id or not lista.company_id
            precio = gema._xb_precio_diamane(tasa) if gema.active and propia else None
            item = existentes.get(gema.id)
            if precio is None:
                if item:
                    item.unlink()
                    quitados += 1
                continue
            if item:
                if item.compute_price != "fixed" or float_compare(item.fixed_price, precio, precision_digits=2):
                    item.write({"compute_price": "fixed", "fixed_price": precio})
                    puestos += 1
            else:
                nuevos.append({"pricelist_id": lista.id, "applied_on": "1_product", "product_tmpl_id": gema.id,
                               "compute_price": "fixed", "fixed_price": precio})
        if nuevos:
            Item.create(nuevos)
            puestos += len(nuevos)
        return puestos, quitados

    @api.model
    def _cron_xb_precio_rapaport(self):
        gemas = self.with_context(active_test=False).search(
            [("categ_id", "=", CATEG_GEMA), ("tracking", "=", "serial"), ("x_studio_precio_publico", ">", 0)])
        cambiadas = gemas._xb_aplicar_precio_rapaport()
        _logger.info("Precio de venta Rapaport: %s de %s gemas actualizadas", cambiadas, len(gemas))
        lab = self.with_context(active_test=False).search([("xb_costo_lab_quilate", "=", True)])
        _logger.info("Costo LAB por quilate: %s de %s diamantes actualizados", lab._xb_aplicar_costo_lab(), len(lab))
        _logger.info("Lista DIAMANE: %s precios puestos, %s quitados", *self._xb_sincronizar_lista_diamane())
        return cambiadas

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        if not self.env.context.get("xb_precio_rapaport"):
            templates._xb_aplicar_precio_rapaport()
            templates._xb_aplicar_costo_lab()
            templates._xb_ocultar_acentos()
            templates._xb_sincronizar_lista_diamane(templates)
        return templates

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get("xb_precio_rapaport"):
            return res
        if CAMPOS_PRECIO.intersection(vals):
            self._xb_aplicar_precio_rapaport()
        if {"xb_costo_lab_quilate", "x_studio_quilataje_c"}.intersection(vals):
            self._xb_aplicar_costo_lab()
        if {"is_published", "website_published", "self_order_available", "categ_id", "tracking",
                "x_studio_tipo_gema_c"}.intersection(vals):
            self._xb_ocultar_acentos()
        if CAMPOS_PRECIO.intersection(vals) or {"active", "name", "x_studio_tipo_gema_c"}.intersection(vals):
            self._xb_sincronizar_lista_diamane(self)
        return res
