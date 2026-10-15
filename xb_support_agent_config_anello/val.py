import datetime
co = env["res.company"].sudo().browse(3); assert co.name == "Anello"
co.quotation_validity_days = 10
so = env["sale.order"].sudo().browse(373); assert so.state == "draft" and so.company_id.id == 3
so.validity_date = so.create_date.date() + datetime.timedelta(days=10)
env.cr.commit()
print("OK validez compañía", co.quotation_validity_days, "S00373 vence", so.validity_date)
