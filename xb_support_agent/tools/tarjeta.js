// Dibuja la tarjeta personalizada de BNI (HTML → imagen). Lo llama xb_support_agent (bni_card.py)
// con un JSON por stdin: {html, out}. No navega a ningún sitio: solo pinta el HTML recibido.
const { chromium } = require("playwright");
const leer = () => new Promise((ok) => {
  let s = "";
  process.stdin.on("data", (d) => (s += d));
  process.stdin.on("end", () => ok(JSON.parse(s)));
});
(async () => {
  const p = await leer();
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
  const r = { ok: false };
  try {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1350 }, deviceScaleFactor: 1 });
    await page.setContent(p.html, { waitUntil: "load" });
    await page.screenshot({ path: p.out });
    r.ok = true;
  } catch (e) {
    r.error = String(e.message || e).slice(0, 300);
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(r));
})();
