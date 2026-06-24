from odoo import fields, models


class DespachoAutologinUsed(models.Model):
    """Nonces ya consumidos: garantiza que un magic-link sea de un solo uso.

    Las filas caducan junto con el token (campo ``expires``) y el controlador
    purga las vencidas en cada acceso, asi que la tabla se mantiene minuscula.
    """
    _name = 'despacho.autologin.used'
    _description = 'Despacho auto-login: nonces consumidos'

    nonce = fields.Char('Nonce', required=True, index=True)
    expires = fields.Datetime('Caduca', required=True, index=True)
