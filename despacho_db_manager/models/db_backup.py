from odoo import api, fields, models


def _human_size(num):
    if not num:
        return '0 B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(num) < 1024.0:
            return '%3.1f %s' % (num, unit)
        num /= 1024.0
    return '%.1f PB' % num


class DespachoDbBackup(models.Model):
    """Una línea por archivo de respaldo nocturno (automático) de una BD.

    La llena el censo a partir de /backup/postgres/<fecha>/<db>-<fecha>.sql.gz de
    CADA servidor. Es de solo lectura para el usuario: refleja lo que hay en disco.
    """
    _name = 'despacho.db.backup'
    _description = 'Respaldo automático de BD'
    _order = 'backup_date desc, name desc'

    project_id = fields.Many2one('project.project', string='Base de datos',
                                 required=True, ondelete='cascade', index=True)
    name = fields.Char('Archivo', required=True)
    backup_date = fields.Date('Fecha')
    backup_size = fields.Float('Tamaño (bytes)', aggregator='sum')
    size_display = fields.Char('Tamaño', compute='_compute_size_display')
    path = fields.Char('Ruta')
    server = fields.Char('Servidor')
    checksum_ok = fields.Boolean(
        'Integridad', help='El archivo figura en el SHA256SUMS.txt de su carpeta '
        '(el respaldo registró su checksum al generarse).')

    @api.depends('backup_size')
    def _compute_size_display(self):
        for rec in self:
            rec.size_display = _human_size(rec.backup_size)


class DespachoDbOffsite(models.Model):
    """Resumen de un destino OFF-SITE de respaldo (Nextcloud / OneDrive) para una
    BD. La llena el censo: lee los destinos del backup-odoo.sh del servidor y hace
    un listado barato (rclone) por nube. retention_days/fechas son del servidor
    (la nube guarda por carpeta de fecha con todas las BDs); has_latest es por BD
    (el .sql.gz más reciente de ESTA BD figura en el destino)."""
    _name = 'despacho.db.offsite'
    _description = 'Destino off-site de respaldo'
    _order = 'remote'

    project_id = fields.Many2one('project.project', string='Base de datos',
                                 required=True, ondelete='cascade', index=True)
    remote = fields.Char('Destino', required=True, help='Nextcloud / OneDrive.')
    available = fields.Boolean(
        'Verificable', default=True,
        help='El censo pudo listar el destino (rclone OK). Si no, no se pudo verificar.')
    retention_days = fields.Integer(
        'Días en la nube', help='Carpetas de fecha conservadas en el destino.')
    date_oldest = fields.Date('Más antiguo')
    date_newest = fields.Date('Más reciente')
    has_latest = fields.Boolean(
        'Última copia presente',
        help='El respaldo más reciente de ESTA BD ya está en el destino.')
