// Actual Flask pages and native JS. Browser requests outside this fixture abort.
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const {spawn}=require('node:child_process');const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:5069';let checks=0;
async function check(name,fn){await fn();checks++;console.log('OK '+name);}
(async()=>{
 const fixture=spawn(process.env.TEST_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'evolution_fixture.py'),'5069'],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
 let error='',browser;fixture.stderr.on('data',b=>error+=b);fixture.stdout.resume();
 try{
  let ready=false;for(let n=0;n<100;n++){if(fixture.exitCode!==null)throw Error(error);try{ready=(await fetch(base+'/sante')).ok;}catch(_){}if(ready)break;await new Promise(r=>setTimeout(r,100));}assert(ready,error);
  const chrome=process.env.TEST_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  browser=await chromium.launch({headless:true,...(fs.existsSync(chrome)?{executablePath:chrome}:{})});
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>r.request().url().startsWith(base+'/')?r.continue():r.abort());
  async function login(pin='1379'){await page.goto(base+'/admin/connexion');await page.locator('[name="pin"]').fill(pin);await Promise.all([page.waitForNavigation(),page.locator('button[type="submit"]').click()]);}
  await login();
  for(const [name,width,height] of [['desktop',1440,1000],['1024',1024,900],['tablette',820,1180],['768',768,1024],['430',430,932],['mobile',390,844],['375',375,812],['360',360,800],['320',320,740]]){
   await page.setViewportSize({width,height});
   for(const [key,url] of [['categories','/admin/reglages/usagers'],['integrations','/admin/reglages/structure'],['notifications','/admin/reglages/notifications'],['data','/admin/reglages/donnees'],['activities','/admin/activites'],['resources','/admin/ressources'],['authorizations','/admin/habilitations'],['reservations','/admin/ressources/reservations'],['calendar-week','/admin/calendrier?date=2099-10-08'],['calendar-month','/admin/calendrier?date=2099-10-08&view=month']]){
    await check(key+' '+name+' responsive',async()=>{
     await page.goto(base+url);assert.equal(await page.locator('h1').count(),1);
     const expectedTab=key.startsWith('calendar')?'Calendrier':(['categories','integrations','notifications','data'].includes(key)?'Réglages':'Activités');
     assert.equal(await page.locator('.admin-tabs .active').innerText(),expectedTab);
     assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),key+' global overflow');
     if(await page.locator('.settings-subtabs').count()){
       assert.deepEqual(await page.locator('.settings-subtabs a').allTextContents(),['Affichage','Usagers','Borne','Notifications','Tarifs','Données','Structure']);
       assert(await page.locator('.settings-subtabs').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
       if(width>=768){const tops=await page.locator('.settings-subtabs a').evaluateAll(els=>els.map(el=>Math.round(el.getBoundingClientRect().top)));assert.equal(new Set(tops).size,1);}
     }
     if(key==='calendar-week'){
       assert.equal(await page.locator('.calendar-event').filter({hasText:/Exemple/}).count(),2);assert.equal(await page.locator('.calendar-grid .calendar-day').count(),7);
       assert(await page.locator('.calendar-scroll').evaluate(el=>el.scrollHeight<=el.clientHeight+1));
       assert(await page.locator('.calendar-hours .calendar-day-label').evaluate(el=>el.scrollWidth<=el.clientWidth));
       assert.equal(await page.locator('.calendar-timeline').first().evaluate(el=>el.clientHeight),600);
     }
     if(key==='categories'){assert.equal(await page.locator('.category-danger[open]').count(),0);assert(await page.locator('input[type="color"]').first().evaluate(el=>el.clientWidth<=56));}
     if(process.env.UI_SCREENSHOT_DIR&&['desktop','mobile'].includes(name)&&key==='categories')await page.locator('.category-section').screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'revision-category-cards-'+name+'.png')});
     if(process.env.UI_SCREENSHOT_DIR&&['desktop','mobile'].includes(name)&&key==='resources')await page.locator('section.admin-section').filter({has:page.getByRole('heading',{name:'Catégories de ressources',exact:true})}).screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'revision-resource-categories-'+name+'.png')});
     if(process.env.UI_SCREENSHOT_DIR&&['desktop','tablette','mobile','320'].includes(name)&&['categories','resources','calendar-week','integrations','authorizations','data','notifications','activities'].includes(key))await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'revision-'+key+'-'+name+'.png'),fullPage:false});
    });
   }
  }
  for(const width of [1440,1024,820,768,430,390,375,360,320])await check('kiosk footer '+width+'px',async()=>{
   await page.setViewportSize({width,height:900});await page.goto(base+'/');
   assert.equal(await page.locator('a').filter({hasText:/^Créer un compte$/}).count(),1);
   assert.equal(await page.locator('footer a').last().innerText(),'Créer un compte');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  });
  await check('welcome opt-in only for valid email, default unchecked',async()=>{
   await page.goto(base+'/admin/usagers/nouveau');const box=page.locator('[data-welcome-email]');
   assert(await box.isDisabled());await page.locator('[name="email"]').fill('camille@example.invalid');assert(await box.isEnabled());assert(!(await box.isChecked()));
   await box.check();await page.locator('[name="email"]').fill('invalid');assert(await box.isDisabled());assert(!(await box.isChecked()));
  });
  await check('kiosk shared form locks privileged session and returns QR receipt',async()=>{
   await page.goto(base+'/inscription');assert.equal(await page.locator('h1').innerText(),'Créer mon compte');
   assert.equal(await page.locator('[name="category"]').count(),0);assert.equal(await page.locator('[name="public_id"]').count(),0);
   await page.locator('[name="first_name"]').fill('Éloïse-Exemple');await page.locator('[name="last_name"]').fill('FICTIF');
   await Promise.all([page.waitForNavigation(),page.locator('.form-actions button').click()]);
   assert(page.url().includes('/inscription/terminee'));await page.locator('img').last().evaluate(img=>img.decode());
   await page.goto(base+'/admin/calendrier');assert(page.url().includes('/admin/connexion'));
   if(process.env.UI_SCREENSHOT_DIR){await page.goto(base+'/inscription');await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'kiosk-mobile.png'),fullPage:true});}
  });
  await check('moderator calendar permitted, SMTP/category configuration denied',async()=>{
   await login('8642');await page.goto(base+'/admin/calendrier');assert.equal(await page.locator('h1').innerText(),'Calendrier');
   await page.goto(base+'/admin/reglages/integrations');assert(!page.url().includes('/admin/reglages/integrations'));
  });
  await check('no JavaScript exception in new pages',async()=>assert.deepEqual(errors,[]));
  console.log(checks+' evolution UI tests passed');
 }finally{if(browser)await browser.close();fixture.kill('SIGTERM');await new Promise(r=>fixture.exitCode!==null?r():fixture.once('exit',r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
