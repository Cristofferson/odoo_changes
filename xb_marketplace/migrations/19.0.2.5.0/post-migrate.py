def migrate(cr, version):
    # Las montaduras de referencia de Halo y Pavé (Cefalú con pavé) ya traen sus piedras chicas.
    cr.execute("UPDATE nv_avaluo_estilo SET montadura_trae_pave = TRUE WHERE name IN ('Halo', 'Pavé')")
