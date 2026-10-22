# -*- coding: utf-8 -*-
import os
import re

from odoo.http import request

from odoo.addons.xb_anillo_diamante_natural.models.sale_order import SESION
from odoo.addons.xb_showroom_wall.controllers.wall import ShowroomWall
from odoo.addons.xb_showroom_wall_self_order.controllers.kiosk import ShowroomKiosk


def _gema(template, options, gema_id):
    """El diamante natural ``gema_id`` si el anillo lleva «Diamante natural» y la gema lo es."""
    Product = request.env["product.product"].sudo()
    if not gema_id or not template or not template.sudo()._xb_ptav_natural(options.sudo()):
        return Product
    try:
        gema = Product.browse(int(gema_id)).exists()
    except (TypeError, ValueError):
        return Product
    return gema if gema and gema._xb_es_diamante_natural() else Product


# La forma de la piedra central como la escribe la zirconia de los materiales
# («Zirconia central princesa 5 mm») → el prefijo de los diamantes sueltos.
_FORMAS = {"redonda": "BR", "princesa": "PR", "oval": "OV", "ovalada": "OV", "esmeralda": "EM",
           "corazón": "HS", "corazon": "HS", "cojín": "CB", "cojin": "CB", "marquesa": "MQ",
           "pera": "PS", "baguette": "BG", "radiante": "RA", "asscher": "AS"}


def _forma_anillo(template):
    """Prefijo de la forma de la piedra central del anillo («BR», «PR»…),
    leído de su zirconia central; «BR» si no la dice."""
    bom = request.env["mrp.bom"].sudo().search(
        [("product_tmpl_id", "=", template.id), ("product_id", "=", False)], limit=1)
    for line in bom.bom_line_ids:
        m = re.match(r"\s*zirconia\s+central\s+(\S+)", line.product_id.name or "", re.I)
        if m:
            return _FORMAS.get(m.group(1).lower(), m.group(1).upper())
    return "BR"


def _muestra_lab(template, options):
    """Un diamante de laboratorio suelto con video, de la misma forma que la
    piedra del anillo y el tamaño más parecido. Nunca de otra forma; y si no
    es redondo, solo una muestra que la tienda aprobó por nítida: sin ella el
    muro se queda con el estuche."""
    opcion = (options or request.env["product.template.attribute.value"]).filtered(
        lambda v: "laboratorio" in (v.name or "").lower())[:1]
    m = opcion and re.search(r"(\d+(?:[.,]\d+)?)\s*ct", opcion.name or "")
    if not m:
        return None
    quilates = float(m.group(1).replace(",", "."))
    forma = _forma_anillo(template)
    Tmpl = request.env["product.template"].sudo()
    Att = request.env["ir.attachment"].sudo()
    # Las muestras que la tienda escogió por nítidas van primero (parámetro
    # del sistema con ids de producto separados por comas).
    preferidas = [int(x) for x in re.findall(r"\d+", request.env["ir.config_parameter"].sudo().get_param(
        "xb_anillo_diamante_natural_showroom.muestras_lab") or "")]
    candidatos = Tmpl.search([("name", "=ilike", "Diamante LAB %s %%" % forma),
                              ("company_id", "in", [False, template.company_id.id])])
    if preferidas and candidatos.filtered(lambda t: t.id in preferidas):
        candidatos = candidatos.filtered(lambda t: t.id in preferidas)
    elif forma != "BR":
        # Los videos de princesa, oval… que hay se ven borrosos en grande.
        return None
    con_video = set(Att.search([("res_model", "=", "product.template"), ("res_id", "in", candidatos.ids),
                                ("res_field", "=", "x_studio_video")]).mapped("res_id"))
    candidatos = candidatos.filtered(lambda t: t.id in con_video)
    if not candidatos:
        return None
    return min(candidatos, key=lambda t: (abs((t.x_studio_quilataje_c or 0.0) - quilates), t.id))


# Muestras generadas con IA para las formas sin un video nítido de verdad:
# una foto por forma en static/src/img/muestras/<prefijo>.jpg.
_MUESTRAS_IA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "src", "img", "muestras")


def _muestra_ia(template, options):
    """Prefijo de la forma («PR»…) si el anillo lleva diamante de laboratorio,
    no es redondo y hay foto de muestra para esa forma."""
    opcion = (options or request.env["product.template.attribute.value"]).filtered(
        lambda v: "laboratorio" in (v.name or "").lower())[:1]
    if not (opcion and re.search(r"\d\s*ct", opcion.name or "")):
        return None
    forma = _forma_anillo(template)
    if forma == "BR" or not os.path.isfile(os.path.join(_MUESTRAS_IA, "%s.jpg" % forma)):
        return None
    return forma


def _forma_lab(template):
    """«PR» de «Diamante LAB PR 0.47 …»."""
    m = re.match(r"\s*Diamante\s+LAB\s+(\S+)", template.name or "", re.I)
    return m.group(1).upper() if m else ""


def _medidas(gema):
    """Alto y ancho del diamante visto de arriba («Medida 1» × «Medida 2», en
    mm), solo si los tiene. La muestra de laboratorio no lleva: sus medidas no
    son las del diamante que irá en el anillo."""
    alto = getattr(gema, "x_studio_medida1_c", 0) or 0
    ancho = getattr(gema, "x_studio_medida2_c", 0) or 0
    if not (alto and ancho):
        return None
    return {"height": "%.2f mm" % alto, "width": "%.2f mm" % ancho}


class XbDnShowroomWall(ShowroomWall):

    def _wall_stone(self, template, options):
        """Tienda: el diamante que el cliente eligió en la ficha (queda en la sesión)."""
        elegidas = request.session.get(SESION) or {}
        gema = _gema(template, options, elegidas.get(str(template.id)))
        if not gema:
            return super()._wall_stone(template, options)
        precios = gema.product_tmpl_id._get_sales_prices(request.website)
        return gema, precios[gema.product_tmpl_id.id]["price_reduce"]

    def _wall_stone_media(self, screen, product, options, slot):
        """Natural: el diamante que eligió el cliente. Laboratorio: el anillo
        no lleva una piedra en particular, así que va uno de nuestros
        diamantes de laboratorio sueltos como muestra («Imagen de referencia»)."""
        stone = slot.stone_id if slot else None
        if stone:
            gema = stone.product_tmpl_id.sudo()
            return {"stone": gema, "sample": False, "size": _medidas(gema)}
        muestra = _muestra_lab(product.product_tmpl_id, options)
        if muestra:
            # Las miniaturas pueden venir de otro diamante de laboratorio con
            # fotos más claras de corazones y flechas (parámetro del sistema).
            vistas = re.findall(r"\d+", request.env["ir.config_parameter"].sudo().get_param(
                "xb_anillo_diamante_natural_showroom.muestras_lab_vistas") or "")
            otra = request.env["product.template"].sudo().browse(int(vistas[0])).exists() if vistas else None
            # Esas vistas son de un redondo: a otra forma le van las suyas.
            if otra and _forma_lab(otra) != _forma_lab(muestra):
                otra = None
            return {"stone": muestra, "sample": True, "views": otra or None}
        return super()._wall_stone_media(screen, product, options, slot)

    def _stone_media_dict(self, screen, product, options, slot):
        media = super()._stone_media_dict(screen, product, options, slot)
        if media or (slot and slot.stone_id):
            return media
        forma = _muestra_ia(product.product_tmpl_id, options)
        if not forma:
            return media
        # Foto fija: el muro la hace girar despacio, como en el tornamesa.
        return {"motion": "", "image": "/xb_anillo_diamante_natural_showroom/static/src/img/muestras/%s.jpg?v=1" % forma,
                "sample": True, "size": False, "views": [], "spin": True}

    def _wall_stone_allowed(self, screen, template):
        if template.company_id.id not in (False, screen.company_id.id):
            return False
        if (template.name or "").upper().startswith("DIAMANTE LAB "):
            return True
        variante = template.product_variant_id
        return bool(variante and variante._xb_es_diamante_natural())

    def _wall_stone_video(self, template):
        if "x_studio_video" not in template._fields:
            return super()._wall_stone_video(template)
        return request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "product.template"), ("res_id", "=", template.id),
            ("res_field", "=", "x_studio_video")], limit=1)

    def _wall_stone_views(self, template):
        """Las otras vistas del diamante, en el orden en que más dicen: corazones,
        flechas y ASET muestran el corte; «Imagen N» pasa a «Vista N». Sin la
        miniatura del video (el video ya está grande al lado)."""
        orden = ("imagen 2", "corazones", "flechas", "aset", "idealscope", "imagen 1")
        vistas = [(img, etiqueta) for img, etiqueta in super()._wall_stone_views(template)
                  if etiqueta.lower() in orden]
        vistas.sort(key=lambda v: orden.index(v[1].lower()))
        return [(img, re.sub(r"^Imagen\b", "Vista", etiqueta)) for img, etiqueta in vistas]

    def _wall_ref_token(self, value):
        """Como lo escribe la referencia de Anello: el «Atajo» del valor
        (BCO14, DL050) y la medida siempre con un decimal (6 → 6.0)."""
        atajo = value.product_attribute_value_id._fields.get("x_atajo") and \
            (value.product_attribute_value_id.x_atajo or "").strip()
        if atajo:
            return atajo
        nombre = (value.name or "").strip()
        try:
            return "%.1f" % float(nombre.replace(",", "."))
        except ValueError:
            return super()._wall_ref_token(value)

    def _wall_stone_facts(self, screen, stone, facts):
        tmpl = stone.product_tmpl_id
        if not hasattr(tmpl, "_xb_datos_diamante"):
            return super()._wall_stone_facts(screen, stone, facts)
        d = tmpl.with_context(lang=screen.env.lang)._xb_datos_diamante(0)
        etiquetas = self._wall_fact_labels(screen)
        central, total = etiquetas["centre"], etiquetas["total"]
        quilates = d["quilates"] or 0.0
        nuevo = [(central, " ".join(filter(None, [
            "Diamante natural", (d["forma"] or "").lower(),
            ("%.2f ct" % quilates) if quilates else ""])))]
        nuevo += [(etiquetas[clave], d[campo]) for clave, campo in
                  (("colour", "color"), ("clarity", "pureza"), ("cut", "corte"), ("certificate", "certificado"))
                  if d[campo]]
        for etiqueta, valor in facts:
            if etiqueta == central:
                continue
            if etiqueta == total and quilates:
                # «0.20 ct + piedra central» → la suma con el diamante elegido.
                m = re.match(r"\s*([\d.]+)", valor or "")
                valor = "%.2f ct" % ((float(m.group(1)) if m else 0.0) + quilates)
            nuevo.append((etiqueta, valor))
        if quilates and not any(e == total for e, _v in nuevo):
            nuevo.append((total, "%.2f ct" % quilates))
        return nuevo


class XbDnShowroomKiosk(ShowroomKiosk):

    def _kiosk_stone(self, config, template, options, stone_id):
        """Kiosco: el diamante que el cliente eligió, con el precio de la lista del kiosco."""
        gema = _gema(template, options, stone_id)
        if not gema or not config:
            return super()._kiosk_stone(config, template, options, stone_id)
        pricelist = config.pricelist_id
        precio = pricelist._get_product_price(gema, 1.0)
        impuestos = gema.product_tmpl_id.taxes_id._filter_taxes_by_company(config.company_id)
        total = impuestos.compute_all(precio, currency=pricelist.currency_id, quantity=1.0, product=gema)
        return gema, total["total_included"]
