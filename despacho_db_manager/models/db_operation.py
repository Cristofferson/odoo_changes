import json
import os
import re
import time

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
PHASE1_OPS = ('alta', 'census', 'baja', 'respaldo', 'refresh', 'crear_test',
              'mcp_add', 'mcp_remove', 'site_suspend', 'site_resume')
# slug del endpoint MCP (segmento de la URL pública /<slug>/mcp). Igual que el
# que validan add-client.sh y el worker.
MCP_SLUG_RE = re.compile(r'^[a-z][a-z0-9-]{1,30}$')
EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

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

# Servidores cuyas BDs NO viven en este box: el puente MCP corre igual en odoo19
# pero apunta al Odoo remoto por IP directa (xmlrpc). El VALOR es el nombre que
# entiende add-client.sh --remote (allowlist en el worker root). Solo método token.
MCP_REMOTE_SERVERS = {'odoo18': 'ovh'}


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
        ('mcp_add', 'Activar MCP'),
        ('mcp_remove', 'Desactivar MCP'),
        ('site_suspend', 'Suspender sitio'),
        ('site_resume', 'Reactivar sitio'),
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
    source_project_id = fields.Many2one(
        'project.project', string='BD de origen (producción)',
        domain="[('database_hosting','!=',False),('despacho_is_test','=',False),"
               "('despacho_server','=',dest_server)]",
        help='Base de datos de PRODUCCIÓN (del inventario) cuyos datos se copiarán a '
             'la de prueba. Solo se listan las del MISMO servidor que la de prueba.')
    # Servidor de la BD destino (la de prueba): se usa para filtrar el desplegable
    # de origen al mismo servidor. Va invisible en el formulario.
    dest_server = fields.Char(related='project_id.despacho_server')

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

    # --- Parámetros de MCP (activar/desactivar el puente de IA del cliente) ---
    mcp_slug = fields.Char(
        'Identificador del endpoint',
        help='Segmento de la URL pública: https://mcp.xubax.com/<slug>/mcp. '
             'Minúsculas, números y guiones; corto y reconocible (ej: lamur). '
             'Es lo que verá el cliente.')
    mcp_as_user = fields.Char(
        'Conectar como (usuario)',
        help='Login del usuario de Odoo con el que la IA se conectará. Por defecto es '
             'el administrador de la BD (el mismo de "Conectar como"), para que la IA '
             'tenga LOS MISMOS PRIVILEGIOS que ese usuario logueado. Si lo dejas vacío '
             'se usa un usuario dedicado de solo lectura (mcp_readonly).')
    mcp_writes = fields.Boolean(
        'Permitir escrituras', default=True,
        help='Si está activo, la IA puede crear/modificar/borrar según los permisos '
             'del usuario de conexión (coherente con "mismos privilegios que logueado"). '
             'Desactívalo para limitar la IA a solo consulta.')
    mcp_purge_key = fields.Boolean(
        'Revocar también la API key', default=True,
        help='Al desactivar, elimina la API key del usuario mcp_readonly en la BD '
             '(recomendado: deja la credencial inservible).')
    mcp_oauth = fields.Boolean(
        'Login por OAuth (ChatGPT)', default=False,
        help='Activo: el puente se publica en su propio subdominio mcp-<id>.xubax.com '
             'protegido por Cloudflare Access. El cliente entra con su CORREO (login '
             'OAuth), compatible con ChatGPT y Claude web. Apagado: endpoint clásico '
             'con token Bearer (solo apps que aceptan token, p.ej. Claude escritorio).')
    mcp_email = fields.Char(
        'Correo del cliente (login)',
        help='Correo con el que el cliente iniciará sesión (Cloudflare le manda un '
             'código). Solo ese correo podrá entrar a su endpoint.')

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

    # ------------------------------------------------------------------ feedback
    def _notify(self, kind, title, message, sticky=False):
        """Envía un toast (bus) al usuario que creó la operación. kind:
        success/danger/warning/info. No-op para censo (el botón ya avisa)."""
        if self.op == 'census':
            return
        user = self.create_uid or self.env.user
        if user and user.partner_id:
            self.env['bus.bus']._sendone(user.partner_id, 'simple_notification', {
                'type': kind, 'title': title, 'message': message, 'sticky': sticky})

    def _error_reason(self):
        """Línea más informativa del registro para mostrar en el toast de error."""
        log = self.log or ''
        for line in reversed(log.splitlines()):
            s = line.strip()
            if s and ('error' in s.lower() or 'abort' in s.lower() or 'rechaz' in s.lower()):
                return s
        lines = [l.strip() for l in log.splitlines() if l.strip()]
        return lines[-1] if lines else ''

    def _notify_mcp_credentials(self):
        """Muestra UNA sola vez el endpoint + token del puente recién activado.
        El token NO se persiste en Odoo; vive en el .bearer (root) del servidor.
        El result que lo trae es 640 root:odoo (no world-readable)."""
        rpath = os.path.join(SPOOL, 'result', '%d.json' % self.id)
        endpoint = bearer = email = ''
        try:
            with open(rpath) as fh:
                m = (json.load(fh) or {}).get('mcp') or {}
            endpoint = m.get('endpoint') or ''
            bearer = m.get('bearer') or ''
            email = m.get('email') or ''
        except (OSError, ValueError):
            pass
        if email:  # puente por OAuth (Cloudflare Access): no hay token, login por correo
            self._notify(
                'success', '✅ MCP (OAuth) activado',
                'Entrega al cliente para conectar su IA (ChatGPT/Claude):\n\n'
                'Endpoint:\n%s\n\nInicia sesión con el correo:\n%s\n\n(Cloudflare le '
                'mandará un código a ese correo; solo ese correo puede entrar.)'
                % (endpoint, email), sticky=True)
        elif bearer:
            self._notify(
                'success', '✅ MCP activado — copia el token AHORA',
                'Entrega estos datos al cliente para su IA (el token NO se vuelve a '
                'mostrar):\n\nEndpoint:\n%s\n\nAutenticación:\nAuthorization: Bearer %s'
                % (endpoint, bearer), sticky=True)
        else:
            self._notify(
                'warning', '✅ MCP activado',
                'Activado, pero no pude leer el token aquí. Está en el servidor: '
                '/opt/odoo-mcp/clients/<slug>.bearer', sticky=True)

    def _notify_outcome(self):
        """Toast según el estado actual de la operación."""
        label = self.display_name or ('operación #%d' % self.id)
        if self.op == 'mcp_add' and self.state == 'done':
            return self._notify_mcp_credentials()
        if self.state == 'done':
            self._notify('success', '✅ Operación completada', '%s: Listo.' % label)
        elif self.state == 'error':
            self._notify('danger', '❌ Error en la operación',
                         self._error_reason() or ('%s falló. Revisa el Registro.' % label),
                         sticky=True)
        else:
            self._notify('warning', '⏳ Operación en proceso',
                         '%s está en proceso. Te avisaré al terminar (o revisa "Operaciones").'
                         % label)

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
        # Llamada interna (p.ej. censo en lote): no esperar ni notificar por op.
        if self.env.context.get('dpm_no_wait'):
            return True
        # Esperar brevemente el resultado para dar feedback inmediato en ops rápidas
        # (censo, baja, dry-runs, respaldos chicos). Las largas (refresh/crear apply)
        # superan la ventana: se avisa "en proceso" y el cron notifica al terminar.
        rpath = os.path.join(SPOOL, 'result', '%d.json' % self.id)
        # mcp_add tarda más (el odoo shell que crea la API key carga el registro):
        # esperamos hasta ~30 s para entregar el token en el mismo clic.
        n_poll = 60 if self.op == 'mcp_add' else 20
        for _ in range(n_poll):  # ~10 s (mcp_add ~30 s)
            try:
                with open(rpath) as fh:
                    if json.load(fh).get('state') in ('done', 'error'):
                        break
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        self.with_context(skip_notify=True).action_refresh()  # ingiere sin doble toast
        self._notify_outcome()
        # Si se abrió como asistente modal, cerrarlo (el toast llega por el bus).
        if self.env.context.get('dpm_modal'):
            return {'type': 'ir.actions.act_window_close'}
        return True

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
        server = (proj.despacho_server or 'odoo19').strip()
        if server not in SERVER_KEYS:
            raise UserError('Servidor de la BD no reconocido: %s' % server)
        # El origen se elige de una LISTA (no se teclea), así que no puede estar mal
        # escrito. Solo backstops: que esté seleccionado, sea válido, distinto del
        # destino y viva en el mismo servidor.
        src_proj = self.source_project_id
        if not src_proj or not src_proj.database_name:
            raise UserError('Selecciona la BD de origen (producción) de la lista.')
        src = src_proj.database_name.strip().lower()
        if not CENSUS_DB_RE.match(src):
            raise UserError('Nombre de BD de origen inválido: %r' % src)
        if src == dest:
            raise UserError('El origen y el destino no pueden ser la misma BD.')
        if (src_proj.despacho_server or '').strip() != server:
            raise UserError('La BD de origen debe estar en el mismo servidor (%s) '
                            'que la de prueba.' % server)
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

    def _build_mcp_add_req(self):
        if not self.project_id:
            raise UserError('Falta la base de datos.')
        # El contenedor del puente SIEMPRE corre en ESTE servidor (odoo19). Para BDs
        # locales habla con el Odoo local (json2); para BDs de OVH (odoo18) apunta al
        # Odoo remoto por IP directa (xmlrpc) — ver MCP_REMOTE_SERVERS.
        server = self.project_id.despacho_server or '¿?'
        remote = MCP_REMOTE_SERVERS.get(server)
        if server != 'odoo19' and not remote:
            raise UserError('El puente MCP solo se puede activar en bases de ESTE '
                            'servidor (odoo19) o de OVH (odoo18); la elegida está '
                            'en %s.' % server)
        # (El MCP ahora es POR USUARIO: una BD puede tener varios puentes, uno por
        #  usuario. El control "ya tiene puente" se hace por usuario en
        #  databases.user.action_mcp_add_user, y la unicidad del slug la garantiza
        #  add-client.sh. Por eso aquí ya NO se bloquea a nivel de BD.)
        slug = (self.mcp_slug or '').strip().lower()
        if not MCP_SLUG_RE.match(slug):
            raise UserError('Identificador inválido: usa minúsculas, números y '
                            'guiones (2-31 caracteres). Ej: lamur')
        db = (self.project_id.database_name or '').strip()
        if not CENSUS_DB_RE.match(db):
            raise UserError('Nombre de BD inválido: %s' % db)
        req = {
            'id': self.id, 'op': 'mcp_add', 'slug': slug, 'db': db,
            'writes': bool(self.mcp_writes),
            'as_user': (self.mcp_as_user or '').strip(),
        }
        if remote:
            # OVH (odoo18): el contenedor corre en este box pero apunta al Odoo remoto
            # por xmlrpc. Soporta AMBOS métodos: token (add-client.sh --remote ovh) y
            # OAuth/ChatGPT (oauth-enable.sh --remote ovh).
            req['remote'] = remote
        if self.mcp_oauth:
            email = (self.mcp_email or '').strip()
            if not EMAIL_RE.match(email):
                raise UserError('Para el login por OAuth necesitas el correo del '
                                'cliente (con él iniciará sesión). Correo inválido: %s'
                                % (email or '(vacío)'))
            req['oauth'] = True
            req['email'] = email
        return req

    def _build_mcp_remove_req(self):
        if not self.project_id:
            raise UserError('Falta la base de datos.')
        slug = (self.mcp_slug or '').strip().lower()
        if not MCP_SLUG_RE.match(slug):
            raise UserError('No se pudo determinar el identificador del puente MCP.')
        return {
            'id': self.id, 'op': 'mcp_remove', 'slug': slug,
            'purge_key': bool(self.mcp_purge_key),
            'oauth': bool(self.mcp_oauth),
        }

    def _build_site_op_req(self, op):
        """Suspender/reactivar el SITIO web (vhost nginx) de la BD por cobranza.
        Solo BDs locales: el flag de suspensión vive en ESTE servidor (el worker
        crea/borra /etc/nginx/xubax-suspended/<db>.flag y el guard del snippet
        compartido responde 503). No reinicia nginx."""
        proj = self.project_id
        if not proj or not proj.database_name:
            raise UserError('Esta operación requiere seleccionar una base de datos.')
        if not proj.despacho_db_local:
            raise UserError('Solo se puede suspender/reactivar el sitio de una BD '
                            'que vive en este servidor.')
        db = (proj.database_name or '').strip()
        if not CENSUS_DB_RE.match(db):
            raise UserError('Nombre de BD inválido: %r' % db)
        return {'id': self.id, 'op': op, 'db': db}

    def _build_site_suspend_req(self):
        return self._build_site_op_req('site_suspend')

    def _build_site_resume_req(self):
        return self._build_site_op_req('site_resume')

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

    # Ruido de psql al restaurar un volcado (un bloque por secuencia): se filtra al
    # ingerir el log para que la pestaña Registro sea legible (también al pulsar
    # "Actualizar estado", que re-lee el archivo de resultado).
    _LOG_NOISE = [re.compile(p) for p in (
        r'^\s*setval\s*$', r'^\s*set_config\s*$', r'^\s*-{3,}\s*$', r'^\s*\d+\s*$',
        r'^\s*\(\d+ rows?\)\s*$', r'^\s*SET\s*$', r'^\s*COPY \d+\s*$')]

    @api.model
    def _clean_log(self, log):
        out, blanks = [], 0
        for ln in (log or '').splitlines():
            if any(p.match(ln) for p in self._LOG_NOISE):
                continue
            if not ln.strip():
                blanks += 1
                if blanks > 1:
                    continue
            else:
                blanks = 0
            out.append(ln)
        return '\n'.join(out).strip() or '(sin registro)'

    def action_refresh(self):
        skip_notify = self.env.context.get('skip_notify')
        for rec in self:
            rpath = os.path.join(SPOOL, 'result', '%d.json' % rec.id)
            if not os.path.exists(rpath):
                continue
            try:
                with open(rpath) as fh:
                    res = json.load(fh)
            except (OSError, ValueError):
                continue
            was_terminal = rec.state in ('done', 'error')
            rec.write({'state': res.get('state', 'error'),
                       'log': self._clean_log(res.get('log', '(sin registro)'))})
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
                # Cobranza: al dar de baja la BD, CERRAR (churn) su suscripción para
                # dejar de facturar al cliente. Solo si está en un estado activo (no
                # tocar borradores ni las ya cerradas). Reversible con "Reabrir" si
                # fue una baja temporal. set_close() pone end_date + estado churn.
                sub = rec.project_id.sudo().despacho_subscription_id
                if sub and sub.subscription_state in (
                        '2_renewal', '3_progress', '4_paused', '7_upsell'):
                    try:
                        sub.set_close()
                    except Exception:  # noqa: BLE001 — nunca romper el ingest por esto
                        sub.subscription_state = '6_churn'
                    sub.message_post(body=(
                        '🚫 Suscripción cerrada automáticamente al dar de baja la '
                        'base "%s". Si fue una baja temporal/reversible, puedes '
                        'reabrirla.' % (rec.project_id.database_name or '')))
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
            # Activar MCP aplicado: reflejar de inmediato el estado del puente en la
            # ficha (sin guardar el token; ese se muestra una sola vez en el aviso).
            if (rec.op == 'mcp_add' and res.get('state') == 'done'
                    and rec.project_id and isinstance(res.get('mcp'), dict)):
                m = res['mcp']
                is_oauth = bool(m.get('email'))
                # OAuth no sondea (el endpoint pide login); si vino ok lo damos por arriba.
                status = 'running' if (is_oauth or str(m.get('code')) == '200') else 'stopped'
                cprefix = 'mcp-oauth-' if is_oauth else 'mcp-'
                rec.project_id.sudo().write({
                    'despacho_mcp_enabled': True,
                    'despacho_mcp_status': status,
                    'despacho_mcp_url': m.get('endpoint') or False,
                    'despacho_mcp_container': (cprefix + m['slug']) if m.get('slug') else False,
                    'despacho_mcp_port': str(m['port']) if m.get('port') else False,
                    'despacho_mcp_writes': bool(m.get('writes')),
                    'despacho_mcp_health': str(m['code']) if m.get('code') else ('OAuth' if is_oauth else False),
                })
                # Reflejar también en la fila del USUARIO de "Gestión de usuarios"
                # (para que el botón cambie a "Quitar MCP" SIN esperar al censo).
                login = m.get('conn_user') or (rec.mcp_as_user or '').strip()
                if login:
                    du = self.env['databases.user'].sudo().search([
                        ('project_id', '=', rec.project_id.id),
                        ('login', '=', login)], limit=1)
                    if du:
                        du.write({
                            'despacho_mcp_enabled': True,
                            'despacho_mcp_oauth': is_oauth,
                            'despacho_mcp_slug': m.get('slug') or False,
                            'despacho_mcp_url': m.get('endpoint') or False,
                            'despacho_mcp_status': status,
                            'despacho_mcp_writes': bool(m.get('writes')),
                            'despacho_mcp_port': str(m['port']) if m.get('port') else False,
                            'despacho_mcp_health': str(m['code']) if m.get('code') else ('OAuth' if is_oauth else False),
                        })
                # Cobro: asegurar la línea recurrente 'Conexión IA (MCP)' en la
                # suscripción de esta BD (cuota plana por cliente). Si la BD no
                # tiene suscripción ligada, avisar en el chatter para que el
                # gestor la ligue (una sola vez, al volverse terminal).
                billing = rec.project_id.sudo()._sync_mcp_subscription_line()
                if billing == 'no_subscription' and not was_terminal:
                    rec.project_id.sudo().message_post(body=(
                        '⚠️ Se activó un puente MCP, pero esta base no tiene una '
                        'suscripción ligada: no se agregó el cobro de "Conexión IA '
                        '(MCP)". Liga la suscripción en la ficha y se sumará sola.'))
            # Desactivar MCP aplicado: limpiar la fila del usuario y recalcular el
            # resumen de la BD (queda enabled solo si AÚN hay otro usuario con puente).
            if (rec.op == 'mcp_remove' and res.get('state') == 'done' and rec.project_id):
                slug = (rec.mcp_slug or '').strip().lower()
                if slug:
                    du = self.env['databases.user'].sudo().search([
                        ('project_id', '=', rec.project_id.id),
                        ('despacho_mcp_slug', '=', slug)], limit=1)
                    if du:
                        du.write({
                            'despacho_mcp_enabled': False, 'despacho_mcp_slug': False,
                            'despacho_mcp_url': False, 'despacho_mcp_status': False,
                            'despacho_mcp_writes': False, 'despacho_mcp_port': False,
                            'despacho_mcp_health': False, 'despacho_mcp_oauth': False,
                        })
                any_left = bool(self.env['databases.user'].sudo().search_count([
                    ('project_id', '=', rec.project_id.id),
                    ('despacho_mcp_enabled', '=', True)]))
                if not any_left:
                    rec.project_id.sudo().write({
                        'despacho_mcp_enabled': False, 'despacho_mcp_status': False,
                        'despacho_mcp_url': False, 'despacho_mcp_container': False,
                        'despacho_mcp_port': False, 'despacho_mcp_writes': False,
                        'despacho_mcp_health': False,
                    })
                # Cobro: re-sincronizar la línea de la suscripción (la deja en 0
                # si ya no queda ningún puente en la BD; en >=1 la conserva).
                rec.project_id.sudo()._sync_mcp_subscription_line()
            # Aviso al creador cuando la operación TERMINA (cubre las largas que el
            # poll de action_provision no alcanzó). Solo en la transición a terminal.
            if (not skip_notify and not was_terminal
                    and rec.state in ('done', 'error')):
                rec._notify_outcome()
        return True

    @api.model
    def _cron_refresh(self):
        self.search([('state', 'in', ('queued', 'running'))]).action_refresh()
