// Captura de una pantalla del sistema del cliente para mandarla por WhatsApp.
// Lo llama xb_support_agent (screenshots.py) con un JSON por stdin:
//   {base, db, token, url, resaltar, out}
// Solo NAVEGA a la vista ya validada por Python y resalta un texto: no hace clic
// en nada ni escribe. Al terminar cierra la sesión.
const { chromium } = require("playwright");

const leer = () => new Promise((ok) => {
  let s = "";
  process.stdin.on("data", (d) => (s += d));
  process.stdin.on("end", () => ok(JSON.parse(s)));
});

(async () => {
  const p = await leer();
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
  const resultado = { ok: false, resaltado: false };
  try {
    const ctx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      deviceScaleFactor: 1.5,
      locale: "es-MX",
      // El cliente web de Odoo muestra las horas en la zona del NAVEGADOR.
      timezoneId: "America/Mexico_City",
      extraHTTPHeaders: { "X-Odoo-dbfilter": p.db },
    });
    const page = await ctx.newPage();
    await page.goto(`${p.base}/despacho/autologin?token=${encodeURIComponent(p.token)}`,
                    { waitUntil: "domcontentloaded", timeout: 30000 });
    if (page.url().includes("/web/login")) throw new Error("no se pudo entrar al sistema");
    await page.goto(`${p.base}${p.url}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    // networkidle nunca se cumple en Odoo (el bus deja una conexión abierta).
    await page.waitForSelector(".o_action_manager .o_view_controller", { timeout: 30000 });
    await page.waitForTimeout(1500);
    if (p.resaltar) {
      const el = page.getByText(p.resaltar, { exact: false }).filter({ visible: true }).first();
      if (await el.count()) {
        await el.scrollIntoViewIfNeeded();
        await el.evaluate((n) => {
          n.style.outline = "4px solid #e11d48";
          n.style.outlineOffset = "3px";
          n.style.borderRadius = "4px";
          n.style.boxShadow = "0 0 0 9999px rgba(0,0,0,.18)";
          n.style.position = n.style.position || "relative";
          n.style.zIndex = "9999";
        });
        resultado.resaltado = true;
        await page.waitForTimeout(300);
      }
    }
    await page.screenshot({ path: p.out });
    resultado.ok = true;
    await page.goto(`${p.base}/web/session/logout`, { waitUntil: "domcontentloaded", timeout: 15000 })
      .catch(() => {});
  } catch (e) {
    resultado.error = String(e.message || e).slice(0, 300);
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(resultado));
})();
