/* Public UX and real jsQR decoding with simulated cameras: no images uploaded. */
'use strict';
const assert=require('assert'),fs=require('fs'),path=require('path'),http=require('http'),{execFileSync}=require('child_process');
const {chromium,webkit}=require('playwright');
const assets=path.resolve(__dirname,'../wordpress/openfablab-reservations/assets');
const widths=[320,360,390,430,768,1024,1280,1440,1920];let checks=0;
function ok(value,label){assert(value,label);checks++;}
const qr={};for(const text of ['2001','9999','invalid'])qr[text]=execFileSync(process.env.TEST_PYTHON||'python3',['-c',"import segno,io,base64; b=io.BytesIO();segno.make('"+text+"',micro=False).save(b,kind='png',scale=10,border=4);print(base64.b64encode(b.getvalue()).decode())"],{encoding:'utf8'}).trim();
const server=http.createServer((req,res)=>{
  res.setHeader('Content-Type',req.url.endsWith('.js')?'application/javascript; charset=utf-8':req.url.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8');
  const name=path.basename(req.url);
    if(['family.js','qr-scanner.js','jsQR-1.4.0.js','reservations.css'].includes(name)){res.end(fs.readFileSync(path.join(assets,name)));}
  else res.end('<!doctype html><html lang="fr"><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/reservations.css"></head><body style="margin:12px;font:16px system-ui"><section class="openfablab-reservations" data-environment="production"><p class="openfablab-status" role="status"></p><div class="openfablab-animation-list"></div><div class="openfablab-form-host"></div></section></body></html>');
});
async function setup(page,base,required=false,phone=false){
  await page.goto(base);await page.evaluate(({required,phone,qr})=>{
    window.OpenFabLabReservations={api:'/api/'};window.fixture={required,phone,posts:[],tracksStopped:0,constraints:[],mode:'ok',qr};
    window.fetch=async(url,options={})=>{
      const route=url.split('/api/')[1],body=options.body?JSON.parse(options.body):null;if(body)fixture.posts.push({route,body});
      let value={csrf:'fictional-session'};
      if(route.startsWith('animations'))value={animations:[{service_id:1,title:'Animation fictive au titre particulièrement long pour vérifier le responsive',date:'20/10/2026',hours:'10:00–12:00',available:4,waitlist_enabled:true,account_required:required,phone_required:phone},{service_id:2,title:'Autre animation',date:'21/10/2026',hours:'09:00–11:00',available:1,waitlist_enabled:false,account_required:required,phone_required:phone}]};
      if(['verify','guest'].includes(route))value={state:'pending'};
      if(route==='status'){
        const previous=fixture.posts.findLast(x=>x.route==='verify'||x.route==='guest');
        value={state:'done',result:{ok:previous?.body.public_id!=='9999',message:'Ce compte n’a pas pu être vérifié.',value:previous?.route==='verify'?{token:'fictional-grant',participants:[{key:'fictional-person',name:'Camille FICTIF',label:'Autonome'}]}:{status:'confirmed',count:1}}};
      }
      return {ok:true,status:200,json:async()=>value};
    };
    Object.defineProperty(HTMLMediaElement.prototype,'srcObject',{get(){return this._stream},set(v){this._stream=v},configurable:true});
    HTMLMediaElement.prototype.play=async function(){};HTMLMediaElement.prototype.pause=function(){};
    Object.defineProperties(HTMLVideoElement.prototype,{readyState:{get:()=>4,configurable:true},videoWidth:{get:()=>290,configurable:true},videoHeight:{get:()=>290,configurable:true}});
    const draw=CanvasRenderingContext2D.prototype.drawImage;
    CanvasRenderingContext2D.prototype.drawImage=function(source,...rest){if(source instanceof HTMLVideoElement){if(window.qrImage)return draw.call(this,qrImage,...rest);this.fillStyle='white';this.fillRect(0,0,720,720);return;}return draw.call(this,source,...rest);};
    Object.defineProperty(navigator,'mediaDevices',{value:{enumerateDevices:async()=>[{kind:'videoinput',deviceId:'front'},{kind:'videoinput',deviceId:'back'}],getUserMedia:async constraints=>{
      fixture.constraints.push(constraints);
      if(fixture.mode==='late')await new Promise(resolve=>window.finishPermission=resolve);
      if(['NotAllowedError','NotFoundError','NotReadableError'].includes(fixture.mode))throw Object.assign(new Error('fixture'),{name:fixture.mode});
      const track={stop(){fixture.tracksStopped++},getSettings:()=>({deviceId:constraints.video.deviceId?.exact||'front'})};return {getTracks:()=>[track],getVideoTracks:()=>[track]};
    }},configurable:true});
  },{required,phone,qr});
  for(const file of ['jsQR-1.4.0.js','qr-scanner.js','family.js'])await page.addScriptTag({url:base+'/'+file});
  try {await page.getByRole('button',{name:'Réserver',exact:true}).first().waitFor();}
  catch(error){console.error(await page.textContent('body'));throw error;}
}
async function image(page,text){await page.evaluate(async text=>{const img=new Image();img.src='data:image/png;base64,'+fixture.qr[text];await img.decode();window.qrImage=img;},text);}
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 for(const [name,type] of [['Chromium',chromium],['WebKit',webkit]]){
  const browser=await type.launch(name==='Chromium'?{executablePath:process.env.TEST_CHROME,headless:true}:{headless:true});
  for(const width of widths){
   const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await setup(page,base,false,width===430);
   ok(!(await page.textContent('body')).includes('Disponibilité indicative'),'removed availability warning');
   ok((await page.textContent('body')).includes('liste d’attente autorisée'),'waitlist natural wording');
   ok(!(await page.locator('.openfablab-card').nth(1).textContent()).includes('liste d’attente'),'no false waitlist label');
   await page.getByRole('button',{name:'Réserver',exact:true}).first().focus();
   ok(await page.getByRole('button',{name:'Réserver',exact:true}).first().evaluate(el=>getComputedStyle(el).outlineStyle!=='none'),'visible keyboard focus');
   await page.keyboard.press('Enter');
   ok(await page.locator('.is-selected').count()===1,'one selected card');
   ok(await page.getByRole('button',{name:'Réserver',exact:true}).first().getAttribute('aria-pressed')==='true','accessible selection');
   ok((await page.locator('.openfablab-selected-summary').textContent()).includes('20/10/2026 · 10:00–12:00'),'dynamic event recall');
   await page.getByRole('button',{name:'Réserver',exact:true}).nth(1).click();
   ok(await page.locator('.is-selected').getAttribute('data-service-id')==='2','selection moves');
   ok((await page.locator('.openfablab-selected-summary').textContent()).includes('Autre animation'),'recall moves');
   if(process.env.OFL_SCREENSHOTS&&[390,1280].includes(width)){fs.mkdirSync(process.env.OFL_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.OFL_SCREENSHOTS,name+'-'+width+'-choices.png'),fullPage:true});}
   await page.getByRole('button',{name:'Réserver sans compte',exact:true}).click();
   if(process.env.OFL_SCREENSHOTS&&[390,1280].includes(width))await page.screenshot({path:path.join(process.env.OFL_SCREENSHOTS,name+'-'+width+'-guest-form.png'),fullPage:true});
   ok(await page.locator('[name=phone]').evaluate(el=>el.required)===(width===430),'phone independent policy');
   for(const [key,value] of Object.entries({first_name:'Camille',last_name:'FICTIF',birth_date:'1990-01-02',email:'camille@example.invalid',phone:'0600000000'}))await page.locator('[name='+key+']').fill(value);
   await page.getByRole('button',{name:'Voir le récapitulatif'}).click();
   ok((await page.locator('.openfablab-selected-summary').textContent()).includes('Autre animation'),'recap retains recall');
   await page.locator('[type=checkbox]').check();await page.getByRole('button',{name:'Valider la réservation'}).click();
   await page.getByRole('heading',{name:'Réservation confirmée',exact:true}).waitFor();
   ok(await page.evaluate(()=>fixture.posts.filter(x=>x.route==='guest').length)===1,'single guest durable deposit');
   ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),name+' '+width+' no overflow');
   await page.getByRole('button',{name:'Réserver',exact:true}).first().click();await page.getByRole('button',{name:'J’ai un compte OpenFabLab',exact:true}).click();
   ok(await page.getByRole('button',{name:'Scanner mon QR Code'}).count()===1,'QR as visible as manual');
   if(process.env.OFL_SCREENSHOTS&&[390,1280].includes(width))await page.screenshot({path:path.join(process.env.OFL_SCREENSHOTS,name+'-'+width+'-identification.png'),fullPage:true});
   await page.locator('[name=public_id]').fill('2001');await page.locator('[name=contact]').fill('person0@example.invalid');await page.getByRole('button',{name:'Continuer',exact:true}).click();
   await page.locator('[name=participants]').waitFor();ok(await page.locator('.openfablab-selected-summary').count()===1,'family step retains recall');
   ok(errors.length===0,'no JavaScript error');await context.close();
  }
  const context=await browser.newContext(),page=await context.newPage();await setup(page,base,true);
  await page.getByRole('button',{name:'Réserver',exact:true}).first().click();
  ok(await page.getByRole('button',{name:'Réserver sans compte',exact:true}).count()===0,'mandatory account no guest path');
  const scan=page.getByRole('button',{name:'Scanner mon QR Code'}),manual=page.getByRole('button',{name:'Saisir mon identifiant'});
  await scan.click();await page.getByRole('button',{name:'Changer de caméra'}).waitFor();
  ok(await page.evaluate(()=>fixture.constraints[0].video.facingMode.exact)==='user','front camera preferred');
  await page.getByRole('button',{name:'Changer de caméra'}).click();await page.waitForTimeout(100);
  ok(await page.evaluate(()=>fixture.constraints.at(-1).video.deviceId.exact)==='back','switch camera');
  await manual.click();ok(await page.evaluate(()=>fixture.tracksStopped)===2,'manual stops cameras');
  for(const mode of ['NotAllowedError','NotFoundError','NotReadableError']){
   await page.evaluate(mode=>fixture.mode=mode,mode);await scan.click();await page.getByText(/Vous pouvez saisir votre identifiant/).last().waitFor();
   ok(await manual.isVisible(),'manual fallback '+mode);
  }
  await page.evaluate(()=>fixture.mode='ok');await image(page,'invalid');await scan.click();await page.getByText(/Ce QR Code n’est pas un badge/).waitFor();
  ok(await page.locator('[name=public_id]').inputValue()==='','invalid QR not accepted');await manual.click();
  for(const content of ['2001','2001','9999']){
   await image(page,content);const stops=await page.evaluate(()=>fixture.tracksStopped);await scan.click();await page.waitForFunction(stops=>fixture.tracksStopped===stops+1,stops);
   await page.getByText('QR Code reconnu.',{exact:false}).waitFor();
   ok(await page.locator('[name=public_id]').inputValue()===content,'real QR decode '+content);
   ok(await page.evaluate(()=>fixture.tracksStopped)===stops+1,'recognized QR stops stream');
   ok(await page.evaluate(()=>fixture.posts.filter(x=>x.route==='verify').length)===0,'QR never authenticates automatically');
   await page.waitForTimeout(200);ok(await page.evaluate(()=>fixture.tracksStopped)===stops+1,'held QR no second trigger');
  }
  await page.locator('[name=contact]').fill('person0@example.invalid');await page.getByRole('button',{name:'Continuer',exact:true}).click();await page.getByText('Ce compte n’a pas pu être vérifié.').waitFor();ok(true,'unknown QR still passes identity verification');
  await page.evaluate(()=>{fixture.mode='late';window.qrImage=null});await scan.click();await manual.click();await page.evaluate(()=>finishPermission());await page.waitForTimeout(100);ok(await page.locator('.openfablab-scanner').isHidden(),'late permission closed stream');
  await page.evaluate(()=>{fixture.mode='ok';Object.defineProperty(navigator,'mediaDevices',{value:undefined})});await scan.click();ok(await page.getByText('Caméra indisponible.',{exact:false}).isVisible(),'no media API fallback');
  await context.close();await browser.close();
 }
 console.log(checks+' public guest/QR checks passed');server.close();
})().catch(e=>{console.error(e);server.close();process.exit(1)});
