from odoo import models


class ResUsers(models.Model):
    """Botón "Crear buzón" en la ficha del usuario (res.users), junto a "Crear
    empleado": crea la bandeja humana de correo de ese usuario (cuenta@dominio,
    derivada de su login/correo) reutilizando la maquinaria del alta."""
    _inherit = 'res.users'

    def _mailbox_parts(self):
        """De un login/correo josette@divana.mx -> ('josette', 'divana.mx'). Prefiere
        el login si parece correo; si no, usa el email. Si ninguno sirve, ('', '')."""
        self.ensure_one()
        login = (self.login or '').strip().lower()
        src = login if '@' in login else (self.email or '').strip().lower()
        if '@' in src:
            local, _, dom = src.partition('@')
            return local, dom
        return '', ''

    def action_mailbox_create_user(self):
        """Abre el asistente de "Crear buzón" prellenado desde este usuario."""
        self.ensure_one()
        local, dom = self._mailbox_parts()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Crear buzón para %s' % (self.login or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mailbox_create',
                'default_mail_domain': dom,
                'default_mailbox_accounts': local,
                'default_with_webmail': True,
                'default_simulate': False,
                'dpm_modal': True,
            },
        }
