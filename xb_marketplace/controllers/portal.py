import base64

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


# Metales que se ofrecen al vendedor. Son valores del atributo Metal del
# catálogo de Anello — no una lista propia del marketplace.
METALES_PUBLICADOS = [
    'Oro amarillo 10kt', 'Oro amarillo 14kt', 'Oro amarillo 18kt',
    'Oro blanco 10kt', 'Oro blanco 14Kt', 'Oro blanco 18kt',
    'Oro rosa 10Kt', 'Oro rosa 14Kt', 'Oro rosa 18Kt',
    'Oro bitono 10Kt', 'Oro bitono 14Kt', 'Oro bitono 18Kt',
    'Platino Puro (999)',
]

# El origen del formulario, dicho como lo dice el catálogo de gemas.
ORIGEN_A_CATALOGO = {
    'Natural': 'Natural (mina)',
    'Cultivado (lab)': 'Sintético (laboratorio)',
}

# Cómo se llamaban los metales en la versión anterior del formulario, para que
# los anuncios viejos y cualquier envío rezagado sigan cayendo en su lugar.
METALES_ANTERIORES = {
    'Oro blanco 14k': 'Oro blanco 14Kt',
    'Oro blanco 18k': 'Oro blanco 18kt',
    'Oro amarillo 14k': 'Oro amarillo 14kt',
    'Oro amarillo 18k': 'Oro amarillo 18kt',
    'Platino': 'Platino Puro (999)',
    # 'Oro rosa' no se mapea a propósito: sin kilataje es ambiguo y se
    # pregunta en la moderación.
}


class MarketplacePortal(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _es(self, modelo):
        """El modelo con el idioma anclado en español.

        Los nombres de metales y atributos que este archivo compara están
        escritos en español, pero `name` es un campo traducible: se resuelve
        en el idioma del visitante. Sin anclarlo, un vendedor navegando
        anello.mx en inglés recibiría el selector de metales VACÍO, porque
        el valor se llamaría «18K Yellow Gold» y no «Oro amarillo 18kt».
        """
        return request.env[modelo].sudo().with_context(lang='es_MX')

    def _attr_catalogo(self, nombre):
        """El atributo del catálogo de Anello, no el que creó el marketplace.
        Se distinguen porque el bueno genera variantes (dinámico)."""
        return self._es('product.attribute').search(
            [('name', '=', nombre), ('create_variant', '=', 'dynamic')],
            limit=1)

    def _metales_disponibles(self):
        attr = self._attr_catalogo('Metal')
        if not attr:
            return request.env['product.attribute.value']
        valores = self._es('product.attribute.value').search(
            [('attribute_id', '=', attr.id), ('name', 'in', METALES_PUBLICADOS)])
        orden = {n: i for i, n in enumerate(METALES_PUBLICADOS)}
        return valores.sorted(lambda v: orden.get(v.name, 99))

    def _medidas_disponibles(self):
        attr = self._attr_catalogo('Medida')
        if not attr:
            return request.env['product.attribute.value']
        return self._es('product.attribute.value').search(
            [('attribute_id', '=', attr.id), ('name', '!=', 'Otro')])

    def _vocabulario(self, modelo):
        """Los catálogos de gemología que ya existen en novadiam."""
        if modelo not in request.env:
            return None
        return request.env[modelo].sudo().search([])

    def _gema_vals(self, post):
        """Los datos gemológicos van a los campos del catálogo de gemas.

        Ya existían y con la escala completa —color D–Z, pureza FL–I3, corte
        EX–P y 13 laboratorios—, capturados en cientos de productos. Este
        módulo llegó a declarar atributos propios con tres rangos gruesos:
        pedirle al vendedor el mismo dato dos veces sólo garantizaba que los
        dos lados se contradijeran. Se quedan los campos, se fueron los
        atributos.
        """
        T = request.env['product.template']
        vals = {}

        origen = ORIGEN_A_CATALOGO.get(post.get('origen'))
        if origen and 'x_studio_origen_c' in T._fields:
            vals['x_studio_origen_c'] = origen

        for campo, modelo, dato in (
                ('x_studio_color_real', 'x_color', post.get('color')),
                ('x_studio_pureza_real', 'x_purezas', post.get('pureza')),
                ('x_studio_corte', 'x_corte', post.get('corte'))):
            if not dato or campo not in T._fields or modelo not in request.env:
                continue
            rec = request.env[modelo].sudo().search(
                [('x_name', '=', dato)], limit=1)
            if rec:
                vals[campo] = rec.id

        # El laboratorio es un many2many al mismo catálogo que usa el taller.
        lab = {'GIA': 'GIA', 'IGI': 'IGI'}.get(post.get('cert_type'))
        if post.get('cert_type') == 'Sin certificado':
            lab = 'Ninguno'
        elif post.get('cert_type') == 'Otra certificadora':
            lab = 'Otro'
        if lab and 'x_studio_certificados' in T._fields:
            rec = self._vocabulario('x_laboratorios_gemolog')
            rec = rec and rec.filtered(lambda r: r.x_name == lab)[:1]
            if rec:
                vals['x_studio_certificados'] = [(6, 0, rec.ids)]
        return vals

    def _acentos_vals(self, post):
        """Los grupos de piedras de acento que declaró el vendedor.

        Un anillo puede llevar 12 de 1.5 mm y 8 de 2 mm; por eso van por grupo
        y no como un solo número. Si el módulo de STIJ no está instalado, el
        campo no existe y esto no se usa.
        """
        if "dmn_accent_ids" not in request.env["product.template"]._fields:
            return []
        grupos = []
        for i in (1, 2, 3):
            n = str(post.get("accent_qty_%d" % i) or "").strip()
            if not n.isdigit() or int(n) <= 0:
                continue
            mm = str(post.get("accent_mm_%d" % i) or "").replace(",", ".").strip()
            grupos.append({
                "qty": int(n),
                "size_mm": float(mm) if mm.replace(".", "", 1).isdigit() else 0.0,
                "stone_type": (post.get("accent_type_%d" % i) or "zirconia").strip(),
            })
        return grupos

    def _laboratorios(self):
        modelo = 'x_laboratorios_gemolog'
        if modelo not in request.env:
            return None
        return request.env[modelo].sudo().search([])

    def _linea_catalogo(self, nombre_attr, nombre_valor):
        """(0,0,vals) amarrando un valor del atributo REAL del catálogo."""
        if not nombre_valor:
            return None
        attr = self._attr_catalogo(nombre_attr)
        if not attr:
            return None
        valor = self._es('product.attribute.value').search(
            [('attribute_id', '=', attr.id), ('name', '=', nombre_valor)],
            limit=1)
        if not valor:
            return None
        return (0, 0, {'attribute_id': attr.id,
                       'value_ids': [(6, 0, [valor.id])]})

    def _get_seller(self, create=False):
        partner = request.env.user.partner_id
        Seller = request.env['marketplace.seller'].sudo()
        seller = Seller.search([('partner_id', '=', partner.id)], limit=1)
        if not seller and create:
            seller = Seller.create({'partner_id': partner.id})
        return seller

    def _attr_line(self, attr_xmlid, value_name):
        """Devuelve (0,0,vals) para amarrar un valor de atributo por nombre."""
        env = request.env
        try:
            attr = env.ref('xb_marketplace.%s' % attr_xmlid).sudo()
        except ValueError:
            return None
        if not value_name:
            return None
        value = self._es('product.attribute.value').search([
            ('attribute_id', '=', attr.id), ('name', '=', value_name)], limit=1)
        if not value:
            return None
        return (0, 0, {'attribute_id': attr.id, 'value_ids': [(6, 0, [value.id])]})

    # ------------------------------------------------------------------
    # Wizard de publicación
    # ------------------------------------------------------------------
    @http.route('/marketplace/vender', type='http', auth='user', website=True,
                methods=['GET'], sitemap=False)
    def vender_form(self, **kw):
        seller = self._get_seller()
        return request.render('xb_marketplace.vender_form', {
            'seller': seller,
            'error': kw.get('error'),
            'metales': self._metales_disponibles(),
            'medidas': self._medidas_disponibles(),
            'laboratorios': self._laboratorios(),
            'colores': self._vocabulario('x_color'),
            'purezas': self._vocabulario('x_purezas'),
            'cortes': self._vocabulario('x_corte'),
        })

    @http.route('/marketplace/vender', type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def vender_submit(self, **post):
        if not post.get('contrato'):
            return request.render('xb_marketplace.vender_form', {
                'seller': self._get_seller(),
                'error': _('Para publicar necesitas aceptar el contrato de '
                           'comisión mercantil.'),
                'values': post,
            })
        seller = self._get_seller(create=True)
        if post.get('city'):
            seller.write({'city': post['city']})

        estilo = post.get('estilo') or 'Otro'
        metal = post.get('metal') or ''
        brand = (post.get('brand') or '').strip()
        try:
            carats = float((post.get('carats') or '0').replace(',', '.'))
        except ValueError:
            carats = 0.0
        try:
            price = float((post.get('price') or '0').replace(',', ''))
        except ValueError:
            price = 0.0

        name_bits = [estilo]
        if brand:
            name_bits.insert(0, brand)
        if carats:
            name_bits.append('%.2f ct' % carats)
        if metal:
            name_bits.append(metal)

        cert_map = {'GIA': 'gia', 'IGI': 'igi', 'Otra certificadora': 'other',
                    'Sin certificado': 'none'}
        cert_type = cert_map.get(post.get('cert_type'), 'unknown')
        # Metal y Medida se amarran a los atributos del catálogo de Anello.
        # Sólo Marca y Estilo siguen siendo atributos propios del marketplace:
        # no tienen equivalente en el catálogo. Color, pureza, corte,
        # laboratorio y origen viajan como campos, no como atributos.
        metal = METALES_ANTERIORES.get(metal, metal)
        medida = (post.get('size') or '').strip()

        attr_lines = []
        for nombre_attr, valor in [('Metal', metal), ('Medida', medida)]:
            linea = self._linea_catalogo(nombre_attr, valor)
            if linea:
                attr_lines.append(linea)

        for xmlid, value in [
            ('attr_estilo', estilo),
            ('attr_marca', brand or 'Sin marca / hechura particular'),
        ]:
            line = self._attr_line(xmlid, value)
            if line:
                attr_lines.append(line)
        # marca capturada que no está en catálogo → "Otra marca"
        if brand and not any(
                l for l in attr_lines
                if l[2]['attribute_id'] == request.env.ref(
                    'xb_marketplace.attr_marca').sudo().id):
            line = self._attr_line('attr_marca', 'Otra marca')
            if line:
                attr_lines.append(line)

        vals = {
            'name': ' · '.join(name_bits) or _('Anillo de compromiso'),
            'nv_is_listing': True,
            'nv_state': 'review',
            'nv_seller_id': seller.id,
            'nv_brand': brand,
            'nv_city': post.get('city'),
            'nv_size': post.get('size'),
            'nv_carats': carats,
            'x_studio_peso_joya': (post.get('peso') or '').strip() or False,
            'nv_cert_type': cert_type,
            'nv_cert_number': post.get('cert_number'),
            'nv_story': post.get('story'),
            'type': 'consu',
            'list_price': price,
            'is_published': False,
            'description_sale': post.get('description'),
            'attribute_line_ids': attr_lines,
            'nv_contract_accept_date': fields.Datetime.now(),
            'nv_contract_version': request.env['ir.config_parameter'].sudo(
                ).get_param('xb_marketplace.contract_version', '2026-07'),
        }
        vals.update(self._gema_vals(post))
        acentos = self._acentos_vals(post)
        if acentos:
            vals["dmn_accent_ids"] = [(0, 0, a) for a in acentos]

        photos = request.httprequest.files.getlist('photos')
        images = []
        for f in photos:
            data = f.read()
            if data:
                images.append(base64.b64encode(data))
        if images:
            vals['image_1920'] = images[0]

        cert_file = request.httprequest.files.get('cert_file')
        if cert_file:
            cert_data = cert_file.read()
            if cert_data:
                vals['nv_cert_file'] = base64.b64encode(cert_data)
                vals['nv_cert_filename'] = cert_file.filename

        listing = request.env['product.template'].sudo().create(vals)
        listing._bind_to_marketplace()

        # La certificadora se guarda además en el catálogo de laboratorios
        # gemológicos que ya usa la pestaña de Gema, para no tener dos listas
        # de laboratorios en el sistema.
        labs = self._laboratorios()
        if labs is not None and 'x_studio_certificados' in listing._fields:
            buscado = {'gia': 'GIA', 'igi': 'IGI'}.get(cert_type)
            if cert_type == 'none':
                buscado = 'Ninguno'
            elif cert_type == 'other':
                buscado = 'Otro'
            lab = labs.filtered(lambda l: (l.x_name or '') == buscado)[:1] if buscado else None
            if lab:
                listing.sudo().write({'x_studio_certificados': [(6, 0, lab.ids)]})
        for extra in images[1:]:
            request.env['product.image'].sudo().create({
                'product_tmpl_id': listing.id,
                'name': listing.name,
                'image_1920': extra,
            })
        listing.message_post(body=_(
            'Anuncio enviado desde el portal por %s.', request.env.user.name))

        return request.render('xb_marketplace.vender_gracias', {'listing': listing})

    # ------------------------------------------------------------------
    # Mis anuncios
    # ------------------------------------------------------------------
    @http.route('/my/anuncios', type='http', auth='user', website=True, sitemap=False)
    def my_listings(self, **kw):
        seller = self._get_seller()
        listings = seller and seller.listing_ids.sudo() or request.env['product.template'].sudo()
        state_labels = dict(
            request.env['product.template']._fields['nv_state']._description_selection(request.env))
        return request.render('xb_marketplace.portal_my_listings', {
            'seller': seller,
            'listings': listings.sorted('create_date', reverse=True),
            'state_labels': state_labels,
            'page_name': 'anuncios',
        })


class MarketplaceBuyerPortal(CustomerPortal):
    """Botones del comprador en el portal de su orden: confirmar recepción
    (libera el escrow de inmediato) o reportar un problema (retiene)."""

    def _nv_order_listings(self, order_id, access_token):
        order = self._document_check_access(
            'sale.order', order_id, access_token)
        listings = order.sudo().order_line.product_id.product_tmpl_id.filtered(
            lambda l: l.nv_is_listing
            and l.nv_state in ('shipped', 'inspection'))
        return order, listings

    @http.route('/marketplace/orden/<int:order_id>/recibido', type='http',
                auth='public', website=True, methods=['POST'], csrf=True)
    def nv_buyer_confirm(self, order_id, access_token=None, **kw):
        try:
            order, listings = self._nv_order_listings(order_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        for listing in listings.filtered(lambda l: not l.nv_disputed):
            try:
                listing.sudo().action_release()
            except UserError as exc:
                # p. ej. factura sin registrar el pago: arranca/da por
                # buena la inspección y el equipo libera manualmente.
                if listing.nv_state == 'shipped':
                    listing.sudo().action_start_inspection()
                listing.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_('Comprador confirmó recepción: liberar manualmente'),
                    note=str(exc))
        order.sudo().message_post(body=_(
            'El comprador confirmó la recepción conforme desde el portal.'))
        return request.redirect(order.get_portal_url())

    @http.route('/marketplace/orden/<int:order_id>/disputa', type='http',
                auth='public', website=True, methods=['POST'], csrf=True)
    def nv_buyer_dispute(self, order_id, access_token=None, motivo=None, **kw):
        try:
            order, listings = self._nv_order_listings(order_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if listings:
            listings.sudo().action_dispute()
            order.sudo().message_post(body=_(
                'El comprador reportó un problema desde el portal: %s',
                motivo or _('(sin detalle)')))
        return request.redirect(order.get_portal_url())
