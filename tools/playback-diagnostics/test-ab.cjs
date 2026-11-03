// Developer-only test against tmp/repro-four-videos.py --offline on loopback 8017.
// Never ship this test runner to the field. It simulates the human's point clicks.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('C:/Users/27805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = __dirname;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function probeBoundaries() {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    for (const release of [false, true]) {
      const page = await browser.newPage();
      await page.route('http://127.0.0.1:8017/probe-fixture', route => route.fulfill({contentType:'text/html',body:'<body></body>'}));
      await page.goto('http://127.0.0.1:8017/probe-fixture');
      await page.evaluate(value => { window.__railDiagnosticOptions = {releaseDetached:value}; }, release);
      await page.addScriptTag({content:fs.readFileSync(path.join(root,'browser-probe.js'),'utf8')});
      const result = await page.evaluate(async () => {
        const make = name => {
          const video = document.createElement('video');
          video.preload = 'none'; video.src = '/content/videos/' + name + '.mp4';
          video.calls = {pause:0,load:0};
          video.pause = () => video.calls.pause++;
          video.load = () => video.calls.load++;
          return video;
        };
        const old = make('p01'), current = make('p02'), moved = make('p03');
        const foreign = make('outside'); foreign.src = 'http://example.invalid/foreign.mp4';
        document.body.append(old,current,moved,foreign);
        old.remove(); foreign.remove(); moved.remove(); document.body.append(moved);
        await new Promise(r=>setTimeout(r,50));
        return {old:{src:old.getAttribute('src'),calls:old.calls},current:current.calls,moved:moved.calls,foreign:foreign.calls,probe:window.__railDiagnosticProbe.read()};
      });
      assert.equal(result.old.calls.pause, release ? 1 : 0);
      assert.equal(result.old.calls.load, release ? 1 : 0);
      assert.equal(result.old.src, release ? null : '/content/videos/p01.mp4');
      for (const name of ['current','moved','foreign']) assert.deepEqual(result[name], {pause:0,load:0});
      assert.equal(result.probe.releasedCount,release?1:0);
      assert.equal(result.probe.events.filter(e=>e.event==='detached-video').length,1);
      await page.close();
    }
    console.log('PASS: only detached same-origin file videos are released; current/reinserted/foreign nodes untouched');
  } finally { await browser.close(); }
}

async function runComparison(earlyClose) {
  const reportRoot = path.join(root,'reports');
  const existing = new Set(fs.readdirSync(reportRoot));
  const child = spawn('powershell.exe',['-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(root,'compare.ps1'),'-UseExistingService','-PageUrl','http://127.0.0.1:8017/','-DurationSeconds','22','-NonInteractive','-HeadlessTest'],{windowsHide:true});
  let output=''; child.stdout.on('data', b=>output+=b); child.stderr.on('data',b=>output+=b);
  const exit=new Promise(resolve=>child.on('exit',resolve));
  let folder; const ports=[];
  for(let attempt=0;attempt<120;attempt++) {
    const created=fs.readdirSync(reportRoot).find(n=>n.startsWith('ab-')&&!existing.has(n));
    if(created){folder=path.join(reportRoot,created);break;}
    if(child.exitCode!==null)throw new Error(output);
    await sleep(250);
  }
  assert(folder,'No comparison output directory');
  for(const variant of earlyClose?['original']:['original','release']) {
    const active=path.join(folder,'browser-profile','DevToolsActivePort');
    let port;
    for(let attempt=0;attempt<200;attempt++) {
      if(fs.existsSync(active)){
        const candidate=Number(fs.readFileSync(active,'utf8').split(/\r?\n/)[0]);
        if(candidate&&!ports.includes(candidate)){port=candidate;break;}
      }
      if(child.exitCode!==null)throw new Error(output);
      await sleep(250);
    }
    assert(port,output); ports.push(port);
    const browser=await chromium.connectOverCDP('http://127.0.0.1:'+port);
    const page=browser.contexts()[0].pages()[0];
    const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
    await page.waitForSelector('.station-nav button');
    await sleep(800);
    assert.equal(posts.length,0,'Collector sent an unsolicited control command');
    for(const id of ['01','02']) {
      await page.locator('.station-nav button').filter({hasText:id}).click();
      await page.waitForFunction(id=>document.querySelector('video')?.currentSrc.endsWith('p'+id+'.mp4')&&document.querySelector('video').currentTime>1,id);
      if(id==='01')await sleep(5500); // simulated motor timeout, not real hardware
    }
    if(earlyClose)await page.close();
    assert.equal(posts.length,2,'Only the test operator should cause two activations');
    assert(posts.every(u=>/\/api\/control\/points\/p0[12]\/activate$/.test(u)),JSON.stringify(posts));
    const phaseFile=path.join(folder,variant,'report.json');
    for(let attempt=0;attempt<120;attempt++) {
      const alive=await fetch('http://127.0.0.1:'+port+'/json/version').then(()=>true,()=>false);
      if(!alive)break;
      await sleep(250);
    }
    assert.equal(await fetch('http://127.0.0.1:'+port+'/json/version').then(()=>true,()=>false),false,'Old browser process must exit before next phase');
    assert(fs.existsSync(phaseFile));
  }
  const code=await exit;
  assert.equal(code,earlyClose?1:0,output);
  const file=path.join(folder,'comparison-report.json');
  const raw=fs.readFileSync(file,'utf8'), report=JSON.parse(raw);
  assert.equal(report.completed,!earlyClose,output);
  assert.equal(report.stopMode,'duration','Explicit duration must preserve the timed test mode');
  assert.equal(report.phases.length,earlyClose?1:2);
  assert(!/Authorization|Bearer |remote-control\.key|adminPassword/.test(raw));
  for(const phase of report.phases) {
    assert.equal(phase.motionCommandsIssuedByTool,0);
    assert(phase.samples.length>=5);
    assert(phase.mediaEvents.some(e=>e.data.video_buffering_state||e.data.pipeline_buffering_state),'Need native buffering reason events');
    assert(phase.mediaRequests.length>0,'Need video transfer records');
    const readings=phase.samples.map(s=>s.browser).filter(Boolean);
    if(!earlyClose) {
      assert(readings.some(s=>s.videos.some(v=>v.sourcePath.endsWith('p02.mp4')&&v.currentTime>2)),'Current video must keep playing');
      assert.equal(phase.completed,true);
      assert.equal(phase.completionReason,'duration-elapsed');
      assert(phase.mediaProperties.some(p=>p.properties.some(v=>v.name==='kVideoDecoderName')));
      assert.equal(phase.cdpEventsDiscarded,0);
    }
    if(phase.variant==='original')assert(readings.every(s=>s.releasedCount===0));
    else assert(readings.some(s=>s.releasedCount>=1),'B must actually release a detached video');
  }
  assert.equal((await fetch('http://127.0.0.1:8017/api/status')).status,200,'Must preserve pre-existing backend');
  console.log(JSON.stringify({test:earlyClose?'AB-abort-keeps-partial-report':'AB-two-phases',passed:true,file,phases:report.phases.map(p=>({variant:p.variant,samples:p.samples.length,releaseCount:Math.max(...p.samples.map(s=>s.browser?.releasedCount||0)),requests:p.mediaRequests.length,mediaEvents:p.mediaEvents.length})),ports}));
}

(async()=>{await probeBoundaries();await runComparison(false);await runComparison(true);})().catch(e=>{console.error(e);process.exitCode=1;});
