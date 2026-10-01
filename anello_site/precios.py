# odoo shell -d <BD> < precios.py — precio de los anillos «por metal» = costo × 2, web con IVA incluido. Idempotente.
#   costo = metal fino del día × precio del oro + lista de materiales (hechura y piedras)
#   Antes: lista 2 «Anello (Retail)», regla base Costo con +226 % (= ×3.26).
import json, os
DB = env.cr.dbname
D = '/opt/odoo/anbn_tmp/'
PL = env['product.pricelist'].sudo().browse(2)
assert PL.name in ('Anello (Retail)', 'Predeterminado'), PL.name
Item = env['product.pricelist.item'].sudo()
T = env['product.template'].sudo().with_context(active_test=True)
anillos = T.search([('xb_precio_por_metal', '=', True)])

# respaldo (1a vez)
bk = D + 'respaldo_precios_%s.json' % DB
reglas = Item.search([('pricelist_id', '=', PL.id), ('base', '=', 'standard_price'), ('product_tmpl_id', 'in', anillos.ids)])
if not os.path.exists(bk):
    json.dump({'reglas': [(r.id, r.product_tmpl_id.id, r.price_markup, r.price_discount) for r in reglas],
               'impuestos': {t.id: t.taxes_id.ids for t in anillos},
               'web_iva': env['website'].browse(1).show_line_subtotals_tax_selection}, open(bk, 'w'))

# 1) ×2 = costo + 100 %
reglas.write({'price_markup': 100.0})
faltan = anillos.filtered(lambda t: t.id not in reglas.mapped('product_tmpl_id').ids)
for t in faltan:
    Item.create({'pricelist_id': PL.id, 'applied_on': '1_product', 'product_tmpl_id': t.id,
                 'compute_price': 'formula', 'base': 'standard_price', 'price_markup': 100.0})

# 2) impuestos: los que traían impuesto de COMPRA en «impuestos de cliente» → IVA 16 % de venta
iva = env['account.tax'].sudo().browse(12)
assert iva.type_tax_use == 'sale' and iva.amount == 16, iva
mal = anillos.filtered(lambda t: any(x.type_tax_use == 'purchase' for x in t.taxes_id) or not t.taxes_id)
mal.write({'taxes_id': [(6, 0, [iva.id])]})

# 3) anello.mx muestra precios con IVA incluido
env['website'].browse(1).show_line_subtotals_tax_selection = 'tax_included'
env.cr.commit()

# muestra: las 4 ventas reales con la regla nueva
for name in ('S00213', 'S00220', 'S00197', 'S00257'):
    so = env['sale.order'].search([('name', '=', name)])
    for l in so.order_line.filtered(lambda l: l.product_id.product_tmpl_id.xb_precio_por_metal):
        ptavs = l.product_id.product_template_attribute_value_ids | l.product_no_variant_attribute_value_ids
        p = PL._get_product_price(l.product_id.with_context(xb_combinacion=tuple(ptavs.ids)), 1.0)
        print('%s %-30s mostrador %9.2f | web nuevo %9.2f + IVA = %9.2f' % (name, l.product_id.product_tmpl_id.name[:30], l.price_unit, p, p * 1.16))
print('OK', DB, 'reglas', len(reglas), 'nuevas', len(faltan), 'impuestos corregidos', len(mal))
