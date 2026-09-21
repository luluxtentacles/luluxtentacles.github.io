// render my pages off disk headlessly, screenshot them for a visual check
const { chromium } = require('C:/lulu/node_cache/_npx/86170c4cd1c5da32/node_modules/playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  for (const [file, out] of [
    ['about.html', 'about.png'],
    ['blog/index.html', 'grimoire.png'],
    ['index.html', 'front.png'],
  ]) {
    await page.goto('file:///C:/lulu/projects/site/' + file, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'screenshots/' + out });
    console.log('shot', out);
  }
  await browser.close();
})().catch(e => { console.error(e.message); process.exit(1); });
