// Functional recovery tests, not a substitute for the real digital-human Host.
// Uses only an isolated loopback service with a motor that rejects all actions.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/27805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(__dirname,'../..'), base='http://127.0.0.1:8018';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const results=[];
const serverCode=String.raw`
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
from app import config
load = config.load_configuration
def isolated():
    app, scenes, machine = load()
    app['presentation']['mode'] = 'visit'
    machine['provider'] = 'mock'
    return app, scenes, machine
config.load_configuration = isolated
from app.main import app, runtime
from app import main as application_module
from app.media_diagnostics import MediaDiagnostics
application_module.media_diagnostics = MediaDiagnostics(Path(sys.argv[1]))
from app.services import MockMotorProvider
from fastapi.responses import HTMLResponse
assert isinstance(runtime.motor, MockMotorProvider)
attempts=[]
async def forbidden(*args):
    attempts.append('unexpected motor action')
    raise AssertionError('Test must not request motor action')
runtime.motor.move_to=forbidden
runtime.motor.home=forbidden
runtime.motor.stop=forbidden
runtime.state.current_scene='p03'
runtime.state.display_scene='p03'
@app.get('/diagnostic/safety')
async def safety():
    return {'motorActions': attempts}
@app.get('/diagnostic/frame')
async def frame():
    return HTMLResponse('<iframe src="/?embed=1&avatarAnchor=right" sandbox="allow-scripts allow-same-origin" allow="autoplay" style="width:1080px;height:1920px"></iframe>')
# Register fixture routes ahead of the application's SPA catch-all.
fixtures=app.router.routes[-2:]
app.router.routes[:]=fixtures+app.router.routes[:-2]
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=8018,access_log=False)
`;
async function run({embedded=false,dropFeedback=false,externalPlay=false,midPlayback=false}={}){
  const label={embedded,dropFeedback,externalPlay,midPlayback};
  const logRoot=fs.mkdtempSync(path.join(root,'tmp/media-recovery-log-'));
  const server=spawn('python',['-c',serverCode,logRoot],{cwd:root,windowsHide:true});
  let logs='';server.stderr.on('data',b=>logs+=b);server.stdout.on('data',b=>logs+=b);
  let browser;
  const status=()=>fetch(base+'/api/status').then(r=>r.json());
  const post=async(path,body)=>{const r=await fetch(base+path,{method:'POST',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});assert(r.ok,await r.text());};
  try{
    for(let i=0;i<100;i++){if(await fetch(base+'/api/status').then(r=>r.ok,()=>false))break;if(server.exitCode!==null)throw Error(logs);await sleep(100)}
    browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
    const context=await browser.newContext({viewport:{width:1080,height:1920}});
    const page=await context.newPage();
    const controls=[],errors=[],diagnosticStatuses=[];
    page.on('response',r=>{if(r.url().endsWith('/api/media/diagnostics'))diagnosticStatuses.push(r.status())});
    let broken=!midPlayback,mediaRequests=0;
    page.on('pageerror',e=>errors.push(String(e)));
    page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/api/control/'))controls.push(new URL(r.url()).pathname)});
    await context.route('**/content/videos/*.mp4',async route=>{
      mediaRequests++;
      if(broken)await route.fulfill({status:404,body:'diagnostic missing media'});
      else await route.continue();
    });
    if(dropFeedback)await context.route('**/api/media/events',route=>route.fulfill({contentType:'application/json',body:'{"success":true,"accepted":false}'}));
    await page.goto(base+(embedded?'/diagnostic/frame':'/'));
    let view=page;
    if(embedded){await page.waitForSelector('iframe');view=page.frames().find(f=>f.parentFrame());}
    await view.waitForFunction(()=>document.querySelector('.scene-intro h2')?.textContent.includes('冰川'));
    const play=view.locator('.playback-controls .play-primary');
    await play.click();
    if(midPlayback){
      await view.waitForFunction(()=>document.querySelector('video')?.currentTime>2);
      broken=true;
      await view.evaluate(()=>{const v=document.querySelector('video');v.load();void v.play().catch(()=>{});});
    }
    await view.waitForFunction(()=>Boolean(document.querySelector('video')?.error));
    if(!dropFeedback){for(let i=0;i<60&&(await status()).playbackState!=='error';i++)await sleep(100);assert.equal((await status()).playbackState,'error');}
    const failed=await status();
    const beforeWait=mediaRequests;
    await sleep(1000);
    assert.equal(mediaRequests,beforeWait,'Failure must not trigger an automatic retry storm');
    assert.equal(await view.locator('video').evaluate(v=>getComputedStyle(v).visibility),'hidden');
    // Keep just the old element for the duration of this correctness check, to
    // explicitly verify it was released; this is not a performance benchmark.
    await view.evaluate(()=>{window.failedVideo=document.querySelector('video')});
    broken=false;
    if(externalPlay)await post('/api/control/play');else await play.click();
    await view.waitForFunction(()=>{const v=document.querySelector('video');return v&&!v.error&&!v.paused&&v.currentTime>1&&getComputedStyle(v).visibility==='visible'},{},{timeout:20000});
    const recovered=await status();
    assert.equal(recovered.currentPointId,'p03');assert.equal(recovered.targetPointId,null);
    assert.equal(recovered.displayPointId,'p03');assert.equal(recovered.playbackState,'playing');
    if(!dropFeedback){
      assert.notEqual(recovered.mediaSessionId,failed.mediaSessionId);
      assert.deepEqual(await view.evaluate(()=>({connected:window.failedVideo.isConnected,src:window.failedVideo.getAttribute('src'),paused:window.failedVideo.paused})),{connected:false,src:null,paused:true});
      await post('/api/media/events',{sessionId:failed.mediaSessionId,revision:recovered.playbackRevision,event:'error'});
      assert.equal((await status()).playbackState,'playing','Old feedback must not hide recovered video');
    }
    // Healthy pause/resume: same element/session and preserved position.
    await view.locator('.playback-controls button').filter({hasText:/^暂停$/}).click();
    await view.waitForFunction(()=>document.querySelector('video').paused);
    const paused=await view.locator('video').evaluate(v=>v.currentTime);
    await sleep(700);
    assert(Math.abs(await view.locator('video').evaluate(v=>v.currentTime)-paused)<.1);
    await play.click();
    await view.waitForFunction(t=>document.querySelector('video').currentTime>t+.25,paused);
    assert.equal((await status()).mediaSessionId,recovered.mediaSessionId);
    assert.equal((await fetch(base+'/diagnostic/safety').then(r=>r.json())).motorActions.length,0);
    assert(controls.every(p=>['/api/control/play','/api/control/pause'].includes(p)),JSON.stringify(controls));
    assert.deepEqual(errors,[]);
    await sleep(300);
    assert(diagnosticStatuses.length>0&&diagnosticStatuses.every(s=>s===200),JSON.stringify(diagnosticStatuses));
    const lines=fs.readFileSync(path.join(logRoot,'logs/media-errors.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
    assert(lines.some(x=>x.event==='media_error'&&x.pageId!=='server'&&x.errorCode>0));
    assert(lines.every(x=>x.frontendBuild==='recovery-diagnostics-20261102'));
    assert(!JSON.stringify(lines).includes('http://'),'Logs must not contain full URLs');
    results.push({...label,passed:true,nativeErrorRecovered:true,motorActions:0,logRecords:lines.length});
    console.log(JSON.stringify(results.at(-1)));
  }finally{
    if(browser)await browser.close();
    if(server.exitCode===null){server.kill();await Promise.race([new Promise(r=>server.once('exit',r)),sleep(5000)])}
  }
}
(async()=>{
  assert(!await fetch(base+'/api/status').then(()=>true,()=>false),'8018 occupied; refusing unknown service');
  await run();
  await run({embedded:true,externalPlay:true});
  await run({embedded:true,dropFeedback:true});
  await run({embedded:true,dropFeedback:true,externalPlay:true});
  await run({embedded:true,midPlayback:true});
  fs.mkdirSync(path.join(root,'tmp'),{recursive:true});
  fs.writeFileSync(path.join(root,'tmp/media-recovery-browser-report.json'),JSON.stringify({at:new Date().toISOString(),results},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
