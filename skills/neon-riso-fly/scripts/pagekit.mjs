/* Shared by the headless tools: find a Chrome, find an ffmpeg, and turn a served page into one
 * self-contained file.
 *
 * A neon-riso page loads the core through an HTML comment marker and fetches its contract file
 * over http. inlinePage() puts both inside the page, so it can be opened from a temporary
 * file:// URL with no server at all - which is what a recorder and an unattended job want.
 * Every "<" inside inlined data is escaped, so nothing inlined can close a script block early.
 *
 * Project-agnostic: paths are resolved against the repository root (the parent of scripts/),
 * and the core is found by reading the page's own <script src> inside the marker. */
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

export const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const LIB = /<!--NEON-RISO-->([\s\S]*?)<!--\/NEON-RISO-->/;

/* The core the page asks for, resolved relative to the page itself, so any layout works. */
function coreFor(pagePath, marker) {
  const src = /src\s*=\s*["']([^"']+)["']/.exec(marker);
  if (!src) throw new Error(`the NEON-RISO block in ${pagePath} has no <script src>`);
  return resolve(dirname(resolve(repo, pagePath)), src[1]);
}

export function inlinePage(pagePath, dataPath, extra = '') {
  const page = readFileSync(resolve(repo, pagePath), 'utf8');
  const m = LIB.exec(page);
  if (!m) throw new Error(`${pagePath} has no <!--NEON-RISO--> block to inline`);
  const lib = readFileSync(coreFor(pagePath, m[1]), 'utf8');
  if (/<\/script/i.test(lib)) throw new Error('the neon riso core contains a closing script tag');

  let head = extra;
  let run = null;
  if (dataPath) {
    run = JSON.parse(readFileSync(resolve(repo, dataPath), 'utf8'));
    head = `window.__HEDGEFLY_RUN__=${JSON.stringify(run).replace(/</g, '\\u003c')};${extra}`;
  }
  return { run, html: page.replace(LIB, () => `<script>${head}</script>\n<script>\n${lib}\n</script>`) };
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
  try {
    if (execFileSync('ffmpeg', ['-hide_banner', '-encoders']).toString().includes('libx264'))
      return { bin: 'ffmpeg', h264: true };
  } catch { /* none on PATH */ }
  const cache = join(homedir(), '.cache', 'ms-playwright');
  if (existsSync(cache)) for (const d of readdirSync(cache).filter(d => d.startsWith('ffmpeg-')).sort().reverse()) {
    const bin = join(cache, d, 'ffmpeg-linux');
    if (existsSync(bin)) return { bin, h264: false };
  }
  return null;
}

/* ---- a minimal DevTools client: headless Chrome over Node's own WebSocket, no packages ---- */
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
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { const { ok, fail } = pending.get(m.id); pending.delete(m.id); m.error ? fail(new Error(JSON.stringify(m.error))) : ok(m.result); }
    else if (m.method) for (const l of listeners) l(m);
  };
  const send = (method, params = {}, sessionId) => new Promise((ok, fail) => {
    const msg = { id: ++id, method, params }; if (sessionId) msg.sessionId = sessionId;
    pending.set(msg.id, { ok, fail }); ws.send(JSON.stringify(msg));
  });
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
