/* Shared by the headless tools: find a Chrome, and turn a served page into one self-contained file.
 *
 * A page under visuals/ loads ../lib/neon-riso.js and fetches ../hq/runs.json. inlinePage() puts
 * both inside the page, so it can be opened from a temporary file with no server - which is what an
 * unattended job wants. Every "<" inside inlined data is written as < so nothing inlined can
 * close a script block early. */
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

export const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const LIB = /<!--NEON-RISO-->[\s\S]*?<!--\/NEON-RISO-->/;

export function inlinePage(pagePath, dataPath = 'visuals/hq/runs.json', extra = '') {
  let page = readFileSync(resolve(repo, pagePath), 'utf8');
  const lib = readFileSync(resolve(repo, 'visuals/lib/neon-riso.js'), 'utf8');
  const run = JSON.parse(readFileSync(resolve(repo, dataPath), 'utf8'));
  if (!LIB.test(page)) throw new Error(`${pagePath} has no <!--NEON-RISO--> block to inline`);
  if (/<\/script/i.test(lib)) throw new Error('the neon riso core contains a closing script tag');
  const data = JSON.stringify(run).replace(/</g, '\\u003c');
  return { run, html: page.replace(LIB, () => `<script>window.__HEDGEFLY_RUN__=${data};${extra}</script>\n<script>\n${lib}\n</script>`) };
}

/* A headless Chrome: $HEDGEFLY_CHROME, else the newest Playwright headless shell, else PATH. */
export function findChrome() {
  if (process.env.HEDGEFLY_CHROME) return process.env.HEDGEFLY_CHROME;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  if (existsSync(cache)) {
    const shells = readdirSync(cache).filter(d => d.startsWith('chromium_headless_shell-')).sort().reverse();
    for (const d of shells) for (const sub of readdirSync(join(cache, d))) {
      const bin = join(cache, d, sub, 'chrome-headless-shell');
      if (existsSync(bin)) return bin;
    }
  }
  return 'chromium';
}

/* An ffmpeg that can write H.264, else Playwright's VP8-only build, else nothing. */
export function findFfmpeg() {
  if (process.env.HEDGEFLY_FFMPEG) return { bin: process.env.HEDGEFLY_FFMPEG, h264: true };
  try { if (execFileSync('ffmpeg', ['-hide_banner', '-encoders']).toString().includes('libx264')) return { bin: 'ffmpeg', h264: true }; } catch { /* none */ }
  const cache = join(homedir(), '.cache', 'ms-playwright');
  if (existsSync(cache)) for (const d of readdirSync(cache).filter(d => d.startsWith('ffmpeg-')).sort().reverse()) {
    const bin = join(cache, d, 'ffmpeg-linux');
    if (existsSync(bin)) return { bin, h264: false };
  }
  return null;
}

/* ---- a minimal DevTools client: headless Chrome over Node's own WebSocket ------------- */
export async function launch(w, h) {
  const chrome = spawn(findChrome(), ['--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--allow-file-access-from-files', '--remote-debugging-port=0', `--window-size=${w},${h}`, 'about:blank'],
    { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((ok, fail) => {
    let buf = '';
    const t = setTimeout(() => fail(new Error('Chrome did not start (no DevTools endpoint within 20 s)')), 20000);
    chrome.stderr.on('data', d => { buf += d; const m = buf.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); ok(m[1]); } });
    chrome.on('exit', c => fail(new Error(`Chrome exited with ${c} before it was ready:\n${buf.slice(-600)}`)));
  });
  const ws = new WebSocket(wsUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let id = 0; const pending = new Map(), listeners = [];
  ws.onmessage = e => { const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const { ok, fail } = pending.get(m.id); pending.delete(m.id); m.error ? fail(new Error(JSON.stringify(m.error))) : ok(m.result); }
    else if (m.method) for (const l of listeners) l(m); };
  const send = (method, params = {}, sessionId) => new Promise((ok, fail) => {
    const msg = { id: ++id, method, params }; if (sessionId) msg.sessionId = sessionId;
    pending.set(msg.id, { ok, fail }); ws.send(JSON.stringify(msg)); });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const page = (m, p) => send(m, p, sessionId);
  await page('Page.enable');
  await page('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  const once = method => new Promise(ok => listeners.push(m => m.method === method && m.sessionId === sessionId && ok(m)));
  const evaluate = async expr => {
    const r = await page('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(`page error in ${expr}: ${r.exceptionDetails.text} ${r.exceptionDetails.exception?.description || ''}`);
    return r.result.value;
  };
  return { chrome, ws, page, once, evaluate };
}
