// Drive headless Chrome over the DevTools protocol to test a `cad view` page: no npm packages (Node 22+ WebSocket).
//   node cad_view_browser.mjs PAGE.html [--shot OUT.png] [--selftest] [--mouse X,Y[,click]] [--eval JS] [--size 1440x900] [--timeout 90]
// --selftest opens PAGE#selftest and prints the page's CVTEST line; every console error and uncaught exception is
// printed as CONSOLE ... and fails the run, and so does any request that leaves the file (NET ...): the page is offline. --eval runs JS once the viewer is up (then waits 1 s) before the shot.
// Exit 0 when the page loaded, had no errors and (with --selftest) passed. CHROME overrides the browser binary.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const a = process.argv.slice(2);
const opt = (k, d) => (a.includes(k) ? a[a.indexOf(k) + 1] : d);
const page = a[0];
if (!page || !existsSync(page)) { console.error('usage: node cad_view_browser.mjs PAGE.html [--shot OUT.png] [--selftest] [--eval JS]'); process.exit(2); }
const selftest = a.includes('--selftest');
const [W, H] = opt('--size', '1440x900').split('x').map(Number);
const timeout = +opt('--timeout', 90) * 1000;
const chrome = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
if (!existsSync(chrome)) { console.log('NOCHROME ' + chrome); process.exit(3); }

const prof = mkdtempSync(join(tmpdir(), 'cadview-chrome-'));
const proc = spawn(chrome, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${prof}`, `--window-size=${W},${H}`,
  '--no-first-run', '--no-default-browser-check', '--enable-unsafe-swiftshader', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
let stderr = '';
proc.stderr.on('data', d => (stderr += d));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const t0 = Date.now();
let code = 1;
try {
  let port;
  while (!port) {
    if (Date.now() - t0 > 20000) throw new Error('Chrome did not start: ' + stderr.slice(-400));
    try { port = readFileSync(join(prof, 'DevToolsActivePort'), 'utf8').split('\n')[0]; } catch { await sleep(100); }
  }
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map(), logs = [], net = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
    if (m.method === 'Runtime.exceptionThrown') logs.push('exception: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
    if (m.method === 'Runtime.consoleAPICalled' && ['error', 'assert'].includes(m.params.type)) logs.push('console.error: ' + m.params.args.map(x => x.value ?? x.description).join(' '));
    if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') logs.push('log: ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
    if (m.method === 'Network.requestWillBeSent' && !/^(data|blob|file|about):/.test(m.params.request.url)) net.push(m.params.request.url);
  };
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
  await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  const url = pathToFileURL(resolve(page)).href + (selftest ? '#selftest' : '');
  const tl = Date.now();
  await send('Page.navigate', { url });
  let res = null;
  while (Date.now() - tl < timeout) {
    res = await ev(`(document.getElementById('cv-selftest') || {}).textContent || (window.cadview && !${selftest} ? 'READY' : '')`);
    if (res) break;
    await sleep(200);
  }
  const loadS = ((Date.now() - tl) / 1000).toFixed(1);
  if (!res) throw new Error(`page not ready after ${timeout / 1000} s`);
  let ok = true;
  if (selftest) {
    console.log(res);
    ok = JSON.parse(res.replace(/^CVTEST /, '')).pass === true;
  }
  if (opt('--mouse')) {   // a real pointer move (hover tooltip); 'click' after the point clicks there too
    const [x, y, c] = opt('--mouse').split(',');
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: +x, y: +y });
    await sleep(400);
    if (c === 'click') for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: +x, y: +y, button: 'left', clickCount: 1 });
    console.log('TIP ' + JSON.stringify(await ev("(document.querySelector('.ax-tip') || {}).innerText || ''")));
  }
  if (opt('--eval')) { const r = await ev(opt('--eval')); if (r !== undefined) console.log('EVAL ' + JSON.stringify(r)); await sleep(1000); }
  if (opt('--shot')) {
    await sleep(selftest ? 300 : 1800);   // the dolly-in and fly animations settle
    const s = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(opt('--shot'), Buffer.from(s.result.data, 'base64'));
    console.log('SHOT ' + opt('--shot'));
  }
  for (const l of logs) console.log('CONSOLE ' + l);
  for (const u of net) console.log('NET ' + u);
  console.log(`LOADED ${loadS} s, ${logs.length} console errors, ${net.length} network requests`);
  code = ok && !logs.length && !net.length ? 0 : 1;
  ws.close();
} catch (e) {
  console.log('ERROR ' + (e.stack || e));
} finally {
  proc.kill('SIGKILL');
  await sleep(200);
  try { rmSync(prof, { recursive: true, force: true }); } catch {}
}
process.exit(code);
