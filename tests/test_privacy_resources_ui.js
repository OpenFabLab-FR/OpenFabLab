// Real local Flask templates, fictional database/resources, no external requests.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const base='http://127.0.0.1:5058';
let checks=0;
async function check(name,fn){await fn();checks++;console.log('OK '+name);}
(async()=>{
 const fixture=spawn(process.env.TEST_PYTHON||path.join(root,'.venv/bin/python'),[path.join(__dirname,'privacy_resources_fixture.py'),'5058'],
   {cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
 let error='',browser;fixture.stderr.on('data',b=>{error+=b;});fixture.stdout.resume();
 try{
  let ready=false;
  for(let n=0;n<100;n++){
   if(fixture.exitCode!==null)throw Error(error);
   try{ready=(await fetch(base+'/sante')).ok;}catch(_){ }
   if(ready)break;await new Promise(r=>setTimeout(r,100));
  }
  assert(ready);
  const chrome=process.env.TEST_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  browser=await chromium.launch({headless:true,...(fs.existsSync(chrome)?{executablePath:chrome}:{})});
  const page=await browser.newPage();
  await page.route('**/*',r=>r.request().url().startsWith(base+'/')?r.continue():r.abort());
  await page.goto(base+'/admin/connexion');await page.locator('[name="pin"]').fill('1379');
  await Promise.all([page.waitForNavigation(),page.locator('button[type="submit"]').click()]);
  for(const [name,width,height] of [['desktop',1440,1000],['tablette',820,1180],['mobile',390,844]]){
   await check('resources '+name+' visible independent cards and previews',async()=>{
    await page.setViewportSize({width,height});await page.goto(base+'/admin/reglages/structure');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    const resources=page.locator('#complementary-resources');
    assert.equal(await resources.locator('details').count(),0);
    assert.equal(await resources.locator('[data-resource]').count(),3);
    assert.equal(await resources.locator('.logo-preview img').count(),2);
    for(const image of await resources.locator('.logo-preview img').all()){
     await image.evaluate(img=>img.decode());
     assert(await image.evaluate(img=>img.complete&&img.naturalWidth>0));
    }
    for(const key of ['use_main_logo','use_signature','use_badge_template'])assert(await page.locator('[name="'+key+'"]').isChecked());
    for(const card of await resources.locator('[data-resource]').all()){
     const box=await card.boundingBox();assert(box.x>=0&&box.x+box.width<=width+1);
    }
    if(process.env.UI_SCREENSHOT_DIR)await resources.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'resources-'+name+'.png')});
   });
   await check('privacy fields '+name+' readable and free DPO',async()=>{
    const section=page.locator('#privacy-settings');
    assert.equal(await page.locator('textarea[name="dpo"]').inputValue(),'Service DPO — Atelier fictif');
    assert.equal(await section.locator('input[name="dpo_phone"]').inputValue(),'');
    assert(await section.innerText().then(s=>s.includes('Représentant')&&!s.includes('Représentant du responsable')));
    for(const key of ['dpo','dpo_email','dpo_phone']){
     const box=await page.locator('[name="'+key+'"]').boundingBox();assert(box.x>=0&&box.x+box.width<=width+1);
    }
    if(process.env.UI_SCREENSHOT_DIR)await section.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'privacy-settings-'+name+'.png')});
   });
   await check('public privacy '+name+' two separate contacts no general fallback',async()=>{
    await page.goto(base+'/gestion-des-donnees');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.equal(await page.locator('a[href="mailto:dpo@example.invalid"]').count(),1);
    assert.equal(await page.locator('a[href="mailto:privacy@example.invalid"]').count(),0);
    assert.equal(await page.locator('a[href="https://openfablab.fr"]').filter({hasText:'https://openfablab.fr'}).count(),1);
    assert((await page.locator('.data-information-grid').innerText()).includes("Aucune télémétrie n'est transmise automatiquement"));
    if(process.env.UI_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.UI_SCREENSHOT_DIR,'data-management-'+name+'.png'),fullPage:true});
   });
  }
  await check('resource toggles persist through saving without forgetting configuration',async()=>{
   await page.goto(base+'/admin/reglages/structure');
   for(const key of ['use_main_logo','use_signature','use_badge_template'])await page.locator('[name="'+key+'"]').uncheck();
   await Promise.all([page.waitForNavigation(),page.locator('.structure-save-actions button').click()]);
   for(const key of ['use_main_logo','use_signature','use_badge_template'])assert(!(await page.locator('[name="'+key+'"]').isChecked()));
   assert((await page.locator('[data-resource="badge"]').innerText()).includes('modèle générique OpenFabLab utilisé'));
   assert.equal(await page.locator('.resource-grid .logo-preview img').count(),2);
   for(const key of ['use_main_logo','use_signature','use_badge_template'])await page.locator('[name="'+key+'"]').check();
   await Promise.all([page.waitForNavigation(),page.locator('.structure-save-actions button').click()]);
   assert((await page.locator('[data-resource="badge"]').innerText()).includes('modèle privé configuré'));
  });
  await check('explicit removal requires confirmation before any POST',async()=>{
   let posts=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/supprimer/'))posts++;});
   page.once('dialog',d=>d.dismiss());
   await page.locator('[data-resource="signature"] button').click();assert.equal(posts,0);
  });
  await check('fictitious badge preview available and independent from public site',async()=>{
   const response=await page.request.get(base+'/admin/reglages/structure/badge-apercu.png');
   assert.equal(response.status(),200);assert(response.headers()['content-type'].includes('image/png'));
  });
  console.log(checks+' privacy/resource JavaScript tests passed');
 }finally{if(browser)await browser.close();fixture.kill('SIGTERM');await new Promise(r=>fixture.exitCode!==null?r():fixture.once('exit',r));}
})().catch(e=>{console.error(e);process.exit(1)});
