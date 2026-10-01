// Private administration HTML from the real PHP class. Fictitious in-memory data only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
const php = process.env.PHP_TEST_COMMAND || 'php';
let tests = 0;
async function check(name, task) { await task(); tests++; console.log('OK ' + name); }
function html(mode) {
  const result = spawnSync(php, [path.join(__dirname, 'test_wordpress_test_maintenance.php'), 'html', mode],
    {encoding: 'utf8', env: {...process.env, PHP: '8.1'}});
  assert.equal(result.status, 0, result.stderr);
  assert(!/Fatal error|Parse error|Warning:/.test(result.stdout + result.stderr));
  return result.stdout;
}
(async () => {
  const chrome = process.env.TEST_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({headless: true, ...(fs.existsSync(chrome) ? {executablePath: chrome} : {})});
  const snippets = Object.fromEntries(['analyse', 'preview', 'done', 'denied'].map(mode => [mode, html(mode)]));
  try {
    async function page(mode, width = 1280, height = 800) {
      const p = await browser.newPage({viewport: {width, height}});
      await p.route('**/*', route => route.abort()); // No real site or network allowed.
      await p.setContent(snippets[mode]);
      return p;
    }
    await check('private diagnostic, computed seats, no preselection or contacts', async () => {
      const p = await page('analyse'); const section = p.locator('#openfablab-test-maintenance');
      const text = await section.textContent();
      assert(text.includes('Capacité 6 − 4 places occupées = 2 disponibles'));
      assert(text.includes('Annulation : Oui') && text.includes('Liste d’attente : Oui'));
      assert(!text.includes('example.invalid') && !text.includes('0600000000') && !text.includes('token-hash'));
      assert.equal(await section.locator('input[type=checkbox]:checked').count(), 0);
      assert.equal(await section.locator('tbody tr').count(), 6);
      assert.equal(await section.locator('button[value=clean]').count(), 0);
      assert((await section.innerHTML()).includes('Anne &lt;TEST&gt;'));
      await p.close();
    });
    await check('preview carries exact selected IDs, scoped nonce and strong confirmation', async () => {
      const p = await page('preview'); const form = p.locator('form').filter({has: p.locator('button[value=clean]')});
      assert.deepEqual(await form.locator('input[name="reservation_ids[]"]').evaluateAll(nodes => nodes.map(n => n.value)), ['1', '2', '3']);
      assert.equal(await form.locator('[name=environment]').inputValue(), 'test');
      assert.equal(await form.locator('[name=service_id]').inputValue(), '29');
      assert.equal(await form.locator('[name=_wpnonce]').count(), 1);
      assert.equal((await form.locator('[name=preview_fingerprint]').inputValue()).length, 64);
      assert((await form.textContent()).includes('PURGER TEST 29'));
      assert.equal(await form.locator('[name=orphans_confirmed]').isChecked(), false);
      assert.equal(await form.evaluate(node => node.checkValidity()), false);
      await form.locator('[name=confirmation]').fill('PURGER TEST 29');
      assert.equal(await form.evaluate(node => node.checkValidity()), false);
      await form.locator('[name=orphans_confirmed]').check();
      assert.equal(await form.evaluate(node => node.checkValidity()), true);
      await p.close();
    });
    await check('result and private audit, no NAS email or list promotion', async () => {
      const p = await page('done'); const text = await p.textContent('body');
      assert(text.includes('Avant : 4 occupées / 2 disponibles. Après : 1 occupées / 5 disponibles.'));
      assert(text.includes('utilisateur WordPress #7') && text.includes('places libérées : 3'));
      assert.equal(await p.locator('input[name="reservation_ids[]"]').count(), 2); // current + waitlisted only
      await p.close();
    });
    await check('non-admin sees no private maintenance or identity', async () => {
      const p = await page('denied'); assert.equal(await p.locator('#openfablab-test-maintenance').count(), 0);
      assert(!(await p.textContent('body')).includes('Anne')); await p.close();
    });
    for (const [name, width, height] of [['MacBook',1440,900], ['tablette',1280,800], ['iPhone',390,844]]) {
      await check('responsive administration ' + name, async () => {
        const p = await page('preview', width, height);
        assert(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        for (const button of await p.locator('button').all()) {
          const rect = await button.boundingBox(); assert(rect && rect.x >= 0 && rect.x + rect.width <= width + 1);
        }
        await p.screenshot({path:path.join(process.env.TMPDIR || '/tmp', 'openfablab-maintenance-' + name + '.png'),fullPage:true});
        await p.close();
      });
    }
    console.log(tests + ' JavaScript maintenance UI tests passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
