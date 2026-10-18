'use strict';
// Real browser workflow using only disposable synthetic, nonmedical fixtures.
const {chromium}=require('playwright');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net');
const root=path.resolve(__dirname,'../..');
const python=process.env.EVIDENCE_TEST_PYTHON||path.join(root,'.venv/bin/python');
const directory=fs.mkdtempSync(path.join(os.tmpdir(),'evidence-browser-'));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const number=server.address().port;await new Promise(resolve=>server.close(resolve));return number;}
(async()=>{
 let browser,server;
 try{
  execFileSync(python,['-c',`from pathlib import Path; import pymupdf; p=Path(${JSON.stringify(directory)}); doc=pymupdf.open(); page=doc.new_page(); page.insert_textbox(pymupdf.Rect(40,40,550,700),'Synthetic treatment reduced risk in this fictional sample. Not medical evidence.'); doc.save(p/'source.pdf'); (p/'chapter.md').write_text('Synthetic treatment reduced risk[1].')`]);
  const number=await port();
  server=spawn(python,['-m','evidence_check.entrypoints.server','--config-dir',path.join(root,'backend/config'),'--data-dir',path.join(directory,'data'),'--port',String(number)],{
   cwd:root,stdio:'ignore',env:{...process.env,EVIDENCE_ACCESS_PASSWORD:'browser-fixture-access-password',EVIDENCE_DATA_KEY:'',EVIDENCE_MODEL_URL:'',EVIDENCE_MODEL_KEY:'',EVIDENCE_MODEL_NAME:''}});
  const origin=`http://127.0.0.1:${number}`;
  let ready=false;
  for(let i=0;i<100;i++){try{const response=await fetch(origin+'/api/config');if(response.ok){ready=true;break;}}catch{}await delay(100);}
  if(!ready)throw Error('Product server did not start');
  const executable=process.env.EVIDENCE_CHROMIUM||undefined;
  browser=await chromium.launch({headless:true,executablePath:executable,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(origin);await page.locator('#login-dialog').waitFor({state:'visible'});
  await page.fill('#password','browser-fixture-access-password');await page.locator('#login-form button').click();
  await page.locator('#login-dialog').waitFor({state:'hidden'});
  await page.setInputFiles('#manuscript',path.join(directory,'chapter.md'));
  await page.fill('#references','[1] Synthetic reference for browser testing');
  await page.selectOption('#language','en-en');
  await page.setInputFiles('#evidence',path.join(directory,'source.pdf'));
  await page.locator('#bindings select').selectOption('1');
  // Losing focus must not reset a previously selected PDF binding.
  await page.locator('#references').dispatchEvent('change');
  if(await page.locator('#bindings select').inputValue()!=='1')throw Error('Reference redraw reset PDF binding');
  await page.check('#authorized');await page.check('#single-section');await page.click('#submit');
  await page.locator('.evidence').first().waitFor({timeout:20000});
  await page.check('.evidence-choice');
  for(const [field,value] of Object.entries({support_relation:'supports',scope_relation:'match',causal_relation:'compatible',direction_relation:'match',numeric_relation:'match'}))await page.selectOption(`select[data-field="${field}"]`,value);
  await page.fill('.rationale','Synthetic test review only; not medical judgment.');await page.click('#save-review');
  await page.locator('.pill').filter({hasText:'支持候选'}).waitFor({timeout:20000});
  const downloadEvent=page.waitForEvent('download');await page.click('#export-md');const download=await downloadEvent;
  if(!download.suggestedFilename().endsWith('.md'))throw Error('Markdown export missing');
  if(process.env.EVIDENCE_SCREENSHOT_DIR){fs.mkdirSync(process.env.EVIDENCE_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.EVIDENCE_SCREENSHOT_DIR,'desktop.png'),fullPage:true});}
  await page.setViewportSize({width:390,height:844});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth))throw Error('Mobile horizontal overflow');
  if(process.env.EVIDENCE_SCREENSHOT_DIR)await page.screenshot({path:path.join(process.env.EVIDENCE_SCREENSHOT_DIR,'mobile.png'),fullPage:true});
  page.once('dialog',dialog=>dialog.accept());await page.click('#delete-task');await page.locator('#upload-view').waitFor({state:'visible'});
  if(errors.length)throw Error(errors.join('; '));
  console.log('PASS: login, PDF upload, binding regression, evidence, human review, export, mobile and deletion; zero JS errors.');
 }finally{
  if(browser)await browser.close();
  if(server){server.kill('SIGTERM');await Promise.race([new Promise(resolve=>server.once('exit',resolve)),delay(5000)]);if(server.exitCode===null)server.kill('SIGKILL');}
  fs.rmSync(directory,{recursive:true,force:true});
 }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
