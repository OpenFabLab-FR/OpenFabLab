// Private settings rendered by the actual class; fictional data, all network blocked.
const assert=require('node:assert/strict');const path=require('node:path');
const {spawnSync}=require('node:child_process');const {chromium}=require('playwright');
let tests=0;async function check(name,fn){await fn();tests++;console.log('OK '+name);}
function html(mode){
  const r=spawnSync(process.env.PHP_TEST_COMMAND||'php',[path.join(__dirname,'test_wordpress_emails.php'),'html',mode],{encoding:'utf8',env:{...process.env,PHP:'8.1'}});
  assert.equal(r.status,0,r.stderr);assert(!/Fatal error|Parse error|Warning:/.test(r.stdout+r.stderr));return r.stdout;
}
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.TEST_CHROME ? {executablePath:process.env.TEST_CHROME} : {})});
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  try{
    await check('six models, subject/body, shared signature and placeholders',async()=>{
      await page.setContent(html('settings'));assert.equal(await page.locator('details').count(),6);
      assert.equal(await page.locator('[name="subject"]').count(),6);assert.equal(await page.locator('[name="body"]').count(),6);
      assert.equal(await page.locator('[name="signature"]').count(),1);
      assert((await page.locator('section').textContent()).includes('{{public_id_or_not_provided}}'));
      assert.equal(await page.locator('[name="_wpnonce"]').count(),7);
    });
    await check('templates remain editable and no PHP/HTML editor',async()=>{
      await page.locator('details').first().locator('summary').click();
      await page.locator('[name="subject"]').first().fill('Mon sujet {{animation_title}}');
      await page.locator('[name="body"]').first().fill('Mon texte\n{{cancel_url}}\n{{signature}}');
      assert.equal(await page.locator('[name="subject"]').first().inputValue(),'Mon sujet {{animation_title}}');
      assert.equal(await page.locator('iframe').count(),0);
    });
    await check('reset requires explicit checkbox, no preselection',async()=>{
      assert.equal(await page.locator('[name="reset_confirm"]:checked').count(),0);
      assert.equal(await page.locator('[name="openfablab_email_action"][value="reset"]').count(),6);
    });
    await check('fictional slot preview escaped and draft retained',async()=>{
      await page.setContent(html('preview'));
      assert((await page.locator('pre').textContent()).includes('Créneau : 10:30–10:50'));
      assert((await page.locator('pre').textContent()).includes('example.invalid/annulation-exemple'));
      assert.equal(await page.locator('script').count(),0);
      assert((await page.locator('[name="body"]').first().inputValue()).includes('sans exécution'));
      assert.equal(await page.locator('details[open]').count(),1);
    });
    for(const[name,width,height]of[['MacBook',1440,900],['tablette',1280,800],['iPhone',390,844]]){
      await check('email settings responsive '+name,async()=>{
        await page.setViewportSize({width,height});await page.setContent(html('settings'));
        await page.addStyleTag({content:'body{margin:16px;font-family:system-ui} .large-text{width:100%;box-sizing:border-box} .regular-text{max-width:100%;box-sizing:border-box} input,textarea,select{max-width:100%} button{white-space:normal;margin:4px 0}'});
        await page.locator('details').first().locator('summary').click();
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
        const box=await page.locator('[name="body"]').first().boundingBox();assert(box.x+box.width<=width+1);
      });
    }
    await check('non-admin cannot see templates or signature',async()=>{
      await page.setContent(html('denied'));assert.equal(await page.locator('section').count(),0);
    });
    console.log(tests+' email JavaScript UI tests passed');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
