import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

// Los precios de oro los recalcula un cron nocturno (02:33) reescribiendo las
// reglas de pricelist, pero el POS es una SPA: una pestaña que no se recarga
// sigue vendiendo con los precios del día que se abrió. No existe ningún canal
// bus que empuje precios a una pestaña abierta, así que la única corrección
// posible es recargar la página. Aquí: cada 5 min, si los datos cargados son
// anteriores a la última corrida del cron (~03:00 como margen) y NO hay ninguna
// venta en curso, se recarga en silencio. La recarga resetea loadedAt, por lo
// que ocurre a lo más una vez al día por caja.

const CRON_SAFE_HOUR = 3; // el cron de oro corre 02:33; a las 03:00 ya terminó
const CHECK_EVERY_MS = 5 * 60 * 1000;

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this._priceReloadLoadedAt = new Date();
        setInterval(() => this._priceReloadCheck(), CHECK_EVERY_MS);
    },
    _priceReloadCheck() {
        try {
            const now = new Date();
            const lastCronRun = new Date(now);
            lastCronRun.setHours(CRON_SAFE_HOUR, 0, 0, 0);
            if (now < lastCronRun) {
                lastCronRun.setDate(lastCronRun.getDate() - 1);
            }
            if (this._priceReloadLoadedAt >= lastCronRun) {
                return; // datos ya posteriores al último recálculo de precios
            }
            const busy = this.getOpenOrders().some((o) => !o.isEmpty());
            if (busy) {
                return; // no interrumpir ventas; se reintenta en 5 min
            }
            window.location.reload();
        } catch {
            // nunca dejar que esta rutina rompa el POS
        }
    },
});
