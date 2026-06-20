import json
import os
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

# Misma cola/worker/systemd que el módulo despacho_provision (reutilizada).
SPOOL = '/var/spool/despacho_provision'

# ALTA = BD nueva: nombre estricto (sin guiones) para forzar identificadores limpios.
DB_RE = re.compile(r'^[a-z][a-z0-9_]{1,40}$')
# CENSO = BD existentes: permite guiones (varias BDs históricas los usan), 63 máx.
CENSUS_DB_RE = re.compile(r'^[a-z][a-z0-9_-]{1,62}$')
DOMAIN_RE = re.compile(r'^[a-z0-9][a-z0-9.-]{1,99}$')
MODULES_RE = re.compile(r'^[a-z0-9_,]+$')

# Operaciones implementadas en Fase 1. El resto vive en la selección para
# compatibilidad futura, pero action_provision las rechaza por ahora.
PHASE1_OPS = ('alta', 'census')


class DespachoDbOperation(models.Model):
    _name = 'despacho.db.operation'
    _description = 'Operación sobre base de datos de cliente'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    op = fields.Selection([
        ('alta', 'Alta de cliente'),
        ('baja', 'Baja de cliente'),
        ('respaldo', 'Respaldo'),
        ('email', 'Configurar correo'),
        ('refresh', 'Refrescar BD de prueba'),
        ('census', 'Escanear servidor'),
    ], string='Operación', required=True, default='alta')

    project_id = fields.Many2one(
        'project.project', string='Base de datos', ondelete='cascade',
        domain=[('database_hosting', '!=', False)],
        help='Vacío para alta (la BD aún no existe) y para censo (afecta a todas).')

    # --- Parámetros de ALTA (instantánea congelada al encolar) ---
    db_name = fields.Char('Nombre de la BD',
                          help='Minúsculas, números y _, empieza con letra. Ej: cafemiranda')
    domain = fields.Char('Dominio', help='Ej: cafemiranda.com  o  cafemiranda.xubax.com')
    mail_domain = fields.Char('Dominio de correo',
                              help='Vacío = dominio registrable (últimas 2 etiquetas). '
                                   'Para .com.mx escríbelo explícito.')
    modules = fields.Char('Módulos a instalar', default='base,contacts,l10n_mx')
    with_dns = fields.Boolean('Crear DNS en Cloudflare', default=True)
    with_ssl = fields.Boolean('Emitir certificado SSL', default=True)
    with_mail = fields.Boolean('Configurar correo (DKIM/SPF/DMARC)', default=True)
    wants_cfdi = fields.Boolean('El cliente quiere CFDI',
                                help='Recordatorio para cuando crees su suscripción.')

    # --- Parámetros de CENSO ---
    with_modules = fields.Boolean('Incluir módulos instalados', default=True)

    simulate = fields.Boolean('Simular (dry-run, no crea nada)', default=True,
                              help='Déjalo activado la primera vez para revisar el plan. '
                                   'Desactívalo y vuelve a ejecutar para aplicar de verdad.')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('queued', 'En cola'),
        ('running', 'Ejecutando'),
        ('done', 'Listo'),
        ('error', 'Error'),
    ], default='draft', readonly=True, string='Estado')
    log = fields.Text('Registro', readonly=True)

    @api.depends('op', 'db_name', 'project_id')
    def _compute_display_name(self):
        labels = dict(self._fields['op'].selection)
        for rec in self:
            target = rec.db_name or rec.project_id.database_name or rec.project_id.name or ''
            rec.display_name = '%s%s' % (labels.get(rec.op, rec.op or ''),
                                         (': %s' % target) if target else '')

    # ------------------------------------------------------------------ acciones
    def action_provision(self):
        self.ensure_one()
        if self.op not in PHASE1_OPS:
            raise UserError('La operación "%s" se habilita en la Fase 2.' % self.op)
        req = getattr(self, '_build_%s_req' % self.op)()
        self._enqueue(req)
        self.write({
            'state': 'queued',
            'log': 'Solicitud enviada a la cola. El vigilante la tomará en segundos. '
                   'Usa "Actualizar estado" o espera al refresco automático.',
        })

    def _build_alta_req(self):
        name = (self.db_name or '').strip().lower()
        domain = (self.domain or '').strip().lower()
        mail_domain = (self.mail_domain or '').strip().lower()
        modules = (self.modules or '').strip().lower().replace(' ', '')
        if not DB_RE.match(name):
            raise UserError('Nombre de BD inválido. Usa minúsculas, números y _, empezando con letra.')
        if not DOMAIN_RE.match(domain):
            raise UserError('Dominio inválido.')
        if mail_domain and not DOMAIN_RE.match(mail_domain):
            raise UserError('Dominio de correo inválido.')
        if not MODULES_RE.match(modules):
            raise UserError('Lista de módulos inválida (solo minúsculas, números, _ y comas).')
        return {
            'id': self.id, 'op': 'alta',
            'db': name, 'domain': domain, 'mail_domain': mail_domain, 'modules': modules,
            'with_dns': bool(self.with_dns), 'with_ssl': bool(self.with_ssl),
            'with_mail': bool(self.with_mail), 'simulate': bool(self.simulate),
        }

    def _build_census_req(self):
        return {
            'id': self.id, 'op': 'census',
            'with_modules': bool(self.with_modules), 'simulate': bool(self.simulate),
        }

    def _enqueue(self, req):
        qdir = os.path.join(SPOOL, 'queue')
        try:
            os.makedirs(qdir, exist_ok=True)
            tmp = os.path.join(qdir, '.%d.json.tmp' % self.id)
            final = os.path.join(qdir, '%d.json' % self.id)
            with open(tmp, 'w') as fh:
                json.dump(req, fh)
            os.rename(tmp, final)  # escritura atómica para el vigilante
        except OSError as e:
            raise UserError('No se pudo encolar la solicitud: %s\n'
                            '¿Existe %s y es escribible por el usuario odoo?' % (e, qdir))

    def action_refresh(self):
        for rec in self:
            rpath = os.path.join(SPOOL, 'result', '%d.json' % rec.id)
            if not os.path.exists(rpath):
                continue
            try:
                with open(rpath) as fh:
                    res = json.load(fh)
            except (OSError, ValueError):
                continue
            rec.write({'state': res.get('state', 'error'),
                       'log': res.get('log', '(sin registro)')})
            # El censo trae el inventario en la respuesta: hacer upsert.
            if rec.op == 'census' and res.get('state') == 'done' and isinstance(res.get('census'), list):
                self.env['project.project']._census_upsert(res['census'])
        return True

    @api.model
    def _cron_refresh(self):
        self.search([('state', 'in', ('queued', 'running'))]).action_refresh()
