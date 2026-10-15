A=env['whatsapp.account'].sudo().browse(2); X=env['whatsapp.account'].sudo().browse(3)
assert A.name=='Anello' and X.name=='XUBAX'
txt=open('/home/ubuntu/xbsa_work/anello/instrucciones.txt',encoding='utf-8').read().strip()
# La base de conocimiento sin cuenta aplicaba a todos los números: se queda solo con XUBAX.
Kn=env['xb.support.knowledge'].sudo()
libres=Kn.search([('account_ids','=',False)])
libres.write({'account_ids':[(6,0,X.ids)]})
jacky=env['res.users'].sudo().browse(13); assert 'jacky@anello.mx'==jacky.login
A.write({
 'xb_sa_profile':'tienda','xb_sa_company_name':'Anello','xb_sa_instructions':txt,
 'xb_sa_api_key':X.xb_sa_api_key,'xb_sa_openai_key':X.xb_sa_openai_key,
 'xb_sa_model':X.xb_sa_model,'xb_sa_effort':X.xb_sa_effort,
 'xb_sa_support_user_ids':[(6,0,jacky.ids)],'xb_sa_sales_user_ids':[(6,0,jacky.ids)],'xb_sa_demo_user_ids':[(6,0,jacky.ids)],
 'xb_sa_appointment_type_id':5,'xb_sa_pause_hours':3,
 'xb_sa_hold_message':'Gracias por escribir a Anello 💍. Ya avisé a una persona de la tienda y te contestará lo antes posible (atendemos todos los días de 8:00 a 21:00).',
 'xb_sa_only_numbers':False,'xb_offhours_enabled':False,'xb_sa_shadow':False,'xb_sa_enabled':True,
})
env.cr.commit()
print('OK', len(libres),'conocimientos asignados a XUBAX;', A.xb_sa_profile, A.xb_sa_enabled, A.xb_sa_shadow, A.xb_sa_only_numbers, 'llave:', 'sí' if A.xb_sa_api_key else 'NO')
