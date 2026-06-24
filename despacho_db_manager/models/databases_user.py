from odoo import models
from odoo.exceptions import UserError


class DatabasesUser(models.Model):
    """Botón "Conectar" por usuario en la sección Gestión de usuarios: inicia
    sesión en la BD del cliente COMO ese usuario concreto (no solo el admin)."""
    _inherit = 'databases.user'

    def action_autologin_as_user(self):
        self.ensure_one()
        proj = self.project_id
        if not proj or not proj.despacho_autologin_ready:
            raise UserError(
                'Esta base de datos no tiene el auto-login listo todavía '
                '(falta instalar el módulo despacho_autologin o correr el censo).')
        url = proj._despacho_autologin_url(login=self.login)
        if not url:
            raise UserError('No se pudo generar el enlace de conexión para esta base de datos.')
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}
