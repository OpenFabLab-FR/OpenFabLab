// Real Flask routes, real browser input, fictional data and external requests denied.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');const {chromium,webkit}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:5071';let checks=0;
const screenshot=process.env.UI_SCREENSHOT_DIR;
async function check(name,fn){await fn();checks++;console.log('OK '+name);}
(async()=>{
 const fixture=spawn(process.env.TEST_PYTHON||'python3',[path.join(__dirname,'corrective_fixture.py'),'5071'],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
 let error='';fixture.stderr.on('data',b=>error+=b);fixture.stdout.resume();
 try{
  let ready=false;for(let i=0;i<100;i++){if(fixture.exitCode!==null)throw Error(error);try{ready=(await fetch(base+'/sante')).ok;}catch(_){}if(ready)break;await new Promise(r=>setTimeout(r,100));}assert(ready,error);
  const engines=[['Chromium',chromium]];
  if(fs.existsSync(webkit.executablePath()))engines.push(['WebKit',webkit]);else console.log('WEBKIT=NOT_INSTALLED (not tested)');
  for(const [engine,type] of engines){
   const browser=await type.launch({headless:true,...(engine==='Chromium'?{executablePath:process.env.TEST_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}:{})});
   try{
    const context=await browser.newContext({hasTouch:true}),page=await context.newPage(),errors=[],external=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',r=>{if(r.request().url().startsWith(base+'/'))return r.continue();external.push(r.request().url());return r.abort();});
    async function login(pin='1379'){await page.goto(base+'/admin/connexion');if(await page.locator('[name="pin"]').count()){await page.locator('[name="pin"]').fill(pin);await Promise.all([page.waitForNavigation(),page.locator('button[type="submit"]').click()]);}}
    await check(engine+' segmented login and masked input',async()=>{
     await page.goto(base+'/admin/connexion');assert.equal(await page.getByRole('radio').count(),2);
     await page.getByRole('radio',{name:'Modérateur'}).check();assert(await page.getByRole('radio',{name:'Modérateur'}).isChecked());
     assert.equal(await page.locator('[name="pin"]').getAttribute('type'),'password');assert.equal(await page.locator('[name="pin"]').getAttribute('maxlength'),'4');
     await page.locator('[name="pin"]').fill('0000');await Promise.all([page.waitForNavigation(),page.locator('button[type="submit"]').click()]);
     assert(await page.getByRole('alert').isVisible());assert(await page.getByRole('radio',{name:'Modérateur'}).isChecked());
     if(screenshot&&engine==='Chromium')await page.screenshot({path:path.join(screenshot,'after-login-desktop.png')});
    });
    await login();
    const routes=[['categories','/admin/reglages/usagers'],['notifications','/admin/reglages/notifications'],['resources','/admin/ressources'],['authorizations','/admin/habilitations'],['calendar-week','/admin/calendrier?date=2026-10-03'],['calendar-month','/admin/calendrier?date=2026-10-03&view=month'],['day','/admin/frequentation/journee?date=2026-10-03']];
    for(const width of [1440,1280,1024,820,768,430,390,375,360,320]){
     await page.setViewportSize({width,height:1000});
     for(const [name,url] of routes)await check(engine+' '+name+' '+width+'px',async()=>{
      await page.goto(base+url);assert.equal(await page.locator('h1').count(),1);
      if(name==='day'){
       await page.locator('[data-session-toggle]').first().click();assert(await page.locator('.session-detail-row').first().isVisible());
       assert.equal(await page.locator('[data-session-toggle]').first().getAttribute('aria-expanded'),'true');
       assert(await page.locator('.session-detail-row input[name="date"]').first().evaluate(el=>el===document.activeElement));
       assert.equal(await page.locator('.session-detail-row td').first().getAttribute('colspan'),'6');
      }
      if(name==='resources'){
       await page.locator('.resource-edit > summary').first().click();
       assert.equal(await page.locator('[name="price_euros"]').first().getAttribute('inputmode'),'decimal');
      }
      if(name==='categories'||name==='notifications'){
       const tops=await page.locator('.settings-subtabs a').evaluateAll(els=>els.map(el=>Math.round(el.getBoundingClientRect().top)));
       assert(new Set(tops).size<=(width<601?2:1),'settings tabs row count');
      }
      const overflow=await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(el=>!el.closest('.calendar-scroll,.openlab-traffic-scroll,.admin-tabs,.admin-subtabs,.table-scroll')&&el.getBoundingClientRect().right>innerWidth+2).map(el=>el.tagName+'.'+el.className).slice(0,8));
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' global overflow '+overflow.join(','));
      if(screenshot&&engine==='Chromium'&&[1440,820,390,320].includes(width)&&['notifications','resources','authorizations','calendar-week','calendar-month','day'].includes(name))await page.screenshot({path:path.join(screenshot,'after-'+name+'-'+width+'.png'),fullPage:false});
      if(name==='day'){
       await page.locator('.session-detail-row input[name="date"]').first().press('Escape');
       assert(await page.locator('.session-detail-row').first().isHidden());assert(await page.locator('[data-session-toggle]').first().evaluate(el=>el===document.activeElement));
      }
     });
    }
    await page.setViewportSize({width:1280,height:1000});
    await check(engine+' keyboard ordering and saved reload',async()=>{
     await page.goto(base+'/admin/reglages/usagers');
     assert.equal(await page.locator('[name="order"]').count(),0);
     const keys=await page.locator('[data-order-key]').evaluateAll(els=>els.map(el=>el.dataset.orderKey));
     const button=page.locator('[data-order-key]').nth(1).locator('[data-order-move="-1"]');
     await button.focus();await button.press('Enter');
     await page.waitForFunction(()=>document.querySelector('[data-order-status]').textContent==='Ordre enregistré.');
     await page.reload();const after=await page.locator('[data-order-key]').evaluateAll(els=>els.map(el=>el.dataset.orderKey));
     assert.deepEqual(after,[keys[1],keys[0],...keys.slice(2)]);
    });
    await check(engine+' pointer handle ordering',async()=>{
     const keys=await page.locator('[data-order-key]').evaluateAll(els=>els.map(el=>el.dataset.orderKey));
     await page.locator('[data-order-key]').first().locator('.drag-handle').scrollIntoViewIfNeeded();
     await page.locator('[data-order-key]').nth(1).scrollIntoViewIfNeeded();
     const handle=await page.locator('[data-order-key]').first().locator('.drag-handle').boundingBox();
     const target=await page.locator('[data-order-key]').nth(1).boundingBox();
     await page.mouse.move(handle.x+20,handle.y+20);await page.mouse.down();
     await page.mouse.move(target.x+100,target.y+target.height-10,{steps:15});await page.mouse.up();
     await page.waitForFunction(()=>document.querySelector('[data-order-status]').textContent==='Ordre enregistré.');
     await page.reload();const after=await page.locator('[data-order-key]').evaluateAll(els=>els.map(el=>el.dataset.orderKey));
     assert.deepEqual(after,[keys[1],keys[0],...keys.slice(2)]);
    });
    await check(engine+' autosave category color and inactive statistics',async()=>{
     const field=page.locator('[data-order-key="staff"] input[name="color"]');
     await field.fill('#147a39');await field.dispatchEvent('change');
     await page.waitForFunction(()=>document.querySelector('[data-order-status]').textContent==='Réglages enregistrés.');
     await page.goto(base+'/admin/usagers');
     const badge=page.locator('.category-badge.category-staff').first();
     assert.equal(await badge.evaluate(el=>getComputedStyle(el,'::before').backgroundColor),'rgb(20, 122, 57)');
     assert(!await page.getByText('Historique / inconnue').count());
     await page.goto(base+'/admin/frequentation/statistiques?year=total');
     assert.equal(await page.locator('.category-badge.category-intern').count(),0);
     await page.locator('[name="show_inactive"]').check();await Promise.all([page.waitForNavigation(),page.locator('form').filter({has:page.locator('[name="show_inactive"]')}).getByRole('button',{name:'Afficher',exact:true}).click()]);
     assert(await page.locator('.category-badge.category-intern').count()>0);
    });
    await check(engine+' calendar keyboard dialog and focus return',async()=>{
     await page.goto(base+'/admin/calendrier?date=2026-10-03');
     const event=page.locator('[data-calendar-detail]').filter({hasText:'Laser Exemple'}).first();
     await event.focus();await event.press('Enter');assert(await page.getByRole('dialog').isVisible());
     assert(await page.getByRole('dialog').getByText('Camille EXEMPLE',{exact:false}).count());
     await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);
     assert(await event.evaluate(el=>el===document.activeElement));
    });
    await check(engine+' reduced motion and visible focus',async()=>{
     await page.emulateMedia({reducedMotion:'reduce'});const tab=page.locator('.admin-tab').first();
     await tab.focus();await tab.hover();
     const values=await tab.evaluate(el=>({transform:getComputedStyle(el).transform,duration:getComputedStyle(el).transitionDuration,outline:getComputedStyle(el).outlineWidth}));
     assert.equal(values.transform,'none');assert.equal(values.duration,'0s');assert.notEqual(values.outline,'0px');
    });
    await check(engine+' no JS exceptions or external request',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(external,[]);});
    await context.close();
    const nojs=await browser.newContext({javaScriptEnabled:false}),plain=await nojs.newPage();
    await check(engine+' usable server forms without JS',async()=>{
     await plain.goto(base+'/admin/connexion');await plain.locator('[name="pin"]').fill('1379');await Promise.all([plain.waitForNavigation(),plain.locator('button[type="submit"]').click()]);
     await plain.goto(base+'/admin/ressources');await plain.locator('.resource-edit > summary').first().click();assert(await plain.locator('[name="price_euros"]').first().isVisible());
     await plain.goto(base+'/admin/calendrier?date=2026-10-03');assert(await plain.locator('.calendar-event').first().getAttribute('href'));
    });
    await nojs.close();
   }finally{await browser.close();}
  }
  console.log(checks+' corrective UI tests passed');
 }finally{fixture.kill('SIGTERM');await new Promise(r=>fixture.exitCode!==null?r():fixture.once('exit',r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
