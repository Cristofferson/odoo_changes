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

# Operaciones habilitadas (Fase 1: alta+censo; Fase 2: baja, respaldo, refresh).
# El resto vive en la selección; action_provision rechaza lo no habilitado.
PHASE1_OPS = ('alta', 'census', 'baja', 'respaldo', 'refresh', 'crear_test')

# Registro de servidores que el censo puede escanear. La CLAVE es un nombre LÓGICO
# (odoo19/odoo18), NO el hostname del SO: el censo y THIS_SERVER mapean
# socket.gethostname() -> esta clave (ver HOSTNAME_TO_KEY en project_project.py).
# La clave viaja a la cola; el worker root la mapea (allowlist cerrado) a un destino
# SSH; Odoo nunca pasa un host/usuario arbitrario. Debe casar con el campo `server`
# que emite despacho-census.sh y con THIS_SERVER del upsert (idempotencia por
# (database_name, despacho_server)).
SERVERS = [
    ('odoo19', 'odoo19 (este servidor · diamane.mx)'),
    ('odoo18', 'odoo18 (OVH · vps-f101b860)'),
]
SERVER_KEYS = tuple(k for k, _ in SERVERS)


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
        ('crear_test', 'Crear BD de prueba'),
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

    # --- Parámetros de BAJA ---
    do_drop = fields.Boolean(
        'Eliminar la BD (irreversible)', default=False,
        help='Apagado: la baja SOLO respalda y deshabilita el sitio en nginx (reversible). '
             'Encendido: además ELIMINA la base de datos y su filestore, tras respaldar.')
    confirm_name = fields.Char(
        'Confirmar (nombre exacto de la BD)',
        help='Para eliminar/refrescar, escribe exactamente el nombre de la base de datos afectada.')

    # --- Parámetros de REFRESH (refrescar BD de prueba desde producción) ---
    source_db = fields.Char(
        'BD de origen (producción)',
        help='Base de datos de PRODUCCIÓN cuyos datos se copiarán a la de prueba. '
             'Debe vivir en el mismo servidor que la de prueba.')

    # --- Parámetros de CREAR_TEST (nueva BD de prueba desde una de producción) ---
    new_test_db = fields.Char(
        'Nombre de la BD de prueba',
        help='Nombre de la NUEVA base de datos de prueba. Debe empezar con "test". '
             'Se crea como copia exacta de la BD de origen (la de esta ficha) y se '
             'neutraliza. Si ya existe una BD con ese nombre, la operación se ABORTA '
             'salvo que marques "Sobrescribir si ya existe".')
    crear_test_overwrite = fields.Boolean(
        'Sobrescribir si ya existe', default=False,
        help='Por seguridad, crear una BD de prueba se ABORTA si el nombre ya existe '
             '(para no pisar una BD en uso). Activa esto solo si de verdad quieres '
             'reemplazar una BD de prueba existente.')

    # --- Parámetros de CENSO ---
    with_modules = fields.Boolean('Incluir módulos instalados', default=True)
    target_server = fields.Selection(
        SERVERS, string='Servidor a escanear', default='odoo19',
        help='Servidor cuyo inventario de bases de datos se censará. Los remotos '
             'se escanean por SSH (solo lectura).')

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

    def _build_baja_req(self):
        proj = self.project_id
        if not proj or not proj.database_name:
            raise UserError('La baja requiere seleccionar una base de datos del inventario.')
        db = (proj.database_name or '').strip()
        if not CENSUS_DB_RE.match(db):
            raise UserError('Nombre de BD inválido para baja: %r' % db)
        server = (proj.despacho_server or 'odoo19').strip()
        if server not in SERVER_KEYS:
            raise UserError('Servidor de la BD no reconocido: %s' % server)
        # Dominio para deshabilitar nginx: el host del database_url (sin ?srv=…),
        # o <db>.xubax.com como respaldo.
        domain = ''
        m = re.search(r'https?://([^/?#]+)', proj.database_url or '')
        if m:
            domain = m.group(1)
        if not domain:
            domain = '%s.xubax.com' % db
        # Si el dominio derivado no es un hostname válido (p.ej. BDs con guion bajo
        # como staging_xbpos, que no tienen vhost público), se OMITE el paso de
        # nginx; la baja respalda y (opcional) dropea igual. No es un error.
        skip_nginx = not DOMAIN_RE.match(domain)
        if skip_nginx:
            domain = ''
        drop = bool(self.do_drop)
        if drop and (self.confirm_name or '').strip() != db:
            raise UserError('Para ELIMINAR la BD escribe exactamente su nombre (%s) en "Confirmar".' % db)
        return {
            'id': self.id, 'op': 'baja',
            'db': db, 'domain': domain, 'server': server,
            'skip_nginx': skip_nginx,
            'drop': drop, 'confirm': db if drop else '',
            'simulate': bool(self.simulate),
        }

    def _build_respaldo_req(self):
        proj = self.project_id
        if not proj or not proj.database_name:
            raise UserError('El respaldo requiere seleccionar una base de datos del inventario.')
        db = (proj.database_name or '').strip()
        if not CENSUS_DB_RE.match(db):
            raise UserError('Nombre de BD inválido para respaldo: %r' % db)
        server = (proj.despacho_server or 'odoo19').strip()
        if server not in SERVER_KEYS:
            raise UserError('Servidor de la BD no reconocido: %s' % server)
        return {'id': self.id, 'op': 'respaldo', 'db': db, 'server': server,
                'simulate': False}

    def _build_refresh_req(self):
        proj = self.project_id
        if not proj or not proj.database_name:
            raise UserError('El refresh requiere seleccionar la BD de PRUEBA (destino) del inventario.')
        dest = (proj.database_name or '').strip()
        if not dest.startswith('test'):
            raise UserError('Por seguridad, el destino debe ser una BD de prueba '
                            '(su nombre debe empezar con "test"). "%s" no lo es.' % dest)
        if not CENSUS_DB_RE.match(dest):
            raise UserError('Nombre de BD destino inválido: %r' % dest)
        src = (self.source_db or '').strip().lower()
        if not CENSUS_DB_RE.match(src):
            raise UserError('Indica una BD de origen (producción) válida.')
        if src == dest:
            raise UserError('El origen y el destino no pueden ser la misma BD.')
        server = (proj.despacho_server or 'odoo19').strip()
        if server not in SERVER_KEYS:
            raise UserError('Servidor de la BD no reconocido: %s' % server)
        if not self.simulate and (self.confirm_name or '').strip() != dest:
            raise UserError('Vas a SOBRESCRIBIR %s. Escribe su nombre exacto en "Confirmar".' % dest)
        return {
            'id': self.id, 'op': 'refresh', 'source': src, 'dest': dest,
            'server': server, 'confirm': dest if not self.simulate else '',
            'simulate': bool(self.simulate),
        }

    def _build_crear_test_req(self):
        """Crear una BD de prueba NUEVA desde la BD de producción de la ficha.
        El origen es project_id (la prod); el destino es new_test_db (nombre nuevo).
        Reutiliza el worker/script de 'refresh' (crea el destino si no existe), por
        eso emite op='refresh' a la cola: cero cambios en la capa OS."""
        proj = self.project_id
        if not proj or not proj.database_name:
            raise UserError('Selecciona la BD de PRODUCCIÓN de origen (la de esta ficha).')
        src = (proj.database_name or '').strip().lower()
        if not CENSUS_DB_RE.match(src):
            raise UserError('Nombre de BD de origen inválido: %r' % src)
        dest = (self.new_test_db or '').strip().lower()
        if not dest.startswith('test'):
            raise UserError('Por seguridad, la BD de prueba debe llamarse empezando '
                            'con "test". "%s" no lo es.' % dest)
        if not CENSUS_DB_RE.match(dest):
            raise UserError('Nombre de BD de prueba inválido: %r' % dest)
        if src == dest:
            raise UserError('El origen y el destino no pueden ser la misma BD.')
        server = (proj.despacho_server or 'odoo19').strip()
        if server not in SERVER_KEYS:
            raise UserError('Servidor de la BD no reconocido: %s' % server)
        if not self.simulate and (self.confirm_name or '').strip() != dest:
            raise UserError('Vas a crear/sobrescribir %s. Escribe su nombre exacto '
                            'en "Confirmar".' % dest)
        overwrite = bool(self.crear_test_overwrite)
        # Salvaguarda anti-clobber (capa Odoo): si NO se pidió sobrescribir y ya hay
        # una BD con ese nombre en el inventario del mismo servidor, abortar pronto.
        # El backstop autoritativo (--no-clobber) vive en el script por si la BD no
        # está aún en el inventario.
        if not overwrite:
            existing = self.env['project.project'].sudo().with_context(active_test=False).search([
                ('database_name', '=', dest), ('despacho_server', '=', server)], limit=1)
            if existing:
                raise UserError(
                    'Ya existe una BD de prueba llamada "%s" en %s. Para reemplazarla '
                    'marca "Sobrescribir si ya existe"; si no, usa otro nombre.' % (dest, server))
        return {
            'id': self.id, 'op': 'refresh', 'source': src, 'dest': dest,
            'server': server, 'confirm': dest if not self.simulate else '',
            'no_clobber': not overwrite, 'simulate': bool(self.simulate),
        }

    def _build_census_req(self):
        server = self.target_server or 'odoo19'
        if server not in SERVER_KEYS:
            raise UserError('Servidor a escanear no reconocido: %s' % server)
        return {
            'id': self.id, 'op': 'census', 'server': server,
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
            # El respaldo trae fecha/rutas: refrescar "Último respaldo" de la BD.
            if (rec.op == 'respaldo' and res.get('state') == 'done'
                    and isinstance(res.get('backup'), dict) and rec.project_id):
                bt = res['backup'].get('backup_time')
                if bt:
                    rec.project_id.sudo().despacho_last_backup = bt
            # Baja aplicada de verdad: reflejar el resultado en el inventario para
            # que el listado no siga mostrando la BD como activa.
            #  - con drop: la BD se eliminó -> marcar 'dropped' y ARCHIVAR (sale del
            #    listado por defecto; el registro y su historial se conservan).
            #  - sin drop (reversible): el sitio se deshabilitó -> marcar 'suspended'.
            if (rec.op == 'baja' and res.get('state') == 'done'
                    and not rec.simulate and rec.project_id):
                if rec.do_drop:
                    rec.project_id.sudo().write({
                        'despacho_provision_state': 'dropped', 'active': False})
                else:
                    rec.project_id.sudo().despacho_provision_state = 'suspended'
            # Crear BD de prueba aplicado de verdad: dar de alta el nuevo test en el
            # inventario para que aparezca de inmediato (el censo llenará tamaños).
            if (rec.op == 'crear_test' and res.get('state') == 'done'
                    and not rec.simulate and isinstance(res.get('refresh'), dict)):
                ref = res['refresh']
                dest = ref.get('dest')
                server = ref.get('server') or (rec.project_id.despacho_server
                                               if rec.project_id else False)
                if dest and server:
                    self.env['project.project']._census_upsert(
                        [{'db_name': dest, 'server': server}])
        return True

    @api.model
    def _cron_refresh(self):
        self.search([('state', 'in', ('queued', 'running'))]).action_refresh()
