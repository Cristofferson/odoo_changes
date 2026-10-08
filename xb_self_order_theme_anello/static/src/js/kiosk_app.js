/**
 * El kiosco como app: registra el service worker (para que Chrome lo pueda instalar) y,
 * si se abrió en el navegador normal, pasa a pantalla completa con el primer toque.
 */
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/xb-kiosk/sw.js", { scope: "/pos-self/" }).catch(() => {});
}
const instalada = () =>
    window.matchMedia("(display-mode: fullscreen)").matches ||
    window.matchMedia("(display-mode: standalone)").matches;
document.addEventListener(
    "pointerdown",
    () => {
        if (!instalada() && !document.fullscreenElement && document.documentElement.requestFullscreen) {
            document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
        }
    },
    { capture: true }
);
