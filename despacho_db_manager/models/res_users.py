from odoo import api, fields, models
from odoo.exceptions import UserError

from . import mailbox_util


class ResUsers(models.Model):
    """Botón "Crear buzón" en la ficha del usuario (res.users), junto a "Crear
    empleado": crea la bandeja humana de correo de ese usuario (cuenta@dominio,
    derivada de su login/correo) reutilizando la maquinaria del alta. Solo se
    ofrece si el buzón NO existe y SÍ hospedamos el dominio."""
    _inherit = 'res.users'

    despacho_mailbox_state = fields.Char(
        compute='_compute_despacho_mailbox_state',
        help="Estado del buzón de correo de este usuario en nuestro servidor: "
             "'exists' (ya existe), 'can' (se puede crear), 'cannot' (no hay dominio "
             "que hospedemos para él).")

    @api.depends('login', 'email')
    def _compute_despacho_mailbox_state(self):
        domains = mailbox_util.hosted_domains()
        boxes = mailbox_util.existing_mailboxes()
        for user in self:
            local, dom = mailbox_util.mailbox_parts(user.login, user.email)
            user.despacho_mailbox_state = mailbox_util.mailbox_state(
                local, dom, domains, boxes)

    def _mailbox_parts(self):
        self.ensure_one()
        return mailbox_util.mailbox_parts(self.login, self.email)

    def action_mailbox_create_user(self):
        """Abre el asistente de "Crear buzón" prellenado desde este usuario."""
        self.ensure_one()
        local, dom = self._mailbox_parts()
        state = mailbox_util.mailbox_state(local, dom)
        if state == 'exists':
            raise UserError('Este usuario ya tiene el buzón %s@%s en el servidor. '
                            'No hay nada que crear.' % (local, dom))
        if state == 'cannot':
            raise UserError(
                'No hay manera de crear un buzón para este usuario: su login/correo '
                'no apunta a un dominio de correo que hospedemos en el servidor.')
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
