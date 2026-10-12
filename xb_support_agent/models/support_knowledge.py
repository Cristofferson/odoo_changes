# -*- coding: utf-8 -*-
from odoo import fields, models


class XbSupportKnowledge(models.Model):
    """Lo que el agente sabe de la empresa: servicios, precios «desde», preguntas
    frecuentes y reglas. Se edita desde Odoo; el agente lo lee en cada plática."""
    _name = "xb.support.knowledge"
    _description = "Base de conocimiento del agente de WhatsApp"
    _order = "kind, sequence, id"

    name = fields.Char("Título", required=True)
    kind = fields.Selection([
        ("service", "Servicio"),
        ("price", "Precio «desde»"),
        ("faq", "Pregunta frecuente"),
        ("policy", "Regla o política"),
    ], string="Tipo", required=True, default="faq")
    content = fields.Text("Contenido", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    account_ids = fields.Many2many(
        "whatsapp.account", string="Números",
        help="Vacío = aplica a todos los números con agente.")

    def _xb_as_text(self):
        titulos = dict(self._fields["kind"].selection)
        partes = []
        for kind, titulo in titulos.items():
            items = self.filtered(lambda r: r.kind == kind)
            if not items:
                continue
            partes.append(f"## {titulo}")
            partes += [f"### {r.name}\n{r.content.strip()}" for r in items]
        return "\n\n".join(partes)
