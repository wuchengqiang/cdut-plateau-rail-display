// Local-only automated test. Requires the isolated mock application on 8017.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { chromium } = require('C:/Users/27805/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = __dirname;
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function run(earlyClose) {
  const existing = new Set(fs.existsSync(path.join(root, 'reports')) ? fs.readdirSync(path.join(root, 'reports')) : []);
  const child = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'collect.ps1'), '-UseExistingService', '-PageUrl', 'http://127.0.0.1:8017/', '-DurationSeconds', '22', '-NonInteractive', '-HeadlessTest'], {windowsHide:true});
  let text = '';
  child.stdout.on('data', b=>text+=b.toString());
  child.stderr.on('data', b=>text+=b.toString());
  const exit = new Promise(resolve=>child.on('exit', code=>resolve(code)));
  let folder, port;
  for(let attempt=0;attempt<120;attempt++) {
    const names = fs.existsSync(path.join(root,'reports')) ? fs.readdirSync(path.join(root,'reports')) : [];
    const created = names.find(n=>!existing.has(n));
    if(created) {
      folder=path.join(root,'reports',created);
      const active=path.join(folder,'test-browser-profile','DevToolsActivePort');
      if(fs.existsSync(active)) {port=Number(fs.readFileSync(active,'utf8').split(/\r?\n/)[0]);if(port)break;}
    }
    if(child.exitCode!==null) throw new Error(text);
    await sleep(250);
  }
  assert(port,'Collector did not create a local debug endpoint');
  const browser=await chromium.connectOverCDP('http://127.0.0.1:'+port);
  const context=browser.contexts()[0], page=context.pages()[0];
  const requests=[];
  page.on('request',r=>{if(r.method()!=='GET')requests.push({method:r.method(),url:r.url()});});
  await page.waitForSelector('.station-nav button');
  await sleep(1000);
  assert.equal(requests.filter(r=>r.method==='POST').length,0,'Collector must not issue POST commands');
  const button=id=>page.locator('.station-nav button').filter({hasText:id});
  // These clicks are the TEST operator, not collector behavior. Motor is forced mock.
  await button('01').click();
  await page.waitForFunction(()=>document.querySelector('video')?.currentTime>1);
  await sleep(5500);
  await button('02').click();
  await page.waitForFunction(()=>document.querySelector('video')?.currentSrc.endsWith('p02.mp4')&&document.querySelector('video').currentTime>1);
  if(earlyClose) await page.close();
  const code=await exit;
  const report=JSON.parse(fs.readFileSync(path.join(folder,'report.json'),'utf8'));
  assert.equal(code,earlyClose?1:0,text);
  assert.equal(report.completed,!earlyClose);
  assert.equal(report.motionCommandsIssuedByTool,0);
  assert(report.samples.length>=5);
  const videos=report.samples.flatMap(s=>s.browser?.videos||[]);
  assert(videos.some(v=>v.sourcePath.endsWith('p01.mp4')&&v.currentTime>0));
  if(!earlyClose) assert(videos.some(v=>v.sourcePath.endsWith('p02.mp4')&&v.currentTime>0));
  assert(videos.every(v=>!v.sourcePath.includes('?')));
  assert(report.mediaProperties.some(p=>p.properties.some(v=>v.name==='kVideoDecoderName')),'No decoder properties');
  assert(report.systemSamples.length>0);
  const body=fs.readFileSync(path.join(folder,'report.json'),'utf8');
  assert(!/Authorization|Bearer |remote-control\.key|adminPassword/.test(body));
  const unexpected=requests.filter(r=>r.method==='POST'&&!/\/api\/control\/points\/p0[12]\/activate$/.test(r.url));
  assert.equal(unexpected.length,0,JSON.stringify(unexpected));
  const endpointAlive=await fetch('http://127.0.0.1:'+port+'/json/version').then(()=>true,()=>false);
  assert.equal(endpointAlive,false,'Diagnostic port should close on exit');
  assert.equal((await fetch('http://127.0.0.1:8017/api/status')).status,200,'Must not terminate existing service');
  console.log(JSON.stringify({test:earlyClose?'early-close-partial-report':'complete-point-switching',samples:report.samples.length,decoder:report.mediaProperties.flatMap(p=>p.properties).filter(p=>p.name==='kVideoDecoderName').map(p=>p.value),report:path.relative(root,path.join(folder,'report.json')),passed:true}));
}
(async()=>{await run(false);await run(true);})().catch(e=>{console.error(e);process.exitCode=1;});
