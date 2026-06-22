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
