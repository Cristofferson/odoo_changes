import base64

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class MarketplacePortal(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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
        value = env['product.attribute.value'].sudo().search([
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
        cert_value_name = {'gia': 'GIA', 'igi': 'IGI', 'other': 'Otra',
                           'none': 'Sin certificado'}.get(cert_type)

        attr_lines = []
        for xmlid, value in [
            ('attr_estilo', estilo),
            ('attr_metal', metal),
            ('attr_certificadora', cert_value_name),
            ('attr_origen', post.get('origen')),
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
