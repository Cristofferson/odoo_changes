# odoo shell -d <BD> < configurar_tienda.py — anello.mx: vender sin existencias + plata oculta en web + regla ×2 por categoría. Idempotente.
DB = env.cr.dbname
T = env['product.template'].sudo()
# 1) «Seguir vendiendo» (nativo website_sale_stock) en los anillos publicados con nombre italiano («Ciudad · Estilo»)
italianos = T.search([('is_published', '=', True), ('website_id', 'in', [1, False]), ('name', 'like', '·')])
cambiar = italianos.filtered(lambda t: not t.allow_out_of_stock_order)
cambiar.write({'allow_out_of_stock_order': True})
# 2) Plata oculta en la tienda en línea (sigue en caja y Ventas)
plata = env['product.attribute.value'].sudo().search([('attribute_id', '=', 9), ('name', 'ilike', 'plata'),
                                                       ('name', 'not ilike', 'imitaci')])
plata.write({'xb_ocultar_web': True})
# 3) Regla ×2 por categoría (nativa) para que los anillos NUEVOS nazcan con precio: Montadura (86) y Argolla (60)
Item = env['product.pricelist.item'].sudo()
for categ_id in (86, 60):
    if not Item.search([('pricelist_id', '=', 2), ('applied_on', '=', '2_product_category'), ('categ_id', '=', categ_id),
                        ('base', '=', 'standard_price')]):
        Item.create({'pricelist_id': 2, 'applied_on': '2_product_category', 'categ_id': categ_id,
                     'compute_price': 'formula', 'base': 'standard_price', 'price_markup': 100.0})
env.cr.commit()
print('OK', DB, 'italianos', len(italianos), 'activados', len(cambiar), '| plata oculta:', plata.mapped('name'))
