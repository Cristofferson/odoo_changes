# odoo shell < oro_suelto_fix.py — 5-oct: «Oro suelto por gramo» sale de la lista «Costo Oro» (XAU): sus renglones viejos de gramos
#  hacían que la tarea «XUBAX: Refrescar precio ORO en POS» le congelara cada noche un precio FIJO ($0) en Anello (Retail),
#  que le ganaba a la regla «costo + 8 %». Ahora su precio sale solo del costo del día + 8 %.
Item = env['product.pricelist.item']
cost_pls = env['product.pricelist'].search([('currency_id.name', 'in', ['XAU', 'XAG', 'XPT'])])
tm = env['product.template'].search([('name', 'in', ['Oro suelto por gramo', 'Plata suelta por gramo', 'Platino suelto por gramo'])])
viejos = Item.search([('pricelist_id', 'in', cost_pls.ids), '|', ('product_tmpl_id', 'in', tm.ids), ('product_id.product_tmpl_id', 'in', tm.ids)])
print('renglones en listas de metal', len(viejos)); viejos.unlink()
fijos = Item.search([('pricelist_id', 'not in', cost_pls.ids), ('compute_price', '=', 'fixed'), '|', ('product_tmpl_id', 'in', tm.ids), ('product_id.product_tmpl_id', 'in', tm.ids)])
print('reglas fijas borradas', [(f.id, f.pricelist_id.name, f.fixed_price) for f in fijos]); fijos.unlink()
print('reglas que quedan', [(r.pricelist_id.name, r.product_tmpl_id.name, r.compute_price, r.base, r.price_markup) for r in Item.search([('product_tmpl_id', 'in', tm.ids)])])
env.cr.commit()
