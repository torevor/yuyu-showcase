// Screenshot live showcase items into card thumbnails.
// Reads a JSON array of {url, out, wait?} and writes each to <out> (viewport thumbnail).
// Usage: node shot_urls.js targets.json
//
// Used in Wave 3 to thumbnail the existing standalone items over the Tailscale mirror
// (http://100.74.37.45:8090/...), where they serve directly with no Access gate.
const fs = require('fs');
const path = require('path');

function findPlaywright() {
  const candidates = [
    'C:/Users/trevo/AppData/Roaming/npm/node_modules/@playwright/mcp/node_modules/playwright',
    'playwright',
  ];
  for (const c of candidates) { try { return require(c); } catch (e) {} }
  throw new Error('playwright not found');
}

(async () => {
  const targets = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
  const { chromium } = findPlaywright();
  const b = await chromium.launch();
  let ok = 0, fail = 0;
  for (const t of targets) {
    try {
      const ctx = await b.newContext({ viewport: { width: 1200, height: 750 }, deviceScaleFactor: 1.5 });
      const p = await ctx.newPage();
      await p.goto(t.url, { waitUntil: 'networkidle', timeout: 25000 }).catch(() => {});
      await p.waitForTimeout(t.wait || 2500);
      fs.mkdirSync(path.dirname(t.out), { recursive: true });
      await p.screenshot({ path: t.out, type: 'jpeg', quality: 82, fullPage: false });
      await ctx.close();
      console.log('OK   ' + t.out);
      ok++;
    } catch (e) {
      console.log('FAIL ' + t.out + '  ' + e.message);
      fail++;
    }
  }
  await b.close();
  console.log(`DONE ${ok} ok, ${fail} failed`);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
