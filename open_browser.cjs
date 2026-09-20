// Master's window: Lulu's browser profile, headed, through her proxy.
// Uses the SYSTEM Edge (channel 'msedge') because Google refuses sign-in on
// playwright's "Chrome for Testing" build ("this browser might not be secure").
// Same door she uses, so logins made here are hers.
const { chromium } = require('C:/lulu/node_cache/_npx/86170c4cd1c5da32/node_modules/playwright');

(async () => {
  const ctx = await chromium.launchPersistentContext('C:/lulu/browser-profile', {
    channel: 'msedge',
    headless: false,
    proxy: { server: 'http://127.0.0.1:38123' },
    viewport: null,
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.goto('https://www.google.com');
  console.log('Edge open with Lulu\'s profile, proxy 38123');
})().catch(e => { console.error(e.message); process.exit(1); });