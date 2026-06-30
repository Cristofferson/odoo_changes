"""Utilidades para saber, desde Odoo, el estado del buzón humano de un usuario.

El correo (Postfix/Dovecot virtual) vive en ESTE box. Los mapas de Postfix son
legibles por el usuario `odoo` (644), así que podemos calcular sin privilegios:
  - qué dominios HOSPEDAMOS (vmail_domains)
  - qué buzones YA EXISTEN (vmail_mailbox)

Estado de <cuenta>@<dominio>:
  'exists'  -> el buzón ya existe (no ofrecer crearlo)
  'can'     -> hospedamos el dominio y el buzón no existe (ofrecer "Crear buzón")
  'cannot'  -> no hay cuenta/dominio derivable, o no hospedamos ese dominio
               (p.ej. login @gmail.com) -> no hay manera de crearlo aquí
"""
VMAIL_DOMAINS = '/etc/postfix/vmail_domains'
VMAIL_MAILBOX = '/etc/postfix/vmail_mailbox'


def hosted_domains():
    out = set()
    try:
        with open(VMAIL_DOMAINS) as fh:
            for line in fh:
                parts = line.split()
                if parts:
                    out.add(parts[0].strip().lower())
    except OSError:
        pass
    return out


def existing_mailboxes():
    out = set()
    try:
        with open(VMAIL_MAILBOX) as fh:
            for line in fh:
                parts = line.split()
                if parts:
                    out.add(parts[0].strip().lower())
    except OSError:
        pass
    return out


def mailbox_parts(login, email=''):
    """De un login/correo -> (cuenta, dominio). Prefiere el login si parece correo;
    si no, usa el email. Si ninguno sirve, ('', '')."""
    login = (login or '').strip().lower()
    src = login if '@' in login else (email or '').strip().lower()
    if '@' in src:
        local, _, dom = src.partition('@')
        return local, dom
    return '', ''


def mailbox_state(local, dom, domains=None, boxes=None):
    if not local or not dom:
        return 'cannot'
    if domains is None:
        domains = hosted_domains()
    if boxes is None:
        boxes = existing_mailboxes()
    if ('%s@%s' % (local, dom)) in boxes:
        return 'exists'
    if dom in domains:
        return 'can'
    return 'cannot'
