# odoo shell < diamantes_serie.py — 3-oct: los 5 diamantes LAB centrales llevan inventario y NÚMERO DE SERIE (uno por piedra → su ICERT).
T = env['product.template']
ds = T.search([('name', 'like', 'Diamante LAB %Qts VVS2 E ID')])
ds.write({'is_storable': True, 'tracking': 'serial'})
env.cr.commit()
for t in ds: print(t.id, t.name, t.type, t.is_storable, t.tracking)
