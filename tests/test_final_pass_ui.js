// Final 2.7.1 pass, fictional local fixture; no production or external requests.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');const {chromium,webkit}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:5075',screens=process.env.UI_SCREENSHOT_DIR;
let checks=0;
async function check(name,fn){await fn();checks++;console.log('OK '+name);}
(async()=>{
 const fixture=spawn(process.env.TEST_PYTHON||'python3',[path.join(__dirname,'corrective_fixture.py'),'5075'],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
 let diagnostics='';fixture.stderr.on('data',data=>diagnostics+=data);fixture.stdout.resume();
 try{
  let ready=false;for(let i=0;i<100;i++){if(fixture.exitCode!==null)throw Error(diagnostics);try{ready=(await fetch(base+'/sante')).ok;}catch(_){}if(ready)break;await new Promise(r=>setTimeout(r,100));}assert(ready,diagnostics);
  for(const [name,type] of [['Chromium',chromium],['WebKit',webkit]]){
   assert(fs.existsSync(type.executablePath())||name==='Chromium','WebKit runtime required for this pass');
   const browser=await type.launch({headless:true,...(name==='Chromium'?{executablePath:process.env.TEST_CHROME}: {})});
   try{
    const context=await browser.newContext({hasTouch:true}),page=await context.newPage(),errors=[],external=[];
    page.on('pageerror',e=>errors.push(e.message));
    await context.route('**/*',route=>{if(route.request().url().startsWith(base+'/'))return route.continue();external.push(route.request().url());return route.abort();});
    async function login(role='Administrateur',pin='1379'){
     await page.goto(base+'/admin/connexion');await page.getByRole('radio',{name:role,exact:true}).check();await page.locator('[name="pin"]').fill(pin);
     await Promise.all([page.waitForNavigation(),page.locator('button[type="submit"]').click()]);
    }
    const publicRoutes=[['home','/'],['animations','/animations']];
    await page.goto(base+'/animations');const detail=await page.getByRole('link',{name:'Voir l’animation'}).first().getAttribute('href');
    publicRoutes.push(['animation',detail],['request',detail+'/reserver']);
    for(const width of [1440,1280,1024,820,768,430,390,375,360,320]){
     await page.setViewportSize({width,height:1000});
     for(const [view,url] of publicRoutes)await check(name+' public '+view+' '+width,async()=>{
      await page.goto(base+url);
      assert(await page.locator('h1').count()<=1);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'public horizontal overflow');
      assert.equal(await page.locator('.brand-wordmark--openfablab').count(),1);
      assert(!await page.getByText('Instance issue d’une copie de test',{exact:false}).count());
      if(view==='animations')assert.equal(await page.getByRole('link',{name:'Voir l’animation'}).count(),1);
      if(screens&&name==='Chromium'&&[1280,820,390].includes(width)&&['animations','request'].includes(view))await page.screenshot({path:path.join(screens,'final-'+view+'-'+width+'.png')});
     });
     await login();
     await check(name+' session grid '+width,async()=>{
      await page.goto(base+'/admin/frequentation/journee?date=2026-10-03');await page.locator('[data-session-toggle]').first().click();
      const geometry=await page.locator('.session-detail-row:not([hidden]) .session-edit-form').evaluate(form=>({
       columns:getComputedStyle(form).gridTemplateColumns.split(' ').length,
       labels:[...form.querySelectorAll('label')].every(el=>el.querySelector('span').getBoundingClientRect().bottom<=el.querySelector('input').getBoundingClientRect().top+1)
      }));assert(geometry.labels,'labels must remain above inputs');assert.equal(geometry.columns,width<=600?1:width<=820?2:4);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      if(screens&&name==='Chromium'&&[1280,390].includes(width))await page.screenshot({path:path.join(screens,'final-day-'+width+'.png')});
     });
     await check(name+' authorization heading '+width,async()=>{
      await page.goto(base+'/admin/habilitations');assert(await page.getByRole('heading',{name:'Habilitations',exact:true}).count());
      assert(!await page.getByText('Une définition utilisée',{exact:false}).count());
      const aligned=await page.locator('.authorization-heading').first().evaluate(el=>{const title=el.querySelector('h3').getBoundingClientRect(),controls=el.lastElementChild.getBoundingClientRect();return controls.bottom>=title.top&&title.bottom>=controls.top;});assert(aligned);
      await page.locator('.authorization-definition').locator('..').locator('summary').click();
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      if(screens&&name==='Chromium'&&[1280,390].includes(width))await page.screenshot({path:path.join(screens,'final-authorizations-'+width+'.png')});
     });
     await check(name+' calendar popovers '+width,async()=>{
      await page.goto(base+'/admin/calendrier?date=2026-10-03');
      assert.equal(await page.locator('.calendar-all-day').count(),8,'fixture contains all-day training');
      const animation=page.locator('[data-calendar-detail]').filter({hasText:'Animation Exemple'}).first();
      await animation.focus();await animation.press('Enter');let dialog=page.getByRole('dialog');
      assert(await dialog.getByText('Camille EXEMPLE',{exact:true}).count());assert(await dialog.getByText('Liste d’attente',{exact:true}).count());
      assert(await dialog.locator('.category-badge').count()>0);await page.keyboard.press('Escape');assert(await animation.evaluate(el=>el===document.activeElement));
      const openlab=page.locator('[data-calendar-detail]').filter({hasText:'OpenLab'}).last();await openlab.click();dialog=page.getByRole('dialog');
      assert(await dialog.getByRole('link',{name:'Ouvrir la journée'}).count());assert(await dialog.getByText('Pic simultané',{exact:false}).count());
      assert(await dialog.getByText('Camille EXEMPLE',{exact:true}).count());
      assert(await dialog.evaluate(el=>el.getBoundingClientRect().right<=innerWidth&&el.getBoundingClientRect().left>=0));
      if(screens&&name==='Chromium'&&[1280,390].includes(width))await page.screenshot({path:path.join(screens,'final-openlab-'+width+'.png')});
      await page.keyboard.press('Escape');
      await page.goto(base+'/admin/calendrier?date=2026-10-12');assert.equal(await page.locator('.calendar-all-day').count(),0);assert(!await page.getByText('Sans horaire',{exact:true}).count());
     });
    }
    await page.setViewportSize({width:1280,height:1000});
    await check(name+' annual history has no MacBook scroll',async()=>{
     await page.goto(base+'/admin/frequentation/statistiques?year=total');assert(await page.locator('.annual-history-table').evaluate(el=>el.parentElement.scrollWidth<=el.parentElement.clientWidth+1));
    });
    await check(name+' category whole disk and symmetric edge',async()=>{
     await page.goto(base+'/admin/usagers');const badge=page.locator('.category-badge').first();
     assert(await badge.evaluate(el=>getComputedStyle(el).borderLeftWidth===getComputedStyle(el).borderRightWidth));
     assert.equal(await badge.evaluate(el=>getComputedStyle(el,'::before').borderRadius),'50%');
    });
    await check(name+' first subtab hover has breathing room',async()=>{
     await page.goto(base+'/admin');const tab=page.locator('.admin-subtabs a').first();await tab.hover();
     assert(await tab.evaluate(el=>el.getBoundingClientRect().left-el.parentElement.getBoundingClientRect().left>=10));
     assert.notEqual(await tab.evaluate(el=>getComputedStyle(el).boxShadow),'none');
    });
    await check(name+' public identity challenge replaces companion form and locks session',async()=>{
     await page.goto(base+detail+'/reserver');
     assert(await page.getByRole('heading',{name:'Identifier mon compte'}).count());
     assert.equal(await page.locator('[name="public_id"]').count(),1);
     assert.equal(await page.locator('[name="contact"]').count(),1);
     assert.equal(await page.locator('[name="companion_first_name"]').count(),0);
     await page.goto(base+'/admin/usagers');assert(page.url().includes('/admin/connexion'));
    });
    await check(name+' no JS exceptions or external request',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(external,[]);});
    await context.close();
   }finally{await browser.close();}
  }
  console.log(checks+' final pass UI tests passed');
 }finally{fixture.kill('SIGTERM');await new Promise(resolve=>fixture.exitCode!==null?resolve():fixture.once('exit',resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
