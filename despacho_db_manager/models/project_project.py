import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import socket
import time

from odoo import api, fields, models
from odoo.exceptions import UserError

from .db_operation import CENSUS_DB_RE, SERVER_KEYS

_logger = logging.getLogger(__name__)

# Nombre LÓGICO de cada servidor, mapeado desde el hostname del SO. El hostname
# real NO se cambia (diamane.mx corre correo; renombrarlo sería riesgoso); el
# módulo usa estos nombres lógicos en toda su lógica e inventario.
HOSTNAME_TO_KEY = {'diamane.mx': 'odoo19', 'vps-f101b860': 'odoo18'}
# Clave de ESTE servidor: distingue las BDs locales (que el worker local sí puede
# operar) de las registradas de otros servidores.
THIS_SERVER = HOSTNAME_TO_KEY.get(socket.gethostname(), socket.gethostname())


def _human_size(num):
    if not num:
        return '0 B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(num) < 1024.0:
            return '%3.1f %s' % (num, unit)
        num /= 1024.0
    return '%.1f PB' % num


class ProjectProject(models.Model):
    _inherit = 'project.project'

    despacho_db_local = fields.Boolean(
        'BD en este servidor', default=False, copy=False,
        help='Marcada por el censo: la BD vive en %s y el worker local puede operarla.' % THIS_SERVER)
    despacho_server = fields.Char('Servidor', copy=False,
                                  help='Hostname del servidor donde vive la BD.')
    # Float (double precision), no Integer: el filestore/BD de clientes grandes
    # supera el máximo de int4 de Postgres (~2.15 GB) y desbordaría.
    despacho_db_size = fields.Float('Tamaño BD (bytes)', copy=False, aggregator='sum')
    despacho_filestore_size = fields.Float('Tamaño filestore (bytes)', copy=False, aggregator='sum')
    # Totales almacenados: sirven de medida en las vistas de gráfico/pivot del
    # tablero (un campo computado NO almacenado no se puede agregar en read_group).
    despacho_total_size = fields.Float('Tamaño total (bytes)', copy=False,
                                       compute='_compute_total_size', store=True, aggregator='sum')
    despacho_total_size_gb = fields.Float('Tamaño total (GB)', copy=False,
                                          compute='_compute_total_size', store=True, aggregator='sum',
                                          help='Tamaño total (BD + filestore) en GB, para el tablero.')
    despacho_size_display = fields.Char('Tamaño', compute='_compute_size_display')
    # Salud del respaldo (no almacenada: depende de la fecha actual). Se evalúa
    # al leer; el tablero la usa para colorear y filtrar.
    despacho_days_since_backup = fields.Integer(
        'Días sin respaldo', compute='_compute_backup_health',
        help='Días transcurridos desde el último respaldo. -1 = nunca se ha respaldado.')
    despacho_backup_status = fields.Selection([
        ('never', 'Sin respaldo'),
        ('ok', 'Al día'),
        ('warn', 'Atención'),
        ('late', 'Atrasado'),
    ], string='Estado de respaldo', compute='_compute_backup_health')
    despacho_user_count = fields.Integer(
        'Usuarios', copy=False, aggregator='sum',
        help='Usuarios internos activos (personas que inician sesión, share=false). '
             'Lo llena el censo.')
    despacho_user_total = fields.Integer(
        'Usuarios (total activos)', copy=False, aggregator='sum',
        help='Todos los usuarios activos: internos + portal/externos. Lo llena el censo.')
    despacho_installed_modules = fields.Text('Módulos instalados', copy=False)
    despacho_custom_modules = fields.Text(
        'Apps custom', copy=False,
        help='Módulos custom instalados (los que viven en los addons custom del '
             'servidor, no el core ni enterprise). Los llena el censo.')
    despacho_custom_module_count = fields.Integer(
        'Nº apps custom', copy=False, compute='_compute_custom_module_count',
        store=True, aggregator='sum')
    # Tabla de apps custom con metadatos (la llena el censo). El Text de arriba se
    # conserva para el buscador "tiene app X" del tablero; el detalle vive aquí.
    despacho_module_ids = fields.One2many('despacho.db.module', 'project_id',
                                          string='Apps custom (detalle)')
    # Todos los módulos instalados (tabla simple, para que no se desborde el texto).
    despacho_installed_module_ids = fields.One2many(
        'despacho.db.installed.module', 'project_id', string='Módulos instalados')
    despacho_last_backup = fields.Datetime('Último respaldo', copy=False)
    # Historial de respaldos NOCTURNOS (automáticos), uno por archivo en disco.
    # Lo llena el censo de CADA servidor; es de solo lectura (refleja /backup).
    despacho_backup_ids = fields.One2many('despacho.db.backup', 'project_id',
                                          string='Respaldos automáticos')
    despacho_backup_count = fields.Integer(
        'Nº respaldos', copy=False, compute='_compute_backup_stats',
        store=True, aggregator='sum',
        help='Cantidad de respaldos nocturnos conservados en disco para esta BD.')
    despacho_backup_total_size = fields.Float(
        'Tamaño respaldos (bytes)', copy=False, compute='_compute_backup_stats',
        store=True, aggregator='sum')
    despacho_backup_total_display = fields.Char(
        'Tamaño respaldos', compute='_compute_backup_stats')
    despacho_backup_oldest = fields.Date(
        'Respaldo más antiguo', copy=False, compute='_compute_backup_stats',
        store=True, help='Inicio de la ventana de retención conservada EN DISCO local.')
    # Destinos OFF-SITE (Nextcloud / OneDrive): la retención larga (30 días) vive
    # en la nube, no en el disco local. Lo llena el censo leyendo backup-odoo.sh.
    despacho_offsite_ids = fields.One2many('despacho.db.offsite', 'project_id',
                                           string='Destinos off-site')
    despacho_offsite_summary = fields.Char(
        'Off-site', compute='_compute_offsite_summary',
        help='Resumen de los respaldos en la nube (Nextcloud / OneDrive).')
    despacho_last_census = fields.Datetime('Último escaneo', copy=False)
    despacho_provision_state = fields.Selection([
        ('unknown', 'Desconocido'),
        ('provisioning', 'Provisionando'),
        ('active', 'Activa'),
        ('suspended', 'Suspendida'),
        ('dropped', 'Eliminada'),
    ], string='Estado de provisión', default='unknown', copy=False)
    despacho_operation_ids = fields.One2many('despacho.db.operation', 'project_id',
                                             string='Operaciones')
    despacho_operation_count = fields.Integer(compute='_compute_operation_count')
    despacho_is_test = fields.Boolean(compute='_compute_is_test', store=True,
                                      help='La BD parece de prueba (su nombre empieza con "test").')
    # Auto-login ("Conectar" entra ya logueado). Solo se activa por BD una vez
    # que el módulo compañero `despacho_autologin` está instalado y su secreto
    # sembrado en esa BD. Si está en False, "Conectar" usa el comportamiento
    # nativo (abre el login).
    despacho_autologin_ready = fields.Boolean(
        'Auto-login listo', default=False, copy=False,
        help='El módulo despacho_autologin está instalado en esta BD y su '
             'secreto sembrado: el botón "Conectar" inicia sesión sin pedir clave.')
    despacho_autologin_user = fields.Char(
        'Conectar como', copy=False,
        help='Usuario (login) con el que "Conectar" iniciará sesión en esta BD. '
             'Lo resuelve el censo: el admin canónico (uid 2) si está activo y es '
             'del grupo Ajustes; si no, el administrador activo de menor id.')
    # Bridge MCP: cada cliente puede conectar su IA (Claude/ChatGPT/Gemini) a SU
    # base Odoo en solo-lectura, vía un contenedor puente dedicado (tuanle96/
    # mcp-odoo) en loopback tras Nginx, con un endpoint y Bearer por cliente.
    # Los contenedores viven SOLO en este servidor (odoo19); el censo detecta su
    # estado por BD. Ver memoria mcp-bridge-clientes.
    despacho_mcp_enabled = fields.Boolean(
        'MCP configurado', default=False, copy=False,
        help='Existe un contenedor puente MCP para esta BD: la IA del cliente '
             'puede consultar su Odoo (solo lectura) por un endpoint dedicado.')
    despacho_mcp_status = fields.Selection([
        ('running', 'En línea'),
        ('stopped', 'Detenido'),
        ('absent', 'Sin contenedor'),
    ], 'Estado MCP', copy=False,
        help='Estado del contenedor puente: en línea (vivo y responde), detenido '
             '(existe pero apagado) o sin contenedor.')
    despacho_mcp_url = fields.Char(
        'Endpoint MCP', copy=False,
        help='URL que el cliente configura en su IA (requiere su Bearer).')
    despacho_mcp_container = fields.Char('Contenedor MCP', copy=False)
    despacho_mcp_port = fields.Char('Puerto loopback MCP', copy=False)
    despacho_mcp_writes = fields.Boolean(
        'MCP permite escrituras', default=False, copy=False,
        help='El puente permite escribir en Odoo. Por seguridad debe estar en '
             'falso (solo lectura).')
    despacho_mcp_health = fields.Char(
        'Sondeo MCP', copy=False,
        help='Código HTTP del último handshake del endpoint (200 = sano).')
    # Pendientes (To-do): se ligan reusando las etiquetas que ya usas para
    # agrupar tus to-dos por cliente. Cada BD apunta a SU etiqueta; la ficha
    # muestra los pendientes (abiertos) de esa etiqueta.
    despacho_todo_tag_ids = fields.Many2many(
        'project.tags', 'despacho_db_todo_tag_rel', 'project_id', 'tag_id',
        string='Etiquetas de Pendientes', copy=False,
        help='Etiquetas de la app Pendientes (To-do) que corresponden a este '
             'cliente (una BD puede tener varias marcas → varias etiquetas). '
             'Liga los pendientes con esta base de datos sin re-etiquetarlos.')
    @api.model
    def action_convert_todos_to_tasks(self):
        """Convierte los Pendientes (To-do: project_id vacío) en TAREAS del
        proyecto de su cliente, según el mapeo BD↔etiqueta. Así aparecen en
        "Tareas" de forma nativa. Idempotente y repetible: solo toca los to-dos
        cuyas etiquetas apuntan a UNA sola BD; deja los ambiguos/sin-mapear.
        Botón del listado para arrastrar también los pendientes NUEVOS."""
        P = self.sudo().with_context(active_test=False)
        tag2db = {}
        for p in P.search([('despacho_todo_tag_ids', '!=', False)]):
            for t in p.despacho_todo_tag_ids:
                tag2db.setdefault(t.id, set()).add(p.id)
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        todos = Task.search([('project_id', '=', False), ('parent_id', '=', False)])
        conv = ambig = unmap = 0
        for t in todos:
            dbs = set()
            for tg in t.tag_ids:
                dbs |= tag2db.get(tg.id, set())
            if len(dbs) == 1:
                t.project_id = list(dbs)[0]
                conv += 1
            elif len(dbs) > 1:
                ambig += 1
            else:
                unmap += 1
        msg = ('Convertidos %d pendiente(s) a tareas. '
               'Sin convertir: %d ambiguo(s) (varias etiquetas de distinto cliente) '
               'y %d sin etiqueta de cliente.' % (conv, ambig, unmap))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Pendientes → Tareas',
                'message': msg,
                'type': 'success' if conv else 'warning',
                'sticky': False,
            },
        }

    @api.depends('database_name')
    def _compute_is_test(self):
        for rec in self:
            rec.despacho_is_test = bool(rec.database_name and rec.database_name.startswith('test'))

    @api.depends('despacho_custom_modules')
    def _compute_custom_module_count(self):
        for rec in self:
            mods = (rec.despacho_custom_modules or '').strip()
            rec.despacho_custom_module_count = len(mods.split(',')) if mods else 0

    @api.depends('despacho_db_size', 'despacho_filestore_size')
    def _compute_total_size(self):
        for rec in self:
            total = (rec.despacho_db_size or 0) + (rec.despacho_filestore_size or 0)
            rec.despacho_total_size = total
            rec.despacho_total_size_gb = total / (1024.0 ** 3)

    @api.depends('despacho_backup_ids', 'despacho_backup_ids.backup_size',
                 'despacho_backup_ids.backup_date')
    def _compute_backup_stats(self):
        for rec in self:
            backups = rec.despacho_backup_ids
            rec.despacho_backup_count = len(backups)
            total = sum(backups.mapped('backup_size'))
            rec.despacho_backup_total_size = total
            rec.despacho_backup_total_display = _human_size(total)
            dates = [b.backup_date for b in backups if b.backup_date]
            rec.despacho_backup_oldest = min(dates) if dates else False

    @api.depends('despacho_offsite_ids.remote', 'despacho_offsite_ids.available',
                 'despacho_offsite_ids.retention_days', 'despacho_offsite_ids.has_latest')
    def _compute_offsite_summary(self):
        for rec in self:
            parts = []
            for o in rec.despacho_offsite_ids:
                if not o.available:
                    parts.append('%s ?' % (o.remote or ''))
                else:
                    mark = '' if o.has_latest else ' (sin la última)'
                    parts.append('%s %sd%s' % (o.remote or '', o.retention_days, mark))
            rec.despacho_offsite_summary = ' · '.join(parts)

    @api.model
    def _backup_thresholds(self):
        """Umbrales (días) de salud de respaldo. Configurables vía parámetros del
        sistema despacho.backup_warn_days / despacho.backup_late_days."""
        ICP = self.env['ir.config_parameter'].sudo()
        def _int(key, default):
            try:
                return int(ICP.get_param(key, default))
            except (TypeError, ValueError):
                return default
        return _int('despacho.backup_warn_days', 7), _int('despacho.backup_late_days', 30)

    @api.depends('despacho_last_backup')
    def _compute_backup_health(self):
        warn, late = self._backup_thresholds()
        now = fields.Datetime.now()
        for rec in self:
            if not rec.despacho_last_backup:
                rec.despacho_days_since_backup = -1
                rec.despacho_backup_status = 'never'
                continue
            days = (now - rec.despacho_last_backup).days
            rec.despacho_days_since_backup = days
            rec.despacho_backup_status = (
                'late' if days > late else 'warn' if days > warn else 'ok')

    @api.depends('despacho_db_size', 'despacho_filestore_size')
    def _compute_size_display(self):
        for rec in self:
            total = (rec.despacho_db_size or 0) + (rec.despacho_filestore_size or 0)
            rec.despacho_size_display = '%s (BD %s + FS %s)' % (
                _human_size(total),
                _human_size(rec.despacho_db_size or 0),
                _human_size(rec.despacho_filestore_size or 0),
            )

    @api.depends('despacho_operation_ids')
    def _compute_operation_count(self):
        data = dict(self.env['despacho.db.operation']._read_group(
            [('project_id', 'in', self.ids)], ['project_id'], ['__count']))
        for rec in self:
            rec.despacho_operation_count = data.get(rec, 0)

    # ------------------------------------------------------------------ acciones
    @api.model
    def _despacho_company(self):
        """Compañía XUBAX para los registros del inventario (multi-compañía)."""
        company = self.env['res.company'].sudo().search([('name', '=ilike', 'XUBAX')], limit=1)
        return company or self.env.company

    # ------------------------------------------------------------------
    # Auto-login ("Conectar" entra ya logueado)
    # ------------------------------------------------------------------
    # El secreto de CADA BD se deriva de un secreto maestro guardado solo en la
    # BD del despacho (ir.config_parameter `despacho_autologin.master_secret`,
    # sudo). Así el manager no almacena un secreto por cada BD y, si se filtra
    # el de una BD, no revela el maestro (HMAC es de un solo sentido). El módulo
    # compañero guarda en cada BD destino su `despacho_autologin.secret` =
    # _despacho_autologin_secret() de esa BD.
    AUTOLOGIN_TTL = 30  # segundos de vida del token

    @api.model
    def _despacho_autologin_master(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'despacho_autologin.master_secret')

    def _despacho_autologin_secret(self):
        """Secreto por-BD = HMAC(maestro, nombre_bd). Debe coincidir con el
        sembrado en la BD destino."""
        self.ensure_one()
        master = self._despacho_autologin_master()
        if not master or not self.database_name:
            return None
        return hmac.new(master.encode(), self.database_name.encode(),
                        hashlib.sha256).hexdigest()

    def _despacho_autologin_url(self, login=None):
        """URL magic-link `/despacho/autologin?token=...` para esta BD, o None
        si no se puede firmar (sin maestro, sin URL, etc.). Si se pasa `login`,
        el token pide entrar como ESE usuario; si no, el controlador resuelve el
        admin de la BD."""
        self.ensure_one()
        secret = self._despacho_autologin_secret()
        if not secret or not self.database_url:
            return None
        # Base limpia: esquema+host, sin path ni `?srv=` (las BDs duplicadas
        # entre servidores guardan database_url con sufijo ?srv=<server>).
        m = re.match(r'(https?://[^/?#]+)', self.database_url.strip())
        if not m:
            return None
        base = m.group(1)
        # Sin 'login'/'uid': el controlador de la BD destino RESUELVE su admin real
        # (uid 2 no siempre sirve: puede estar inactivo o no ser del grupo
        # Ajustes). El campo despacho_autologin_user muestra de antemano quién.
        payload = {
            'exp': int(time.time()) + self.AUTOLOGIN_TTL,
            'nonce': secrets.token_urlsafe(12),
        }
        if login:
            payload['login'] = login
        raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
        p_b64 = base64.urlsafe_b64encode(raw).decode().rstrip('=')
        sig = hmac.new(secret.encode(), p_b64.encode(), hashlib.sha256).digest()
        s_b64 = base64.urlsafe_b64encode(sig).decode().rstrip('=')
        return '%s/despacho/autologin?token=%s.%s' % (base, p_b64, s_b64)

    def action_database_connect(self):
        """Override del "Conectar" nativo: si esta BD tiene el auto-login listo,
        redirige al magic-link (entra ya logueado); si no, comportamiento
        nativo (abre el login)."""
        self.ensure_one()
        if self.despacho_autologin_ready:
            url = self._despacho_autologin_url()
            if url:
                return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}
        return super().action_database_connect()

    @api.model
    def action_scan_server(self):
        """Encola un censo de CADA servidor conocido (read-only). Los remotos se
        escanean por SSH. Lo dispara el botón del listado."""
        Op = self.env['despacho.db.operation']
        for server in SERVER_KEYS:
            op = Op.create({
                'op': 'census', 'target_server': server,
                'with_modules': True, 'simulate': False,
            })
            # dpm_no_wait: encolar sin bloquear (este botón ya muestra su propio aviso).
            op.with_context(dpm_no_wait=True).action_provision()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Escaneo encolado',
                'message': 'El inventario de %d servidor(es) se actualizará en ~1-2 minutos.'
                           % len(SERVER_KEYS),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_baja(self):
        """Abre el formulario de baja prellenado para esta BD (dry-run por defecto)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Dar de baja: %s' % (self.database_name or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'baja',
                'default_project_id': self.id,
                'default_simulate': True,
                'dpm_modal': True,
            },
        }

    def action_respaldo(self):
        """Encola un respaldo (dump + filestore) de esta BD. Operación segura (read-only)."""
        self.ensure_one()
        op = self.env['despacho.db.operation'].create({
            'op': 'respaldo', 'project_id': self.id, 'simulate': False,
        })
        op.action_provision()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Respaldo encolado',
                'message': 'Se está respaldando %s. "Último respaldo" se actualizará en ~1 minuto.'
                           % (self.database_name or self.name),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_refresh_test(self):
        """Abre el asistente para refrescar ESTA BD de prueba desde producción
        (dry-run por defecto). Solo tiene sentido en BDs cuyo nombre empieza con 'test'."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Refrescar BD de prueba: %s' % (self.database_name or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'refresh',
                'default_project_id': self.id,
                'default_simulate': True,
                'dpm_modal': True,
            },
        }

    def action_create_test(self):
        """Abre el asistente para CREAR una BD de prueba a partir de ESTA BD de
        producción (copia exacta + neutralize, con un nombre nuevo que empieza con
        'test'). Reutiliza el script de refresh (crea el destino si no existe).
        Dry-run por defecto."""
        self.ensure_one()
        suggested = 'test%s' % re.sub(r'[^a-z0-9]', '', (self.database_name or '').lower())[:40]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Crear BD de prueba desde: %s' % (self.database_name or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'crear_test',
                'default_project_id': self.id,
                'default_new_test_db': suggested,
                'default_simulate': True,
                'dpm_modal': True,
            },
        }

    def _mcp_slug_suggestion(self):
        """Sugerencia de slug para el endpoint MCP: primera etiqueta del nombre de
        la BD, limpia (novadiam-anello-… -> novadiam; lamur-lamorini -> lamur)."""
        base = (self.database_name or self.name or '').lower()
        base = re.split(r'[-_]', base)[0]
        base = re.sub(r'[^a-z0-9-]', '', base)[:31]
        return base or 'cliente'

    def action_mcp_add(self):
        """Abre el asistente para ACTIVAR el puente MCP de esta BD. Por defecto la IA
        del cliente conecta con los MISMOS privilegios que su usuario administrador
        (el mismo 'Conectar como') y con escrituras habilitadas. Solo BDs de este
        servidor."""
        self.ensure_one()
        if self.despacho_server != 'odoo19':
            raise UserError('El puente MCP solo se activa en bases de ESTE servidor '
                            '(odoo19). Esta está en %s.' % (self.despacho_server or '¿?'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activar MCP: %s' % (self.database_name or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mcp_add',
                'default_project_id': self.id,
                'default_mcp_slug': self._mcp_slug_suggestion(),
                'default_mcp_as_user': self.despacho_autologin_user or '',
                'default_mcp_writes': True,
                'default_simulate': False,
                'dpm_modal': True,
            },
        }

    def action_mcp_remove(self):
        """Abre el asistente para DESACTIVAR el puente MCP de esta BD."""
        self.ensure_one()
        slug = (self.despacho_mcp_container or '').replace('mcp-', '', 1) \
            or self._mcp_slug_suggestion()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Desactivar MCP: %s' % (self.database_name or self.name),
            'res_model': 'despacho.db.operation',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_op': 'mcp_remove',
                'default_project_id': self.id,
                'default_mcp_slug': slug,
                'default_mcp_purge_key': True,
                'default_simulate': False,
                'dpm_modal': True,
            },
        }

    def action_view_operations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Operaciones',
            'res_model': 'despacho.db.operation',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    @api.model
    def _census_upsert(self, census_list):
        """Crea/actualiza un registro premise por cada BD reportada por el censo.
        Idempotente por (database_name, despacho_server). Honra el `server` que
        emite cada fila (el censo remoto trae el hostname del otro servidor), de
        modo que despacho_db_local solo es cierto para las BDs de ESTE servidor."""
        Project = self.sudo().with_context(active_test=False)
        now = fields.Datetime.now()
        created = updated = 0
        for row in census_list:
            db = (row.get('db_name') or '').strip()
            if not CENSUS_DB_RE.match(db):
                _logger.warning('Censo: nombre de BD inválido, omitido: %r', db)
                continue
            server = (row.get('server') or THIS_SERVER).strip()
            url = row.get('url') or ('https://%s.xubax.com' % db)
            rec = Project.search([
                ('database_name', '=', db),
                ('despacho_server', '=', server),
            ], limit=1)
            # database_url tiene índice único. Una misma BD puede vivir en dos
            # servidores (p.ej. una migración a medias): si la URL ya la ocupa
            # OTRO registro, la desambiguamos con el servidor para no perder la
            # fila ni romper el índice. El duplicado queda visible en el inventario.
            holder = Project.search([('database_url', '=', url)], limit=1)
            if holder and holder != rec:
                url = '%s?srv=%s' % (url, server)
            # Auto-login listo = el módulo compañero está instalado en esa BD
            # (el secreto lo siembra el alta o el despliegue). Source of truth =
            # presencia del módulo, así el alta no requiere paso manual.
            mods = row.get('modules') or ''
            mod_set = ({m.strip() for m in mods.split(',')}
                       if isinstance(mods, str) else set(mods or []))
            vals = {
                'database_url': url,
                'despacho_db_local': server == THIS_SERVER,
                'despacho_server': server,
                'despacho_db_size': row.get('db_size') or 0,
                'despacho_filestore_size': row.get('filestore_size') or 0,
                'despacho_autologin_ready': 'despacho_autologin' in mod_set,
                'despacho_autologin_user': row.get('autologin_user') or False,
                'database_version': row.get('version') or False,
                'despacho_installed_modules': row.get('modules') or False,
                'despacho_custom_modules': row.get('custom_modules') or False,
                'despacho_user_count': row.get('users_internal') or 0,
                'despacho_user_total': row.get('users_total') or 0,
                'despacho_last_backup': row.get('last_backup') or False,
                'despacho_last_census': now,
                'despacho_provision_state': 'active',
            }
            # Estado del puente MCP de esta BD (solo lo trae el censo local; en
            # remoto mcp viene None y se limpia). enabled=True solo si hay contenedor.
            mcp = row.get('mcp')
            if mcp:
                vals.update({
                    'despacho_mcp_enabled': True,
                    'despacho_mcp_status': mcp.get('status') or False,
                    'despacho_mcp_url': mcp.get('url') or False,
                    'despacho_mcp_container': mcp.get('container') or False,
                    'despacho_mcp_port': str(mcp['port']) if mcp.get('port') else False,
                    'despacho_mcp_writes': bool(mcp.get('writes')),
                    'despacho_mcp_health': str(mcp['health']) if mcp.get('health') else False,
                })
            else:
                vals.update({
                    'despacho_mcp_enabled': False,
                    'despacho_mcp_status': False,
                    'despacho_mcp_url': False,
                    'despacho_mcp_container': False,
                    'despacho_mcp_port': False,
                    'despacho_mcp_writes': False,
                    'despacho_mcp_health': False,
                })
            # Poblar la sección nativa "Gestión de usuarios" (databases.user) con los
            # usuarios internos del censo: reemplaza la lista (5,0,0) por la actual.
            ulist = row.get('users_list')
            if isinstance(ulist, list):
                cmds = [(5, 0, 0)]
                for u in ulist:
                    login = (u.get('login') or '').strip()
                    if not login:
                        continue
                    uv = {'login': login[:200], 'name': (u.get('name') or login)[:200]}
                    if u.get('last'):
                        uv['latest_authentication'] = u['last']
                    cmds.append((0, 0, uv))
                vals['database_user_ids'] = cmds
            # Historial de respaldos nocturnos del censo: reemplaza la lista entera
            # (refleja lo que hay en disco hoy; los caducados desaparecen solos).
            blist = row.get('backups')
            if isinstance(blist, list):
                bcmds = [(5, 0, 0)]
                for b in blist:
                    bname = (b.get('name') or '').strip()
                    if not bname:
                        continue
                    bcmds.append((0, 0, {
                        'name': bname[:255],
                        'backup_date': b.get('date') or False,
                        'backup_size': b.get('size') or 0,
                        'path': (b.get('path') or '')[:255] or False,
                        'server': server,
                        'checksum_ok': bool(b.get('sha_ok')),
                    }))
                vals['despacho_backup_ids'] = bcmds
            # Resumen de destinos off-site (Nextcloud/OneDrive) del censo.
            olist = row.get('offsite')
            if isinstance(olist, list):
                ocmds = [(5, 0, 0)]
                for o in olist:
                    remote = (o.get('remote') or '').strip()
                    if not remote:
                        continue
                    ocmds.append((0, 0, {
                        'remote': remote[:64],
                        'available': bool(o.get('ok')),
                        'retention_days': o.get('days') or 0,
                        'date_oldest': o.get('oldest') or False,
                        'date_newest': o.get('newest') or False,
                        'has_latest': bool(o.get('has_latest')),
                    }))
                vals['despacho_offsite_ids'] = ocmds
            # Tabla de apps custom con metadatos del censo.
            mlist = row.get('custom_modules_detail')
            if isinstance(mlist, list):
                mcmds = [(5, 0, 0)]
                for m in mlist:
                    mname = (m.get('name') or '').strip()
                    if not mname:
                        continue
                    oas = m.get('on_app_store')
                    mcmds.append((0, 0, {
                        'name': mname[:128],
                        'shortdesc': (m.get('shortdesc') or '')[:256] or False,
                        'summary': m.get('summary') or False,
                        'author': (m.get('author') or '')[:256] or False,
                        'installed_version': (m.get('version') or '')[:64] or False,
                        'license': (m.get('license') or '')[:64] or False,
                        'application': bool(m.get('application')),
                        'app_store': 'yes' if oas is True else 'no' if oas is False else 'unknown',
                        'installed_since': m.get('installed_since') or False,
                        'updated': m.get('updated') or False,
                        'website': (m.get('url') or '')[:256] or False,
                    }))
                vals['despacho_module_ids'] = mcmds
            # Tabla simple de TODOS los módulos instalados.
            ilist = row.get('installed_detail')
            if isinstance(ilist, list):
                icmds = [(5, 0, 0)]
                for m in ilist:
                    inm = (m.get('name') or '').strip()
                    if not inm:
                        continue
                    icmds.append((0, 0, {
                        'name': inm[:128],
                        'shortdesc': (m.get('shortdesc') or '')[:256] or False,
                        'installed_version': (m.get('version') or '')[:64] or False,
                        'application': bool(m.get('application')),
                    }))
                vals['despacho_installed_module_ids'] = icmds
            try:
                # Savepoint por fila: un fallo (p.ej. URL duplicada) no tira el lote.
                with self.env.cr.savepoint():
                    if rec:
                        rec.write(vals)
                        updated += 1
                    else:
                        vals.update({
                            'name': db,
                            'database_name': db,
                            'database_hosting': 'premise',
                            # Sin compañía: el inventario es de infraestructura y
                            # debe verse en cualquier compañía activa (la regla
                            # multi-company de project.project permite company_id=False).
                            'company_id': False,
                        })
                        Project.create(vals)
                        created += 1
            except Exception as e:  # noqa: BLE001 — no romper el lote por una BD
                _logger.warning('Censo: no se pudo upsert %r: %s', db, e)
        _logger.info('Censo: %d creadas, %d actualizadas', created, updated)
        return True
