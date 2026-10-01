# odoo shell -d <BD> < configurar_wa.py — WhatsApp de Anello (cuenta 2, website 1). Idempotente.
#   1) prospectos desde el sitio / anuncios  2) aviso fuera de horario 8-21  5) plantilla de carrito abandonado
# Variable SUBMIT_META = True solo en producción: manda la plantilla nueva a revisión de Meta.
import os
DB = env.cr.dbname
SUBMIT_META = DB == 'novadiam-anello-diamane-xubax'
W = env['website'].sudo().browse(1)
ACC = env['whatsapp.account'].sudo().browse(2)
assert W.name == 'Anello' and ACC.name == 'Anello', (W.name, ACC.name)
JACKY = env['res.users'].sudo().browse(13)

# --- 1) prospectos ------------------------------------------------------------
Tag = env['crm.tag'].sudo()
def tag(n):
    return Tag.search([('name', '=', n)], limit=1) or Tag.create({'name': n})
W.write({'xb_wa_leads_enabled': True, 'xb_wa_lead_user_id': JACKY.id,
         'xb_wa_lead_tag_web_id': tag('WhatsApp · Sitio web').id,
         'xb_wa_lead_tag_ad_id': tag('WhatsApp · Anuncio').id})

# --- 2) aviso fuera de horario (xb_whatsapp_autoreply, ya instalado) ----------
Cal = env['resource.calendar'].sudo()
cal = Cal.search([('name', '=', 'Atención WhatsApp Anello')], limit=1)
att = [(5, 0, 0)] + [(0, 0, {'name': d, 'dayofweek': str(i), 'hour_from': 8.0, 'hour_to': 21.0, 'day_period': 'full_day'})
                     for i, d in enumerate(['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'])]
cvals = {'name': 'Atención WhatsApp Anello', 'tz': 'America/Mexico_City', 'company_id': 3, 'attendance_ids': att}
if cal: cal.write(cvals)
else: cal = Cal.create(cvals)
ACC.write({
    'xb_autoreply_enabled': True,
    'xb_welcome_enabled': False,          # sin saludo/menú: solo el aviso fuera de horario
    'xb_escalate_enabled': False,
    'xb_lead_enabled': False,             # los prospectos los hace xb_whatsapp_web_leads
    'xb_offhours_enabled': True, 'xb_offhours_cooldown_hours': 12, 'xb_calendar_id': cal.id,
    'xb_offhours_body': '¡Gracias por escribir a Anello! 💍 En este momento estamos fuera de horario. '
                        'Te contestamos a partir de las 8:00 (atendemos por WhatsApp todos los días de 8:00 a 21:00). '
                        'Si quieres, déjanos tu pregunta y qué anillo te interesa para tenerte la respuesta lista.\n\n'
                        'También puedes agendar una cita, presencial o virtual: https://www.anello.mx/appointment',
})

# --- 5) plantilla de carrito abandonado ----------------------------------------
T = env['whatsapp.template'].sudo()
tpl = T.search([('template_name', '=', 'carrito_anello'), ('wa_account_id', '=', ACC.id)], limit=1)
if not tpl:
    tpl = T.create({
        'name': 'Carrito abandonado Anello', 'template_name': 'carrito_anello', 'wa_account_id': ACC.id,
        'model_id': env['ir.model']._get_id('sale.order'), 'phone_field': 'partner_id.phone', 'lang_code': 'es_MX', 'template_type': 'marketing',
        'body': 'Hola {{1}}, vimos que dejaste el anillo {{2}} en tu carrito de Anello. 💍\n\n'
                '¿Te ayudamos a elegir la medida, el metal o la piedra? Contéstanos aquí y con gusto te asesoramos.\n\n'
                'Puedes verlo de nuevo aquí: {{3}} — te esperamos. ✨',
        'variable_ids': [(5, 0, 0),
                         (0, 0, {'name': '{{1}}', 'line_type': 'body', 'field_type': 'field', 'field_name': 'partner_id.name', 'demo_value': 'Ana'}),
                         (0, 0, {'name': '{{2}}', 'line_type': 'body', 'field_type': 'field', 'field_name': 'xb_wa_cart_product', 'demo_value': 'Ravello · Trilogía princesa'}),
                         (0, 0, {'name': '{{3}}', 'line_type': 'body', 'field_type': 'field', 'field_name': 'xb_wa_cart_url', 'demo_value': 'https://www.anello.mx/shop/2838'})],
    })
if 'Puedes retomarlo en: {{3}}' in (tpl.body or '') and tpl.status in ('draft', 'rejected'):
    tpl.body = tpl.body.replace('Puedes retomarlo en: {{3}}', 'Puedes verlo de nuevo aquí: {{3}} — te esperamos. ✨')
env.cr.commit()   # lo anterior (prospectos y fuera de horario) queda guardado pase lo que pase con Meta
if SUBMIT_META and tpl.status == 'draft':
    try:
        tpl.button_submit_template()
    except Exception as e:  # noqa: BLE001
        env.cr.rollback()
        print('⚠️ Meta no aceptó la plantilla:', str(e)[:200])
W.write({'xb_wa_cart_template_id': tpl.id if tpl.status == 'approved' else False,
         'xb_wa_cart_enabled': True, 'xb_wa_cart_delay_hours': 3})
env.cr.commit()
print('OK', DB, 'calendario', cal.id, 'plantilla', tpl.id, tpl.status, 'enviada a Meta' if SUBMIT_META else '(prueba: NO se manda a Meta)')
