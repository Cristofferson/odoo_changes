import logging
import socket

from odoo import api, fields, models

from .db_operation import CENSUS_DB_RE

_logger = logging.getLogger(__name__)

# Hostname de ESTE servidor: clave para distinguir las BDs locales (que el
# worker local sí puede operar) de las registradas de otros servidores.
THIS_SERVER = socket.gethostname()


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
    despacho_db_size = fields.Float('Tamaño BD (bytes)', copy=False)
    despacho_filestore_size = fields.Float('Tamaño filestore (bytes)', copy=False)
    despacho_size_display = fields.Char('Tamaño', compute='_compute_size_display')
    despacho_installed_modules = fields.Text('Módulos instalados', copy=False)
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
        """Encola un censo del servidor (read-only). Lo dispara el botón del listado."""
        op = self.env['despacho.db.operation'].create({
            'op': 'census', 'with_modules': True, 'simulate': False,
        })
        op.action_provision()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Escaneo encolado',
                'message': 'El inventario de bases de datos se actualizará en ~1 minuto.',
                'type': 'success',
                'sticky': False,
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
        """Crea/actualiza un registro premise por cada BD local reportada por el censo.
        Idempotente por (database_name, despacho_server)."""
        Project = self.sudo().with_context(active_test=False)
        company = self._despacho_company()
        now = fields.Datetime.now()
        created = updated = 0
        for row in census_list:
            db = (row.get('db_name') or '').strip()
            if not CENSUS_DB_RE.match(db):
                _logger.warning('Censo: nombre de BD inválido, omitido: %r', db)
                continue
            url = row.get('url') or ('https://%s.xubax.com' % db)
            vals = {
                'database_url': url,
                'despacho_db_local': True,
                'despacho_server': THIS_SERVER,
                'despacho_db_size': row.get('db_size') or 0,
                'despacho_filestore_size': row.get('filestore_size') or 0,
                'despacho_installed_modules': row.get('modules') or False,
                'despacho_last_backup': row.get('last_backup') or False,
                'despacho_last_census': now,
                'despacho_provision_state': 'active',
            }
            rec = Project.search([
                ('database_name', '=', db),
                ('despacho_server', '=', THIS_SERVER),
            ], limit=1)
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
                            'company_id': company.id,
                        })
                        Project.create(vals)
                        created += 1
            except Exception as e:  # noqa: BLE001 — no romper el lote por una BD
                _logger.warning('Censo: no se pudo upsert %r: %s', db, e)
        _logger.info('Censo: %d creadas, %d actualizadas', created, updated)
        return True
