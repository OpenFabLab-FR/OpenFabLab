// Real browser DOM and actual vanilla plugin JS; all requests mocked, no WordPress.
// NODE_PATH can point to a development Playwright installation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
const plugin = path.join(root, 'tests/historical-wordpress');
const names = ['first_name', 'last_name', 'birth_year', 'email', 'phone'];
const user = {status:'matched', first_name:'Élise-Anne', last_name:'DU PONT', birth_year:1990,
  email:'elise@example.invalid', phone:'+33600000000', masked_identity:'É****-A*** D* P***',
  verification_token:'fixture-proof'};
let tests = 0;
async function check(name, task) { await task(); tests++; console.log('OK ' + name); }
(async () => {
  const chrome = process.env.TEST_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const browser = await chromium.launch({headless:true, ...(fs.existsSync(chrome) ? {executablePath:chrome} : {})});
  async function fixture(width=1280, height=800, verifyReply=user) {
    const page = await browser.newPage({viewport:{width,height}});
    const calls = [];
    await page.route('**/*', async route => {
      const req = route.request();
      if (!req.url().startsWith('https://example.invalid/')) return route.abort();
      calls.push({url:req.url(), data:req.postDataJSON()});
      let body = {};
      if (req.url().includes('/animations?')) body = {animations:[{
        service_id:1, title:'Atelier Test', starts_at:'2099-11-12T14:00:00Z', ends_at:'2099-11-12T15:00:00Z',
        timezone:'Europe/Paris', audience:'all', minimum_age:10, accompaniment_under_age:15,
        available:5, waitlist_enabled:true, registration_open:true,
      }]};
      if (req.url().endsWith('/verify')) body = typeof verifyReply==='function' ? await verifyReply() : verifyReply;
      if (req.url().endsWith('/reserve')) body = {message:'Réservation simulée'};
      return route.fulfill({status:200, contentType:'application/json', body:JSON.stringify(body)});
    });
    await page.setContent('<section class="openfablab-reservations" data-environment="test"><div class="openfablab-status"></div><div class="openfablab-animation-list"></div><div class="openfablab-form-host"></div></section>');
    await page.addStyleTag({path:path.join(plugin,'assets/reservations.css')});
    await page.evaluate(() => { window.OpenFabLabReservations={api:'https://example.invalid/',privacy:'https://example.invalid/privacy'}; });
    await page.addScriptTag({path:path.join(plugin,'assets/reservations.js')});
    await page.locator('.openfablab-card button').click();
    const form = page.locator('.openfablab-booking-form');
    const field = name => form.locator('[name="'+name+'"]');
    await form.locator('[name="user_kind"][value="registered"]').check();
    return {page, form, field, calls};
  }
  async function verified(f, email='elise@example.invalid', phone='') {
    await f.field('public_id').fill('1234'); await f.field('email').fill(email); await f.field('phone').fill(phone);
    await f.form.getByText('Vérifier mon compte',{exact:true}).click();
    await f.form.locator('.openfablab-verification').getByText('Compte reconnu : É****-A*** D* P***',{exact:true}).waitFor();
  }
  try {
    await check('no initial directory identity, correct copy, editable mandatory fields', async () => {
      const f=await fixture(); const text=await f.form.textContent();
      assert(!text.includes('Élise-Anne') && !text.includes('elise@example.invalid'));
      assert(!text.includes('Une réservation = une place = une personne.'));
      assert(text.includes('Les informations demandées sont utilisées pour gérer votre réservation ou vous contacter à ce sujet.'));
      assert(text.includes('Réservation conseillée avec votre identifiant usager, mais possibilité de réserver sans cela'));
      assert.equal(await f.form.getByText('En savoir plus sur la gestion de vos données').getAttribute('href'),'https://example.invalid/privacy');
      for(const name of names) assert(await f.field(name).evaluate(node=>node.required && !node.readOnly && !node.disabled));
      const order=await f.form.locator('.openfablab-fields input').evaluateAll(nodes=>nodes.map(n=>n.name));
      assert(order.indexOf('public_id')<order.indexOf('email') && order.indexOf('phone')<order.indexOf('first_name'));
      await f.page.close();
    });
    for(const [name,email,phone] of [['email only','elise@example.invalid',''],['phone only','','0600000000'],['both contacts','elise@example.invalid','0600000000']]) {
      await check('prefill '+name, async () => {
        const f=await fixture(); await verified(f,email,phone);
        for(const field of names) assert.equal(await f.field(field).inputValue(),String(user[field]));
        assert((await f.form.textContent()).includes('Vos informations peuvent maintenant être préremplies. Elles restent modifiables pour cette réservation.'));
        await f.page.close();
      });
    }
    await check('editable reservation retains verification, no master write', async () => {
      const f=await fixture(); await verified(f);
      await f.field('first_name').fill('Autre prénom'); await f.field('email').fill('changed@example.invalid'); await f.field('phone').fill('0611111111');
      await f.form.getByText('Confirmer la réservation',{exact:true}).click();
      await f.form.locator('.openfablab-feedback').getByText('Réservation simulée',{exact:true}).waitFor();
      const request=f.calls.find(call=>call.url.endsWith('/reserve'));
      assert.equal(request.data.first_name,'Autre prénom'); assert.equal(request.data.verification_token,'fixture-proof');
      assert.equal(request.data.email,'changed@example.invalid'); assert.equal(user.first_name,'Élise-Anne');
      assert(f.calls.every(call=>call.url.includes('/animations?') || /\/(verify|reserve)$/.test(call.url)));
      await f.page.close();
    });
    for(const name of names) {
      await check('browser requires final '+name, async () => {
        const f=await fixture(); await verified(f); await f.field(name).fill('');
        await f.form.getByText('Confirmer la réservation',{exact:true}).click();
        assert(!f.calls.some(call=>call.url.endsWith('/reserve'))); await f.page.close();
      });
    }
    await check('unverified response reveals no identity', async () => {
      const f=await fixture(1280,800,{status:'unverified',message:'Compte non reconnu. Vérifiez votre identifiant et vos coordonnées.'});
      await f.field('public_id').fill('9999'); await f.field('email').fill('wrong@example.invalid');
      await f.form.getByText('Vérifier mon compte',{exact:true}).click();
      await f.form.locator('.openfablab-verification').getByText('Compte non reconnu.',{exact:false}).waitFor();
      assert.equal(await f.field('first_name').inputValue(),''); assert.equal(await f.field('last_name').inputValue(),'');
      assert(!(await f.form.textContent()).includes('Élise')); await f.page.close();
    });
    await check('stale verification cannot fill another ID', async () => {
      let finish; const pending=new Promise(resolve=>{finish=resolve;}); const f=await fixture(1280,800,()=>pending);
      await f.field('public_id').fill('1234'); await f.field('email').fill('elise@example.invalid');
      const request=f.page.waitForRequest('**/verify');
      await f.form.getByText('Vérifier mon compte',{exact:true}).click();
      await request; await f.field('public_id').fill('5678');
      const response=f.page.waitForResponse('**/verify'); finish(user); await response;
      assert.equal(await f.field('first_name').inputValue(),''); assert(!(await f.form.textContent()).includes('Compte reconnu')); await f.page.close();
    });
    await check('Visitor clears only unedited injected fields', async () => {
      const f=await fixture(); await verified(f); await f.field('first_name').fill('Saisie volontaire');
      await f.form.locator('[name="user_kind"][value="visitor"]').check();
      assert.equal(await f.field('first_name').inputValue(),'Saisie volontaire');
      for(const name of names.filter(n=>n!=='first_name')) assert.equal(await f.field(name).inputValue(),'');
      assert.equal(await f.field('public_id').inputValue(),''); await f.page.close();
    });
    await check('minor companion needs email and phone', async () => {
      const f=await fixture(); await verified(f); await f.field('birth_year').fill('2085');
      assert(await f.form.locator('.openfablab-companion').isVisible());
      for(const name of ['companion_first_name','companion_last_name','companion_birth_year','companion_email','companion_phone']) {
        assert(await f.field(name).evaluate(node=>node.required));
      }
      await f.form.getByText('Confirmer la réservation',{exact:true}).click();
      assert(!f.calls.some(call=>call.url.endsWith('/reserve'))); await f.page.close();
    });
    for(const [width,height,label] of [[1280,800,'MacBook'],[1280,800,'tablet landscape'],[390,844,'iPhone portrait'],[844,390,'iPhone landscape']]) {
      await check('responsive '+label, async () => {
        const f=await fixture(width,height); await verified(f);
        assert(await f.page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
        await f.page.screenshot({path:path.join(process.env.TMPDIR||'/tmp','openfablab-public-'+label.replace(/ /g,'-')+'.png'),fullPage:true});
        await f.page.close();
      });
    }
    if(process.env.PHP_TEST_COMMAND) {
      await check('WordPress shortcode Copy buttons and selection fallback', async () => {
        const result=spawnSync(process.env.PHP_TEST_COMMAND,[path.join(__dirname,'test_wordpress_public.php'),'admin-html'],{encoding:'utf8',env:{...process.env,PHP:'8.1'}});
        assert.equal(result.status,0); assert(!/Fatal error|Parse error/.test(result.stdout+result.stderr));
        const page=await browser.newPage(); await page.setContent(result.stdout);
        await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copied=text;}},configurable:true}));
        await page.locator('[data-openfablab-copy="openfablab-shortcode-production"]').click();
        assert.equal(await page.evaluate(()=>window.copied),'[openfablab_reservations environment="production"]');
        await page.locator('[data-openfablab-copy="openfablab-shortcode-test"]').click();
        assert.equal(await page.evaluate(()=>window.copied),'[openfablab_reservations environment="test"]');
        await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true}));
        await page.locator('[data-openfablab-copy="openfablab-shortcode-test"]').click();
        assert.equal(await page.locator('#openfablab-shortcode-test').evaluate(node=>node.value.slice(node.selectionStart,node.selectionEnd)),'[openfablab_reservations environment="test"]');
        await page.close();
      });
    }
    console.log('JS public: '+tests+' tests passed');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
