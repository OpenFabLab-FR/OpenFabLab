// Real browser, local Flask fixture and mocked public HTTP. Never real WordPress.
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const {spawn}=require('node:child_process');
const {chromium}=require('playwright');const root=path.resolve(__dirname,'..');
const base='http://127.0.0.1:5049';let tests=0;
async function check(name,task){await task();tests++;console.log('OK '+name);}
(async()=>{
  const fixture=spawn(process.env.TEST_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'participants_fixture.py'),'5049'],
    {cwd:root,env:{...process.env,OPENFABLAB_SLOT_UI:'1',PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
  let stdout='',stderr='',browser;
  fixture.stdout.on('data',b=>stdout+=b);fixture.stderr.on('data',b=>stderr+=b);
  try{
    let ready=false;for(let i=0;i<100;i++){if(fixture.exitCode!==null)throw Error(stderr);try{ready=(await fetch(base+'/sante')).ok;}catch(_){}if(ready)break;await new Promise(r=>setTimeout(r,100));}
    assert(ready);const data=JSON.parse(stdout.split('\n').find(s=>s.startsWith('{')));
    browser=await chromium.launch({headless:true,...(process.env.TEST_CHROME ? {executablePath:process.env.TEST_CHROME} : {})});
    const page=await browser.newPage();await page.route('**/*',r=>r.request().url().startsWith(base+'/')?r.continue():r.abort());
    await page.goto(base+'/admin/connexion');await page.locator('[name="pin"]').fill('1379');await page.locator('button[type="submit"]').click();
    for(const[name,width,height]of[['MacBook',1440,900],['tablette',1280,800],['iPhone',390,844]]){
      await check('admin slots '+name+' no overflow and ordered cards',async()=>{
        await page.setViewportSize({width,height});await page.goto(base+'/admin/animations/'+data.service_id+'/inscriptions');
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
        assert.equal(await page.locator('.animation-slot-summary article').count(),4);
        assert((await page.locator('.animation-slot-summary').textContent()).includes('10:00–10:20'));
        assert((await page.locator('[data-label="Personne"]').first().textContent()).includes('Créneau : 10:00–10:20'));
        const select=page.locator('[name="slot_uuid"]');const box=await select.boundingBox();assert(box.x+box.width<=width+1);
        await page.goto(base+'/admin/animations');assert((await page.locator('[data-label="Participants"]').first().textContent()).includes('4 créneaux / 1 inscrit / 0 présent'));
        await page.goto(base+'/admin/animations/'+data.service_id+'/modifier');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
        assert.deepEqual(await page.locator('#slot-preview li').allTextContents(),['10:00–10:20','10:30–10:50','11:00–11:20','11:30–11:50']);
      });
    }
    await check('admin preview gap zero, two seats and invalid duration',async()=>{
      await page.locator('#slot-gap').fill('0');assert.equal(await page.locator('#slot-preview li').count(),6);
      assert.equal(await page.locator('#capacity').inputValue(),'12');
      await page.locator('#slot-duration').fill('0');assert.equal(await page.locator('#slot-preview li').count(),0);
      await page.locator('#booking-mode').selectOption('whole');assert.equal(await page.locator('#capacity').getAttribute('readonly'),null);
    });
    const publicPage=await browser.newPage();const calls=[];
    const slots=[0,30,60,90].map((m,i)=>({slot_uuid:'20000000-0000-4000-8000-'+String(i+1).padStart(12,'0'),
      starts_at:new Date(Date.UTC(2027,9,8,8,m)).toISOString(),ends_at:new Date(Date.UTC(2027,9,8,8,m+20)).toISOString(),
      capacity:1,available:i===1?0:1,registration_open:true}));
    await publicPage.route('**/*',async r=>{
      const request=r.request();if(!request.url().startsWith('https://example.invalid/'))return r.abort();
      if(request.url().endsWith('/reserve'))calls.push(request.postDataJSON());
      const body=request.url().includes('/animations?')?{animations:[{service_id:7,title:'Découverte casque VR',
        starts_at:'2027-10-08T08:00:00Z',ends_at:'2027-10-08T10:00:00Z',timezone:'Europe/Paris',audience:'all',
        minimum_age:6,accompaniment_under_age:15,waitlist_enabled:true,available:3,registration_open:true,booking_mode:'slots',slots}]}:{message:'Réservation fictive enregistrée'};
      return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
    });
    for(const[name,width,height]of[['ordinateur',1440,900],['tablette',1280,800],['iPhone',390,844]]){
      await check('public slots '+name+' availability and no overflow',async()=>{
        await publicPage.setViewportSize({width,height});
        await publicPage.setContent('<section class="openfablab-reservations" data-environment="test"><div class="openfablab-status"></div><div class="openfablab-animation-list"></div><div class="openfablab-form-host"></div></section>');
        await publicPage.addStyleTag({path:path.join(root,'tests/historical-wordpress/assets/reservations.css')});
        await publicPage.evaluate(()=>window.OpenFabLabReservations={api:'https://example.invalid/'});
        await publicPage.addScriptTag({path:path.join(root,'tests/historical-wordpress/assets/reservations.js')});
        await publicPage.locator('.openfablab-card button').click();
        const select=publicPage.locator('[name="slot_uuid"]');assert.equal(await select.getAttribute('required'),'');
        const options=await select.locator('option').allTextContents();assert(options[1].includes('10:00–10:20'));assert(options[2].includes('Complet · liste d’attente'));
        assert(await publicPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
        const box=await select.boundingBox();assert(box.x+box.width<=width+1);
        assert.equal(await publicPage.locator('[name="first_name"]').getAttribute('readonly'),null);
        assert.equal(await publicPage.locator('[name="phone"]').getAttribute('required'),'');
      });
    }
    await check('public slot required and stable UUID sent for selected waitlist',async()=>{
      for(const[name,value]of Object.entries({first_name:'Fictif',last_name:'LOCAL',birth_year:'1990',email:'fixture@example.invalid',phone:'0600000000'}))await publicPage.locator('[name="'+name+'"]').fill(value);
      await publicPage.locator('button[type="submit"]').click();assert.equal(calls.length,0);
      await publicPage.locator('[name="slot_uuid"]').selectOption(slots[1].slot_uuid);
      await publicPage.locator('button[type="submit"]').click();await publicPage.locator('.openfablab-feedback').getByText('Réservation fictive enregistrée').waitFor();
      assert.equal(calls[0].slot_uuid,slots[1].slot_uuid);assert.equal(calls[0].environment,'test');
    });
    console.log(tests+' slot UI tests passed');
  }finally{if(browser)await browser.close();fixture.kill('SIGTERM');await new Promise(r=>fixture.exitCode!==null||fixture.signalCode!==null?r():fixture.once('exit',r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
