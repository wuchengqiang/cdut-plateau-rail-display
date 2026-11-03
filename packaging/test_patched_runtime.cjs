// Run only the sandbox copy previously produced by test_recovery_patch_actual.py.
// No installed/field app is modified or contacted.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require('C:/Users/27805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'..');
const fixture=path.join(root,'tmp/recovery-patch-field-verification-20261102/installed/app/runtime');
const base='http://127.0.0.1:8019',remote='http://127.0.0.1:8029';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const parse=f=>JSON.parse(fs.readFileSync(f,'utf8').replace(/^\uFEFF/,''));
const write=(f,v)=>fs.writeFileSync(f,JSON.stringify(v,null,2));
const report={at:new Date().toISOString(),physicalControllerContacted:false,checks:[]};
(async()=>{
  assert(fs.realpathSync(fixture).startsWith(fs.realpathSync(path.join(root,'tmp'))+path.sep));
  for(const url of [base,remote])assert(!await fetch(url+'/api/status').then(()=>true,()=>false),'Test port already occupied');
  const config=path.join(fixture,'config');
  const machine=parse(path.join(config,'machine.json'));machine.provider='mock';write(path.join(config,'machine.json'),machine);
  const settings=parse(path.join(config,'app.json'));settings.apiHost='127.0.0.1';settings.apiPort=8019;settings.presentation.mode='demo';settings.presentation.demoContentPointId='p04';write(path.join(config,'app.json'),settings);
  write(path.join(config,'remote-control.json'),{enabled:true,host:'127.0.0.1',port:8029,allowedClients:['127.0.0.1/32'],allowedOrigins:[]});
  const key='r'.repeat(43);fs.writeFileSync(path.join(config,'remote-control.key'),key);
  fs.copyFileSync(path.join(root,'content/videos/P04.mp4'),path.join(fixture,'content/videos/p04.mp4'));
  assert.equal(parse(path.join(config,'machine.json')).provider,'mock');
  const child=spawn(path.join(fixture,'slider-screen-service.exe'),['--no-browser'],{cwd:fixture,windowsHide:true,env:{...process.env,WAKEFUSION_APP_TOKEN:'patch-verification-token'}});
  let output='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>output+=b);
  let browser;
  try{
    let started=false;for(let i=0;i<150;i++){if(await fetch(base+'/api/status').then(r=>r.ok,()=>false)){started=true;break}if(child.exitCode!==null)throw Error(output);await sleep(200)}assert(started,output);
    const state=()=>fetch(base+'/api/status').then(r=>r.json());
    const initial=await state();assert.equal(initial.motorState,'arrived');
    for(const route of ['health','actions','status'])assert.equal((await fetch(base+'/api/wakefusion/v1/'+route,{headers:{Authorization:'Bearer patch-verification-token'}})).status,200);
    assert.equal((await fetch(remote+'/api/status')).status,401);
    assert.equal((await fetch(remote+'/api/status',{headers:{Authorization:'Bearer '+key}})).status,200);
    assert.equal((await fetch(remote+'/api/media/diagnostics',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:'{}'})).status,403);
    report.checks.push('Host contract routes and central-control authentication preserved');
    browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
    const page=await browser.newPage({viewport:{width:1080,height:1920}});
    let broken=true;
    await page.route('**/content/videos/*.mp4',r=>broken?r.fulfill({status:404,body:'test missing video'}):r.continue());
    await page.goto(base+'/?embed=1&avatarAnchor=right');
    await page.locator('.play-primary').click();
    await page.waitForFunction(()=>!!document.querySelector('video')?.error);
    for(let i=0;i<60&&(await state()).playbackState!=='error';i++)await sleep(100);
    assert.equal((await state()).playbackState,'error');
    const old=(await state()).mediaSessionId;
    broken=false;await page.locator('.play-primary').click();
    await page.waitForFunction(()=>{const v=document.querySelector('video');return !v.error&&!v.paused&&v.currentTime>1&&getComputedStyle(v).visibility==='visible'});
    const recovered=await state();assert.notEqual(recovered.mediaSessionId,old);
    assert.equal(recovered.currentPointId,initial.currentPointId);assert.equal(recovered.targetPointId,null);
    const logFile=path.join(fixture,'logs/media-errors.jsonl');
    await sleep(400);
    let logs=fs.readFileSync(logFile,'utf8').trim().split('\n').map(JSON.parse);
    assert(logs.some(r=>r.event==='media_error'&&r.pageMode==='embedded'&&r.errorCode>0));
    assert(logs.some(r=>r.event==='retry_requested'));
    report.checks.push('Native video failure -> click Play -> fresh visible playing media, no move');
    // Simulate a progress clock that stops, without changing playback or rail.
    await page.evaluate(()=>{const v=document.querySelector('video');const fixed=v.currentTime;Object.defineProperty(v,'currentTime',{configurable:true,get:()=>fixed})});
    await sleep(13500);
    logs=fs.readFileSync(logFile,'utf8').trim().split('\n').map(JSON.parse);
    assert(logs.some(r=>r.event==='stalled'));
    await page.evaluate(()=>{delete document.querySelector('video').currentTime});
    await sleep(2500);
    logs=fs.readFileSync(logFile,'utf8').trim().split('\n').map(JSON.parse);
    assert(logs.some(r=>r.event==='recovered'));
    assert.equal((await state()).currentPointId,initial.currentPointId);
    const raw=JSON.stringify(logs);assert(!raw.includes(key)&&!raw.includes('patch-verification-token'));
    report.checks.push('Native error, stalled clock and recovered events persisted without credentials');
    const rejected=await fetch(base+'/api/media/diagnostics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:'MUST-NOT-LOG'})});assert.equal(rejected.status,422);
    assert.equal((await fetch(base+'/api/media/diagnostics',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(9000)})).status,413);
    assert(!fs.readFileSync(logFile,'utf8').includes('MUST-NOT-LOG'));
    report.checks.push('Oversize and extra sensitive fields rejected');
    report.logRecords=logs.length;report.passed=true;
  }finally{
    if(browser)await browser.close();
    if(child.exitCode===null){child.kill();await Promise.race([new Promise(r=>child.once('exit',r)),sleep(5000)])}
    report.processOutput=output;
    fs.writeFileSync(path.join(root,'tmp/patched-runtime-verification.json'),JSON.stringify(report,null,2));
  }
  console.log(JSON.stringify({...report,processOutput:undefined},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
