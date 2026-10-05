# Tamaños pedidos en la revisión del 5-oct. Costo: el del redondo del mismo tamaño o, si no existe, interpolado.
env = env(context=dict(env.context, allowed_company_ids=[3]))
PP = env['product.product']
def redondo(tipo, qt):
    return PP.search([('name', '=like', 'Diamante %s %sQts %%' % (tipo, qt)), ('name', 'not ilike', 'Baguette'),
                      ('name', 'not ilike', 'Princesa'), ('name', 'not ilike', 'Marquesa')], limit=1)
COSTO = {('LAB', '0.10'): 449.47, ('NAT', '0.10'): 1566.35, ('LAB', '0.0075'): 25.54, ('NAT', '0.0075'): 86.83}
for qt, forma in (('0.06', 'Princesa'), ('0.05', 'Baguette'), ('0.10', 'Princesa'), ('0.0075', '')):
    for tipo in ('LAB', 'NAT'):
        base = redondo(tipo, qt)
        plantilla = base or redondo(tipo, '0.08')
        nombre = ('Diamante %s %sQts SI1 G VG' % (tipo, qt)) + (' ' + forma if forma else '')
        p = PP.search([('name', '=', nombre)], limit=1)
        if not p:
            p = plantilla.product_tmpl_id.copy({'name': nombre}).product_variant_id
        p.standard_price = base.standard_price if base else COSTO[(tipo, qt)]
        print(p.id, p.name, p.standard_price)
env.cr.commit()
