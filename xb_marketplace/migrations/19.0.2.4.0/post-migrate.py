# Las etiquetas en español se guardan aparte (ir_model_fields, clave es_MX) y una
# actualización solo renueva la de inglés: sin esto la pantalla seguiría diciendo
# «Diamante central» y «Acentos» aunque ya incluyan piedras de color y laterales.
ETIQUETAS = {
    'nv_av_diamante': 'Piedra central',
    'nv_av_acentos': 'Laterales y acentos',
    'nv_centro': 'Tipo de piedra central',
}


def migrate(cr, version):
    for campo, texto in ETIQUETAS.items():
        cr.execute("""
            UPDATE ir_model_fields
               SET field_description = field_description || jsonb_build_object('en_US', %s::text, 'es_MX', %s::text)
             WHERE model IN ('product.template', 'product.product') AND name = %s
        """, (texto, texto, campo))
