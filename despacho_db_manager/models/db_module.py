from odoo import api, fields, models


class DespachoDbModule(models.Model):
    """Una app CUSTOM instalada en una BD, con sus metadatos. La llena el censo
    (cruce de módulos instalados con el custom-addons del servidor + lectura de
    ir_module_module + chequeo en apps.odoo.com). Solo lectura para el usuario."""
    _name = 'despacho.db.module'
    _description = 'App custom de una BD'
    _order = 'application desc, name'

    project_id = fields.Many2one('project.project', string='Base de datos',
                                 required=True, ondelete='cascade', index=True)
    name = fields.Char('Nombre técnico', required=True)
    shortdesc = fields.Char('Nombre')
    summary = fields.Text('Descripción')
    author = fields.Char('Autor')
    installed_version = fields.Char('Versión')
    license = fields.Char('Licencia')
    application = fields.Boolean(
        'Es aplicación', help='Aparece como App propia (no solo módulo técnico).')
    app_store = fields.Selection([
        ('yes', 'Sí'),
        ('no', 'No'),
        ('unknown', 'Sin verificar'),
    ], string='En apps.odoo.com', default='unknown',
        help='Si el módulo figura publicado/indexado en apps.odoo.com para su serie.')
    app_store_url = fields.Char('Enlace store', compute='_compute_app_store_url')
    installed_since = fields.Date(
        'Alta', help='Cuándo apareció el módulo en la BD (create_date); para una '
        'app custom agregada después suele coincidir con su instalación.')
    updated = fields.Date('Actualizado', help='Última modificación del módulo (write_date).')
    website = fields.Char('Sitio')

    def _series(self):
        self.ensure_one()
        parts = (self.installed_version or '').split('.')
        if len(parts) >= 2 and parts[0].isdigit():
            return '%s.%s' % (parts[0], parts[1])
        return '19.0'

    @api.depends('name', 'installed_version')
    def _compute_app_store_url(self):
        for rec in self:
            rec.app_store_url = (
                'https://apps.odoo.com/apps/modules/%s/%s/' % (rec._series(), rec.name)
                if rec.name else False)
