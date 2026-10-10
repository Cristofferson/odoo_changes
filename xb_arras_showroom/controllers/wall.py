# -*- coding: utf-8 -*-
import logging

from odoo.addons.xb_showroom_wall.controllers.wall import STAMP_FILES, ShowroomWall, _money, _shop_pricelist

_logger = logging.getLogger(__name__)

# Si cambia el dibujo de las arras, el muro se recarga solo (el sello va en /state).
STAMP_FILES.extend([
    'xb_arras_showroom/static/src/wall_arras.css',
    'xb_arras_showroom/static/src/wall_arras.js',
])


class ArrasWall(ShowroomWall):

    def _wall_plugins(self, screen):
        return super()._wall_plugins(screen) + [{
            'css': '/xb_arras_showroom/static/src/wall_arras.css',
            'js': '/xb_arras_showroom/static/src/wall_arras.js',
        }]

    def _piece_dict(self, screen, product, base, price='', qr=None, options=None, slot=None):
        piece = super()._piece_dict(screen, product, base, price=price, qr=qr, options=options, slot=slot)
        tmpl = product.product_tmpl_id
        if tmpl.xb_arras:
            try:
                piece['arras'] = tmpl.sudo().with_company(screen.company_id)._xb_arras_muro(
                    _shop_pricelist(screen).with_company(screen.company_id),
                    (options or product.product_template_attribute_value_ids).sudo(),
                    screen.company_id, _money)
            except Exception:  # noqa: BLE001 - unas arras mal capturadas no deben dejar el muro en blanco
                _logger.exception('[ARRAS] no se pudo armar la pantalla de %s', tmpl.id)
        return piece
