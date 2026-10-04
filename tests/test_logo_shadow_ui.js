'use strict';
// Real application routes: default vs custom branding, no external requests.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');
const {chromium,webkit}=require('playwright');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:5078';
const selector='.site-header .brand-wordmark--openfablab';
const filter='drop-shadow(rgba(20, 35, 40, 0.14) 0px 1px 1px) drop-shadow(rgba(20, 35, 40, 0.12) 0px 3px 5px)';
const widths=[320,390,768,1024,1280,1440],views=[],existingOverflow=[];
const routes=[['home','/'],['admin','/admin'],['users','/admin/usagers'],
 ['calendar-week','/admin/calendrier?date=2026-10-03'],
 ['calendar-month','/admin/calendrier?date=2026-10-03&view=month']];
let checks=0;
async function check(name,fn){await fn();checks++;console.log('OK '+name);}
async function fixture(kind){
 const child=spawn(process.env.TEST_PYTHON||'python3',[path.join(__dirname,'logo_fixture.py'),'5078',kind],
  {cwd:root,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','ignore','pipe']});
 let error='';child.stderr.on('data',b=>error+=b);
 for(let i=0;i<100;i++){
  if(child.exitCode!==null)throw Error(error);
  try{if((await fetch(base+'/sante')).ok)return child;}catch(_){}
  await new Promise(r=>setTimeout(r,100));
 }
 child.kill('SIGTERM');throw Error('Fixture did not start: '+error);
}
async function stop(child){child.kill('SIGTERM');await new Promise(r=>child.exitCode!==null?r():child.once('exit',r));}
async function verify(page,engine,kind,name,width){
 const logo=page.locator('.site-header .brand-wordmark');
 assert.equal(await logo.count(),1);await logo.evaluate(el=>el.decode());
 const actual=await logo.evaluate(el=>getComputedStyle(el).filter);
 if(kind==='default'){
  assert.equal(await page.locator(selector).count(),1);
  assert.equal(actual,filter);
  assert((await logo.getAttribute('src')).endsWith('/static/brand/OpenFabLab-logo-horizontal.svg'));
  const before=await logo.boundingBox();
  await logo.evaluate(el=>el.style.filter='none');
  assert.deepEqual(await logo.boundingBox(),before,'Shadow changed layout');
  await logo.evaluate(el=>el.style.removeProperty('filter'));
  assert.equal(await logo.evaluate(el=>getComputedStyle(el).filter),actual);
  await logo.hover();assert.equal(await logo.evaluate(el=>getComputedStyle(el).filter),actual,'Hover changes shadow');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await logo.evaluate(el=>getComputedStyle(el).filter),actual,'Reduced motion removes static shadow');
  await page.emulateMedia({reducedMotion:'no-preference'});
  const geometry=await logo.evaluate(el=>{
   const r=el.getBoundingClientRect(),header=el.closest('header').getBoundingClientRect();
   const clipped=[];
   for(let parent=el.parentElement;parent;parent=parent.parentElement){
    const s=getComputedStyle(parent),b=parent.getBoundingClientRect();
    if(['hidden','clip','scroll','auto'].includes(s.overflowX)&&
       (r.left-12<b.left||r.right+12>b.right))clipped.push(parent.tagName+' horizontal');
    if(['hidden','clip','scroll','auto'].includes(s.overflowY)&&
       (r.top-12<b.top||r.bottom+12>b.bottom))clipped.push(parent.tagName+' vertical');
   }
   return {x:r.x,y:r.y,width:r.width,height:r.height,naturalWidth:el.naturalWidth,
    naturalHeight:el.naturalHeight,headerBottom:header.bottom,background:getComputedStyle(el.closest('header')).backgroundColor,
    dpr:devicePixelRatio,clipped};
  });
  assert.equal(geometry.dpr,2);assert.deepEqual(geometry.clipped,[]);
  assert(geometry.x>=12&&geometry.y>=8&&geometry.x+geometry.width+12<=width,
   'Shadow too close to viewport: '+JSON.stringify(geometry));
  assert(geometry.headerBottom>=geometry.y+geometry.height+10,'Shadow crosses header boundary');
  assert.equal(geometry.background,'rgba(255, 255, 255, 0.92)');
  views.push({engine,name,width,geometry});
 }else{
  assert.equal(await page.locator(selector).count(),0);assert.equal(actual,'none');
  assert((await logo.getAttribute('src')).endsWith('/media/structure/wordmark.png'));
 }
 assert.equal(await page.locator('.partner-logos img').count(),2);
 assert.deepEqual(await page.locator('.site-header img:not(.brand-wordmark)').evaluateAll(els=>els.map(el=>getComputedStyle(el).filter)),['none','none']);
 assert(await page.locator('main img').evaluateAll(els=>els.every(el=>getComputedStyle(el).filter==='none')),'Non-header image affected');
 const scrollWidth=await page.evaluate(()=>document.documentElement.scrollWidth);
 await logo.evaluate(el=>el.style.filter='none');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),scrollWidth,
  'Shadow introduced horizontal overflow');
 await logo.evaluate(el=>el.style.removeProperty('filter'));
 if(scrollWidth>width+1){
  assert.equal(name,'users','Unexpected pre-existing page overflow');
  existingOverflow.push({engine,kind,name,width,scrollWidth,unchanged_without_shadow:true});
 }
 if(process.env.UI_SCREENSHOT_DIR&&kind==='default'&&
     ((name==='home'&&[320,1280,1440].includes(width))||(name==='login'&&width===390))){
  const output=process.env.UI_SCREENSHOT_DIR;fs.mkdirSync(output,{recursive:true});
  await page.screenshot({path:path.join(output,engine.toLowerCase()+'-'+name+'-'+width+'.png'),animations:'disabled'});
 }
}
(async()=>{
 const engines=[['Chromium',chromium],['WebKit',webkit]];
 assert(fs.existsSync(webkit.executablePath()),'Install Playwright WebKit for this cross-engine suite');
 for(const kind of ['default','custom']){
  const child=await fixture(kind);
  try{for(const [engine,type] of engines){
   const browser=await type.launch({headless:true,...(engine==='Chromium'&&process.env.TEST_CHROME?{executablePath:process.env.TEST_CHROME}:{})});
   try{
    const errors=[],external=[];
    const authenticated=await browser.newContext({deviceScaleFactor:2,hasTouch:true,serviceWorkers:'block'});
    const anonymous=await browser.newContext({deviceScaleFactor:2,hasTouch:true,serviceWorkers:'block'});
    for(const context of [authenticated,anonymous]){
     context.on('page',page=>page.on('pageerror',e=>errors.push(e.message)));
     await context.route('**/*',r=>{if(r.request().url().startsWith(base+'/'))return r.continue();external.push(r.request().url());return r.abort();});
    }
    const page=await authenticated.newPage(),login=await anonymous.newPage();
    await page.goto(base+'/admin/connexion');await page.locator('[name="pin"]').fill('1379');
    await Promise.all([page.waitForNavigation(),page.locator('button[type="submit"]').click()]);
    for(const width of widths){
     const height=width===1280?800:width===1440?900:width===1024?768:1024;
     await page.setViewportSize({width,height});await login.setViewportSize({width,height});
     for(const [name,route] of routes)await check(engine+' '+kind+' '+name+' '+width,async()=>{
      assert.equal((await page.goto(base+route)).status(),200);await page.evaluate(()=>document.fonts.ready);
      await verify(page,engine,kind,name,width);
     });
     await check(engine+' '+kind+' login '+width,async()=>{
      assert.equal((await login.goto(base+'/admin/connexion')).status(),200);
      await login.evaluate(()=>document.fonts.ready);await verify(login,engine,kind,'login',width);
      assert.equal(await login.getByRole('radio').count(),2);
      await login.getByRole('radio',{name:'Modérateur'}).check();
      assert(await login.getByRole('radio',{name:'Modérateur'}).isChecked());
      await verify(login,engine,kind,'login-moderator',width);
     });
    }
    await check(engine+' '+kind+' no JS error or external request',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(external,[]);});
    await authenticated.close();await anonymous.close();
   }finally{await browser.close();}
  }}finally{await stop(child);}
 }
 if(process.env.UI_SCREENSHOT_DIR)fs.writeFileSync(path.join(process.env.UI_SCREENSHOT_DIR,'RESULT.json'),JSON.stringify({
  result:'PASS',checks,version:'2.7.1',selector,filter,engines:engines.map(v=>v[0]),widths,device_scale_factor:2,
  default_logo_shadow_only:true,custom_and_partner_logos_unchanged:true,no_clipping:true,no_js_errors:true,no_external_requests:true,
  no_new_horizontal_overflow:true,existing_directory_overflow:existingOverflow,views},null,2));
 console.log(checks+' logo UI tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
