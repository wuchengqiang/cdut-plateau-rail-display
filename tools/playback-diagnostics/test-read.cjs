// Developer-only: forced-mock backend on 8017. No activations or motor actions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const http = require('node:http');
const {chromium} = require('C:/Users/27805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=__dirname, workspace=path.resolve(root,'../..'), reports=path.join(root,'reports');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function run({reverse=false,early=false,badHead=false,moving=false}={}) {
  const before=await fetch('http://127.0.0.1:8017/api/status').then(r=>r.json());
  let stub;
  let url='http://127.0.0.1:8017/';
  if(badHead||moving){
    stub=http.createServer((req,res)=>{
      assert(['GET','HEAD'].includes(req.method));
      if(req.url==='/api/status'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify(moving?{...before,motorState:'moving',targetPointId:'p01'}:before));}
      else {res.setHeader('Content-Length','1');res.end(req.method==='HEAD'?undefined:'x');}
    });
    await new Promise(r=>stub.listen(0,'127.0.0.1',r));url='http://127.0.0.1:'+stub.address().port+'/';
  }
  const existing=new Set(fs.readdirSync(reports));
  const args=['-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(root,'read-compare.ps1'),'-UseExistingService','-RuntimeRoot',workspace,'-VideoPath',path.join(workspace,'content/videos/P04.mp4'),'-PageUrl',url,'-DurationSeconds','12','-NonInteractive','-HeadlessTest'];
  if(reverse)args.push('-ReverseOrder');
  const child=spawn('powershell.exe',args,{windowsHide:true});
  let output='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>output+=b);
  const exit=new Promise(r=>child.on('exit',r));
  let folder;
  for(let i=0;i<100;i++){const n=fs.readdirSync(reports).find(n=>n.startsWith('read-')&&!existing.has(n));if(n){folder=path.join(reports,n);break;}await sleep(200);}
  assert(folder,output);
  const ports=[], observed=[];
  if(!badHead&&!moving){
    const order=reverse?['http','file']:['file','http'];
    for(const kind of early?order.slice(0,1):order){
      let port;
      for(let i=0;i<180;i++){
        const active=path.join(folder,'browser-profile/DevToolsActivePort');
        if(fs.existsSync(active)){const n=Number(fs.readFileSync(active,'utf8').split(/\r?\n/)[0]);if(n&&!ports.includes(n)){port=n;break;}}
        if(child.exitCode!==null)throw new Error(output);
        await sleep(250);
      }
      assert(port,output);ports.push(port);
      const browser=await chromium.connectOverCDP('http://127.0.0.1:'+port);
      const page=browser.contexts()[0].pages()[0];
      page.on('request',q=>observed.push({method:q.method(),url:q.url()}));
      await page.waitForFunction(()=>window.__railReadProbe&&document.querySelector('video').currentTime>1);
      const state=await page.evaluate(()=>({probe:window.__railReadProbe.read(),url:location.href,src:document.querySelector('video').currentSrc}));
      assert.equal(state.probe.kind,kind);assert.equal(state.probe.video.actualSourceKind,kind);
      assert(state.url.startsWith('file:')&&state.url.endsWith('read-player.html'));
      assert(state.probe.video.width>0);assert.equal(state.probe.video.volume,.5);assert.equal(state.probe.video.muted,false);
      assert.equal(await page.locator('.station-nav').count(),0);
      if(early)await page.close();
      for(let i=0;i<100;i++){if(!await fetch('http://127.0.0.1:'+port+'/json/version').then(()=>true,()=>false))break;await sleep(250);}
      assert.equal(await fetch('http://127.0.0.1:'+port+'/json/version').then(()=>true,()=>false),false);
    }
  }
  const code=await exit;
  if(stub)await new Promise(r=>stub.close(r));
  assert.equal(code,(early||badHead||moving)?1:0,output);
  const file=path.join(folder,'read-comparison-report.json');
  const raw=fs.readFileSync(file,'utf8'),report=JSON.parse(raw);
  assert.equal(report.completed,!(early||badHead||moving));
  assert.equal(report.motionCommandsIssuedByTool,0);assert.equal(report.controlRequestsObserved,0);
  assert(!/Authorization|Bearer |adminPassword|remote-control\.key/.test(raw));
  assert(observed.every(q=>q.method==='GET'));assert(!observed.some(q=>q.url.includes('/api/')));
  if(badHead||moving)assert.equal(report.phases.length,0);
  else if(early){assert.equal(report.phases.length,1);assert(report.phases[0].samples.length>0);}
  else {
    assert.equal(report.sampledContentMatches,true);assert.equal(report.fileUnchangedDuringRun,true);
    assert.equal(report.validComparison,true);
    assert.equal(report.readChecks.length,3);
    for(const c of report.readChecks){assert(c.matching);assert.equal(c.http.status,206);assert.equal(c.file.sha256,c.http.sha256);assert(c.http.mibPerSecond>0);}
    for(const p of report.phases){
      assert.equal(p.completed,true);assert.equal(p.completionReason,'duration-elapsed');assert.equal(p.cdpEventsDiscarded,0);
      assert.equal(p.playbackObserved,true);
      assert(p.samples.some(s=>s.browser?.video.currentTime>5));
      assert(p.mediaProperties.some(e=>e.properties.some(x=>x.name==='kVideoDecoderName')));
      if(p.kind==='http')assert(p.mediaRequests.some(q=>q.headers.range&&q.responseHeaders?.['content-range']));
    }
  }
  const after=await fetch('http://127.0.0.1:8017/api/status').then(r=>r.json());
  for(const k of ['currentPointId','targetPointId','mediaSessionId','playbackRevision','playbackState'])assert.equal(after[k],before[k],k+' must not change');
  console.log(JSON.stringify({test:moving?'refuse-active-motion':badHead?'reject-wrong-media':early?'early-close-saves-partial':reverse?'http-then-file':'file-then-http',passed:true,report:file,phases:report.phases.map(p=>({kind:p.kind,samples:p.samples.length,requests:p.mediaRequests.length})),reads:report.readChecks.length}));
}
(async()=>{await run();await run({reverse:true});await run({early:true});await run({badHead:true});await run({moving:true});})().catch(e=>{console.error(e);process.exitCode=1;});
