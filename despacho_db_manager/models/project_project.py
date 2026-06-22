import logging
import re
import socket

from odoo import api, fields, models

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
    despacho_installed_modules = fields.Text('Módulos instalados', copy=False)
    despacho_custom_modules = fields.Text(
        'Apps custom', copy=False,
        help='Módulos custom instalados (los que viven en los addons custom del '
             'servidor, no el core ni enterprise). Los llena el censo.')
    despacho_custom_module_count = fields.Integer(
        'Nº apps custom', copy=False, compute='_compute_custom_module_count',
        store=True, aggregator='sum')
    despacho_last_backup = fields.Datetime('Último respaldo', copy=False)
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
    despacho_is_test = fields.Boolean(compute='_compute_is_test',
                                      help='La BD parece de prueba (su nombre empieza con "test").')

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
            op.action_provision()
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
            vals = {
                'database_url': url,
                'despacho_db_local': server == THIS_SERVER,
                'despacho_server': server,
                'despacho_db_size': row.get('db_size') or 0,
                'despacho_filestore_size': row.get('filestore_size') or 0,
                'despacho_installed_modules': row.get('modules') or False,
                'despacho_custom_modules': row.get('custom_modules') or False,
                'despacho_last_backup': row.get('last_backup') or False,
                'despacho_last_census': now,
                'despacho_provision_state': 'active',
            }
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
