from . import models
from . import controllers


def _post_init_marketplace(env):
    """Amarra los servicios de personalización al website/compañía del
    marketplace (para que no aparezcan en las tiendas de otras compañías)
    y deja creadas las cuentas del escrow."""
    products = env['product.template']
    for xmlid in ('xb_marketplace.svc_ajuste_talla',
                  'xb_marketplace.svc_restauracion',
                  'xb_marketplace.svc_grabado_joya',
                  'xb_marketplace.svc_inscripcion_piedra'):
        rec = env.ref(xmlid, raise_if_not_found=False)
        if rec:
            products |= rec
    if products:
        products._bind_to_marketplace()
