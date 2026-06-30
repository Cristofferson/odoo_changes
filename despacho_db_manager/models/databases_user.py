import re

from odoo import models, fields
from odoo.exceptions import UserError


class DatabasesUser(models.Model):
    """Gestión de usuarios por BD. Además del botón "Conectar" (auto-login como ese
    usuario), cada fila puede tener su PROPIO puente MCP: la IA del usuario consulta
    su Odoo con LOS MISMOS PRIVILEGIOS que ese usuario (un contenedor por usuario)."""
    _inherit = 'databases.user'

    # Estatus del puente MCP de ESTE usuario (lo llena el censo leyendo los .env de
    # /opt/odoo-mcp/clients; cada .env trae su CONN_USER y su ODOO_DB).
    despacho_mcp_enabled = fields.Boolean('MCP', default=False, copy=False,
        help='Este usuario tiene un puente MCP propio: su IA puede consultar la BD '
             'con sus mismos privilegios.')
    despacho_mcp_slug = fields.Char('Endpoint MCP (id)', copy=False)
    despacho_mcp_url = fields.Char('Endpoint MCP', copy=False)
    despacho_mcp_status = fields.Char('Estado MCP', copy=False)
    despacho_mcp_writes = fields.Boolean('MCP escribe', copy=False)
    despacho_mcp_port = fields.Char('Puerto MCP', copy=False)
    despacho_mcp_health = fields.Char('Sondeo MCP', copy=False)
    despacho_mcp_oauth = fields.Boolean('MCP OAuth', copy=False,
        help='El puente de este usuario usa login OAuth (Cloudflare Access, '
             'compatible con ChatGPT) en su subdominio propio, en vez de token Bearer.')

    def _mcp_user_email(self):
        """Correo sugerido para el login OAuth: el login si parece un correo (lo más
        común en Odoo). Si no, vacío y el gestor lo escribe en el asistente."""
        self.ensure_one()
        login = (self.login or '').strip()
        return login if '@' in login else ''

    def _mcp_user_slug(self):
        """Slug del endpoint para ESTE usuario: <bd>-<usuario>, URL-safe (2-31).
        Ej: divana + josette@divana.mx -> 'divana-josette'."""
        self.ensure_one()
        base = self.project_id._mcp_slug_suggestion() if self.project_id else 'cliente'
        local = re.split(r'[@+]', (self.login or '').lower())[0]
        local = re.sub(r'[^a-z0-9-]', '', local)[:20] or 'user'
        slug = ('%s-%s' % (base, local))[:31].strip('-')
        return slug or 'cliente-user'

    def _mailbox_parts(self):
        """De un login josette@divana.mx -> ('josette', 'divana.mx'). Si el login no
        es un correo, devuelve ('', '') y el gestor escribe cuenta/dominio a mano."""
        self.ensure_one()
        login = (self.login or '').strip().lower()
        if '@' in login:
            local, _, dom = login.partition('@')
            return local, dom
        return '', ''

    def action_mailbox_create_user(self):
        """Crea el buzón humano de ESTE usuario (<cuenta>@<dominio>, derivado de su
        login) + webmail opcional, reutilizando la maquinaria del alta. Abre el
        asistente prellenado para revisar antes de aplicar."""
        self.ensure_one()
        proj = self.project_id
        local, dom = self._mailbox_parts()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Crear buzón para %s' % (self.login or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mailbox_create',
                'default_project_id': proj.id if proj else False,
                'default_mail_domain': dom,
                'default_mailbox_accounts': local,
                'default_with_webmail': True,
                'default_simulate': False,
                'dpm_modal': True,
            },
        }

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

    def action_mcp_add_user(self):
        """Activa un puente MCP PROPIO para este usuario (conecta como él, espejo de
        privilegios, con escrituras). Abre el asistente prellenado."""
        self.ensure_one()
        proj = self.project_id
        if not proj:
            raise UserError('Este usuario no está ligado a una base de datos.')
        if proj.despacho_server not in ('odoo19', 'odoo18'):
            raise UserError('El puente MCP solo se activa en bases de ESTE servidor '
                            '(odoo19) o de OVH (odoo18). Esta está en %s.'
                            % (proj.despacho_server or '¿?'))
        if self.despacho_mcp_enabled:
            raise UserError('Este usuario ya tiene un puente MCP activo. Quítalo antes '
                            'de volver a activarlo.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activar MCP para %s' % (self.login or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mcp_add',
                'default_project_id': proj.id,
                'default_mcp_slug': self._mcp_user_slug(),
                'default_mcp_as_user': self.login,
                'default_mcp_writes': True,
                'default_simulate': False,
                'dpm_modal': True,
            },
        }

    def action_mcp_remove_user(self):
        """Desactiva el puente MCP de este usuario. Abre el asistente prellenado."""
        self.ensure_one()
        proj = self.project_id
        slug = self.despacho_mcp_slug or self._mcp_user_slug()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Desactivar MCP de %s' % (self.login or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mcp_remove',
                'default_project_id': proj.id if proj else False,
                'default_mcp_slug': slug,
                'default_mcp_purge_key': True,
                'default_mcp_oauth': bool(self.despacho_mcp_oauth),
                'dpm_modal': True,
            },
        }

    def action_mcp_oauth_add_user(self):
        """Activa un puente MCP por OAuth (Cloudflare Access) para este usuario:
        subdominio propio + login por correo, compatible con ChatGPT y Claude web."""
        self.ensure_one()
        proj = self.project_id
        if not proj:
            raise UserError('Este usuario no está ligado a una base de datos.')
        if proj.despacho_server not in ('odoo19', 'odoo18'):
            raise UserError('El puente MCP solo se activa en bases de ESTE servidor '
                            '(odoo19) o de OVH (odoo18). Esta está en %s.'
                            % (proj.despacho_server or '¿?'))
        if self.despacho_mcp_enabled:
            raise UserError('Este usuario ya tiene un puente MCP activo. Quítalo antes '
                            'de volver a activarlo.')
        # Tanto local (odoo19) como OVH (odoo18) soportan OAuth: el contenedor corre
        # en este box; para OVH apunta al Odoo remoto por xmlrpc (oauth-enable.sh
        # --remote ovh). Se pre-marca OAuth (compatible con ChatGPT/Claude web) en ambos.
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activar MCP para %s' % (self.login or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mcp_add',
                'default_project_id': proj.id,
                'default_mcp_slug': self._mcp_user_slug(),
                'default_mcp_as_user': self.login,
                'default_mcp_writes': True,
                'default_mcp_oauth': True,
                'default_mcp_email': self._mcp_user_email(),
                'default_simulate': False,
                'dpm_modal': True,
            },
        }
