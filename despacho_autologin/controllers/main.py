import base64
import hashlib
import hmac
import json
import logging
import time

from datetime import datetime, timezone

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _b64d(data):
    """Decodifica base64url tolerando el padding omitido."""
    if isinstance(data, str):
        data = data.encode('ascii')
    return base64.urlsafe_b64decode(data + b'=' * (-len(data) % 4))


class DespachoAutologin(http.Controller):
    """Magic-link de inicio de sesion para el despacho.

    El manager firma ``payload.signature`` con el secreto de ESTA BD
    (``ir.config_parameter`` ``despacho_autologin.secret``). Aqui se valida la
    firma, la caducidad y la unicidad del nonce antes de abrir la sesion.
    Cualquier fallo cae al login normal: nunca se inicia sesion con un token
    invalido.
    """

    def _resolve_user(self, uid=0):
        """Devuelve el usuario con el que iniciar sesión, o un recordset vacío.

        Orden (compatible Odoo 18 y 19 vía ``has_group``):
        1. ``uid`` explícito del token (si activo e interno).
        2. ``base.user_admin`` (el admin canónico, normalmente uid 2) si está
           activo, es interno y pertenece al grupo Ajustes (``group_system``).
        3. El usuario interno activo de MENOR id que sea admin (group_system).
        4. El usuario interno activo de menor id (último recurso).
        """
        # Entorno sudo: el usuario público no puede leer res.users / grupos /
        # ir.model.data, así que toda la resolución va con privilegios.
        env = request.env(su=True)
        Users = env['res.users']
        if uid:
            u = Users.browse(uid)
            return u if (u.exists() and u.active and u._is_internal()) else Users.browse()

        candidates = Users.search(
            [('active', '=', True), ('id', '>', 1)], order='id'
        ).filtered(lambda u: u._is_internal())
        if not candidates:
            return Users.browse()

        admin = env.ref('base.user_admin', raise_if_not_found=False)
        if admin and admin.id in candidates.ids and admin.has_group('base.group_system'):
            return admin
        for u in candidates:
            if u.has_group('base.group_system'):
                return u
        return candidates[:1]

    @http.route('/despacho/autologin', type='http', auth='public',
                methods=['GET'], csrf=False, sitemap=False)
    def autologin(self, token=None, **kw):
        login_page = request.redirect('/web/login')

        secret = request.env['ir.config_parameter'].sudo().get_param(
            'despacho_autologin.secret')
        if not token or not secret or '.' not in token:
            return login_page

        payload_b64, _, sig_b64 = token.partition('.')

        # 1) Firma HMAC-SHA256 sobre la cadena payload tal cual se transmite.
        expected = hmac.new(secret.encode(), payload_b64.encode(),
                            hashlib.sha256).digest()
        try:
            given = _b64d(sig_b64)
        except Exception:
            return login_page
        if not hmac.compare_digest(expected, given):
            return login_page

        # 2) Payload valido y no caducado.
        try:
            payload = json.loads(_b64d(payload_b64))
        except Exception:
            return login_page
        now = int(time.time())
        if int(payload.get('exp', 0)) < now:
            return login_page
        nonce = payload.get('nonce')
        uid = int(payload.get('uid') or 0)
        if not nonce:
            return login_page

        # 3) Un solo uso: purga vencidos y rechaza nonce repetido.
        Used = request.env['despacho.autologin.used'].sudo()
        Used.search([('expires', '<', fields.Datetime.now())]).unlink()
        if Used.search_count([('nonce', '=', nonce)]):
            return login_page
        Used.create({
            'nonce': nonce,
            'expires': datetime.fromtimestamp(
                int(payload.get('exp', now)), timezone.utc).replace(tzinfo=None),
        })

        # 4) Usuario destino: si el token trae uid explícito se respeta; si no,
        #    se RESUELVE el administrador real de ESTA BD (uid 2 no siempre es el
        #    admin: puede estar inactivo o no pertenecer al grupo Ajustes).
        user = self._resolve_user(uid)
        if not user:
            return login_page

        # 5) Abrir sesion sin contraseña (mismo camino que el login normal
        #    tras validar credenciales): se rellenan pre_login/pre_uid y se
        #    finaliza la sesion, que calcula el session_token.
        request.session['pre_login'] = user.login
        request.session['pre_uid'] = user.id
        request.session.finalize(request.env)
        request.session.should_rotate = True

        _logger.info('Despacho auto-login: usuario %s (uid %s) en BD %s',
                    user.login, user.id, request.db)
        return request.redirect('/odoo')
