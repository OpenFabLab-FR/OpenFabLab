// Actual Flask templates/CSS, isolated SQLite and local browser only. No WordPress.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:5047';
let tests = 0;
async function check(name, task) { await task(); tests++; console.log('OK ' + name); }
(async () => {
  const fixture = spawn(process.env.TEST_PYTHON || path.join(root, '.venv/bin/python'),
    [path.join(__dirname, 'participants_fixture.py'), '5047'],
    {cwd:root, env:{...process.env, PYTHONDONTWRITEBYTECODE:'1'}, stdio:['ignore','pipe','pipe']});
  let stdout = '', stderr = '', browser;
  fixture.stdout.on('data', chunk => { stdout += chunk; });
  fixture.stderr.on('data', chunk => { stderr += chunk; });
  try {
    let ready = false;
    for (let attempt=0; attempt<100; attempt++) {
      if (fixture.exitCode !== null) throw Error('Fixture stopped: ' + stderr);
      try { ready = (await fetch(base + '/sante')).ok; } catch (_) { /* Startup only. */ }
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve,100));
    }
    assert(ready, 'isolated Flask fixture unavailable');
    const data = JSON.parse(stdout.split('\n').find(line => line.startsWith('{')));
    const chrome = process.env.TEST_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
    browser = await chromium.launch({headless:true, ...(fs.existsSync(chrome) ? {executablePath:chrome} : {})});
    const page = await browser.newPage();
    // A UI regression test must never make an external request.
    await page.route('**/*', route => route.request().url().startsWith(base + '/') ? route.continue() : route.abort());
    async function login(pin) {
      await page.goto(base + '/admin/connexion');
      await page.locator('input[name="pin"]').fill(pin);
      await page.locator('button[type="submit"]').click();
      await page.waitForURL(url => !url.pathname.includes('/connexion'));
    }
    const bookings = base + '/admin/animations/' + data.service_id + '/inscriptions';
    await login('1379');
    for (const [name,width,height] of [['MacBook',1440,900],['tablette',1280,800],['iPhone',390,844]]) {
      await check(name + ': grouping, readable controls and no horizontal overflow', async () => {
        await page.setViewportSize({width,height}); await page.goto(bookings);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
        const table = page.locator('.reservation-bookings-table');
        assert(await table.evaluate(node => node.parentElement.scrollWidth <= node.parentElement.clientWidth+1));
        const row = table.locator('tbody tr').first();
        assert.deepEqual(await row.locator('td').evaluateAll(nodes => nodes.map(n => n.dataset.label)),
          ['Personne','Âge','Identifiant','Rattachement','Réservation / présence','Contact','Actions']);
        assert.equal(await row.locator('[data-label="Actions"] select').count(),0);
        for (const action of ['link','unlink','verify']) assert.equal(await row.locator('[data-label="Rattachement"] button[value="'+action+'"]').count(),1);
        assert.equal(await row.locator('.reservation-primary-actions button[value="cancel"]').count(),0);
        for (const selector of ['.reservation-export-actions .admin-button','.reservation-linkage-form select',
          '.reservation-linkage-form button','.reservation-primary-actions button','.reservation-cancel-form button',
          '.walkin-user-choice select']) {
          for (const element of await page.locator(selector).all()) {
            const rect = await element.boundingBox();
            assert(rect && rect.x>=0 && rect.x+rect.width<=width+1, selector+' must fit');
            if (selector.includes('button')) assert(rect.height>=40 && rect.width>=40, 'touch target');
          }
        }
        const actions = await row.locator('.reservation-primary-actions').boundingBox();
        const cancel = await row.locator('.reservation-cancel-form').boundingBox();
        assert(cancel.y >= actions.y+actions.height+12, 'cancellation separate from presence');
        const exports = await page.locator('.reservation-export-actions a').allTextContents();
        assert.deepEqual(exports,['Modifier','Exporter les inscriptions CSV','Exporter les inscriptions PDF']);
        if (process.env.UI_SCREENSHOT_DIR) {
          await row.scrollIntoViewIfNeeded();
          await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'participants-'+name+'.png')});
        }
        await page.goto(base + '/admin/animations');
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
        const buttons=await page.locator('.service-row-actions').first().locator('a').allTextContents();
        assert.deepEqual(buttons,['Inscriptions','Modifier','Calendrier Apple / Outlook']);
      });
    }
    await check('cancellation confirmation prevents accidental POST', async () => {
      await page.goto(bookings); let posts=0;
      const listener = request => { if(request.method()==='POST' && request.url().includes('/action')) posts++; };
      page.on('request',listener);
      page.once('dialog',dialog => { assert(dialog.message().includes('Annuler cette inscription')); return dialog.dismiss(); });
      await page.locator('.reservation-cancel-form button').first().click();
      assert.equal(posts,0);
      const posted=page.waitForRequest(request => request.method()==='POST' && request.url().includes('/action'));
      await page.route('**/inscriptions/*/action', route => route.fulfill({status:200,contentType:'text/html',body:'Simulated cancellation'}));
      page.once('dialog',dialog => dialog.accept());
      await page.locator('.reservation-cancel-form button').first().click();
      assert.equal(new URLSearchParams((await posted).postData()).get('action'),'cancel');
      assert.equal(posts,1); page.off('request',listener);
    });
    await check('Moderator sees bookings and exports but never animation editing', async () => {
      await page.context().clearCookies(); await login('8642');
      await page.goto(bookings);
      assert.deepEqual(await page.locator('.reservation-export-actions a').allTextContents(),
        ['Exporter les inscriptions CSV','Exporter les inscriptions PDF']);
      await page.goto(base + '/admin/animations');
      assert.deepEqual(await page.locator('.service-row-actions').first().locator('a').allTextContents(),
        ['Inscriptions','Calendrier Apple / Outlook']);
      await page.goto(base + '/admin/animations/'+data.service_id+'/modifier');
      assert(!new URL(page.url()).pathname.endsWith('/modifier'));
    });
    console.log(tests + ' participant UI tests passed');
  } finally {
    if(browser) await browser.close();
    fixture.kill('SIGTERM');
    await new Promise(resolve => fixture.exitCode!==null || fixture.signalCode!==null ? resolve() : fixture.once('exit',resolve));
  }
})().catch(error => {console.error(error);process.exitCode=1;});
