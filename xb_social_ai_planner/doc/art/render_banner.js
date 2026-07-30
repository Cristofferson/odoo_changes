const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH,
    args: ['--allow-file-access-from-files', '--font-render-hinting=none'],
  });
  const page = await browser.newPage({
    viewport: { width: 1200, height: 300 },
    deviceScaleFactor: 2,
  });
  await page.goto('file:///home/ubuntu/xb_social_icon/banner.html');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(600);
  await page.screenshot({ path: '/home/ubuntu/xb_social_icon/banner_2x.png' });
  await browser.close();
  console.log('ok');
})();
