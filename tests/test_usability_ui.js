// Real local Flask forms, two engines; no requests outside the isolated fixture.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');const {chromium,webkit}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:5068';let checks=0;
function check(value,label){assert(value,label);checks++;}
(async()=>{
 for(const [engine,type] of [['Chromium',chromium],['WebKit',webkit]]){
  const fixture=spawn(process.env.TEST_PYTHON,[path.join(__dirname,'evolution_fixture.py'),'5068'],{cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
  let diagnostic='',browser;fixture.stdout.resume();fixture.stderr.on('data',b=>diagnostic+=b);
  try{
   let ready=false;for(let n=0;n<100;n++){if(fixture.exitCode!==null)throw Error(diagnostic);try{ready=(await fetch(base+'/sante')).ok;}catch{}if(ready)break;await new Promise(r=>setTimeout(r,100));}check(ready,'fixture ready');
   browser=await type.launch(engine==='Chromium'?{executablePath:process.env.TEST_CHROME}:{headless:true});
   const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',r=>r.request().url().startsWith(base+'/')?r.continue():r.abort());
   async function login(){await page.goto(base+'/admin/connexion');await page.locator('[name=pin]').fill('1379');await Promise.all([page.waitForNavigation(),page.locator('button[type=submit]').click()]);}
   for(const mode of ['automatic_discreet','automatic_visible','customizable']){
    await login();await page.goto(base+'/admin/reglages/usagers');
    const select=page.locator('[name=public_id_assignment_mode]');await select.selectOption(mode);
    const form=select.locator('xpath=ancestor::form');await Promise.all([page.waitForNavigation(),form.getByRole('button',{name:'Enregistrer',exact:true}).click()]);
    for(const width of [320,360,390,430,768,844,1024,1280,1440,1920]){
     await page.setViewportSize({width,height:width===844?390:900});await page.goto(base+'/inscription');await page.evaluate(()=>document.fonts.ready);
     check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),engine+' '+mode+' '+width+' no overflow');
     const id=page.locator('[name=public_id]');check(await id.count()===(mode==='automatic_discreet'?0:1),'ID mode visible');
     if(mode!=='automatic_discreet')check(await id.evaluate((el,mode)=>el.readOnly===(mode==='automatic_visible'),mode),'readonly mode');
     check(await page.locator('[name=affiliation_name]').count()===0,'no affiliation registry in public form');
     if(process.env.UI_SCREENSHOT_DIR&&[390,1280].includes(width))await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,engine+'-'+mode+'-'+width+'.png'),fullPage:true});
    }
    await page.locator('[name=first_name]').fill('Élodie');await page.locator('[name=last_name]').fill('EXEMPLE');await page.locator('[name=birth_year]').fill('1990');
    await page.locator('[name=email]').fill('elodie@example.invalid');await page.locator('[name=phone]').fill('0600000000');
    if(mode==='customizable')await page.locator('[name=public_id]').fill('0007');
    await Promise.all([page.waitForNavigation(),page.locator('.form-actions button[type=submit]').click()]);
    check(page.url().includes('/inscription/terminee'),engine+' '+mode+' creates account with real server validation');
    if(mode==='customizable')check((await page.locator('body').innerText()).includes('0007'),'leading zero receipt');
   }
   await login();await page.goto(base+'/admin/usagers/nouveau');
   check(await page.locator('[name=affiliation_name]').count()===1,'team affiliation form');
   for(const width of [320,390,768,1280,1920]){
    await page.setViewportSize({width,height:900});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'affiliation no overflow');
   }
   check(errors.length===0,engine+' no JS errors');
  }finally{if(browser)await browser.close();fixture.kill('SIGTERM');await new Promise(r=>fixture.exitCode!==null?r():fixture.once('exit',r));}
 }
 console.log(checks+' usability UI tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
