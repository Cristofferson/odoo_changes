# -*- coding: utf-8 -*-
{
    "name": "XB Agente IA de soporte y ventas por WhatsApp",
    "version": "19.0.1.15.0",
    "summary": "Un agente de IA (Claude) atiende el WhatsApp: soporte revisando el sistema del cliente, ventas y prospectos",
    "description": """
Agente de IA para un número de WhatsApp de Odoo:

* **Clientes** (números autorizados por sistema): revisa SU sistema en solo
  lectura y contesta; si ve un arreglo, lo PROPONE para que un humano lo apruebe.
* **Clientes que quieren comprar más**: registra la oportunidad en el CRM.
* **Prospectos nuevos**: explica los servicios (base de conocimiento editable),
  registra el prospecto y agenda una cita/demo en el calendario.
* Pasa la conversación a una persona cuando no sabe, en temas de dinero, si el
  cliente lo pide o ante una caída grave.

Nace APAGADO y con **modo ensayo**: las respuestas se guardan como nota interna
en la conversación, sin enviarse, hasta que se apague el ensayo.
""",
    "category": "Productivity/WhatsApp",
    "author": "XUBAX",
    "license": "OPL-1",
    "depends": ["whatsapp", "despacho_db_manager", "crm", "calendar", "helpdesk", "resource", "appointment_crm", "xb_whatsapp_web_leads"],
    "external_dependencies": {"python": ["anthropic"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/support_contact_views.xml",
        "views/support_proposal_views.xml",
        "views/support_job_views.xml",
        "views/support_knowledge_views.xml",
        "views/whatsapp_account_views.xml",
        "views/project_project_views.xml",
        "views/xb_resume_views.xml",
        "views/support_service_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
