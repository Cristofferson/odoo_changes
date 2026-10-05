# Diamantes de acento con forma (baguette, princesa, marquesa): copia del redondo del mismo tamaño, mismo costo.
env = env(context=dict(env.context, allowed_company_ids=[3]))
PP = env['product.product']
FORMAS = {'Baguette': ['0.08', '0.13'], 'Princesa': ['0.04', '0.05', '0.08'], 'Marquesa': ['0.08']}
for forma, tams in FORMAS.items():
    for qt in tams:
        for tipo in ('LAB', 'NAT'):
            base = PP.search([('name', '=like', 'Diamante %s %sQts %%' % (tipo, qt)), ('name', 'not ilike', 'Baguette'),
                              ('name', 'not ilike', 'Princesa'), ('name', 'not ilike', 'Marquesa')], limit=1)
            assert base, (tipo, qt)
            nombre = '%s %s' % (base.name, forma)
            p = PP.search([('name', '=', nombre)], limit=1)
            if not p:
                p = base.product_tmpl_id.copy({'name': nombre}).product_variant_id
            p.standard_price = base.standard_price
            print(p.id, p.name, p.standard_price)
env.cr.commit()
