#!/usr/bin/env node
/* Record Natural Selection Capital HQ to frames, and to video where this machine can encode it.
 *
 *     node scripts/record_hq.mjs                                   # everything, wide and vertical
 *     node scripts/record_hq.mjs --shapes wide --only lab,floor --seconds 4 --fps 30
 *
 * Shots, in order: the establishing shot of the whole building; every room, with generations
 * playing so the selection event happens on camera; the hero cam following the hero fly on its
 * rounds; and the finale - the vault swinging open on the scoreboard - if a finale exists.
 *
 * It drives headless Chrome over the DevTools protocol with Node's own WebSocket (no packages),
 * and steps the HQ's virtual clock one frame at a time (?record, window.__hedgefly.step), so a
 * recording is exact, repeatable, and never drops a frame however slow the capture is.
 *
 * Output: results/film/<shape>/<shot>/frame_00001.png ... always. Video: this Spark has no
 * ffmpeg with H.264, only Playwright's VP8 build, so it also writes <shot>.webm previews here
 * and prints the one-line command to turn the frames into mp4 on a machine that has ffmpeg
 * (Windows: `winget install ffmpeg`). Set $HEDGEFLY_FFMPEG to an ffmpeg with libx264 to get mp4
 * directly. The data is the same runs.json every other visual reads (PLAN.md rule 8). */
import { spawn, execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir, homedir } from 'node:os';
import { repo, inlinePage, findChrome } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const SHAPES = { wide: [1920, 1080], vertical: [1080, 1920] };
const shapes = arg('shapes', 'wide,vertical').split(',');
const fps = +arg('fps', 30), seconds = +arg('seconds', 6);
const only = arg('only', null)?.split(',');
const out = resolve(repo, arg('out', 'results/film'));

function findFfmpeg() {
  if (process.env.HEDGEFLY_FFMPEG) return { bin: process.env.HEDGEFLY_FFMPEG, h264: true };
  try { if (execFileSync('ffmpeg', ['-hide_banner', '-encoders']).toString().includes('libx264')) return { bin: 'ffmpeg', h264: true }; } catch { /* none */ }
  const cache = join(homedir(), '.cache', 'ms-playwright');
  if (existsSync(cache)) for (const d of readdirSync(cache).filter(d => d.startsWith('ffmpeg-')).sort().reverse()) {
    const bin = join(cache, d, 'ffmpeg-linux');
    if (existsSync(bin)) return { bin, h264: false };
  }
  return null;
}

/* ---- a minimal DevTools client ---------------------------------------------------------- */
async function launch(w, h) {
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

/* ---- the shots ------------------------------------------------------------------------- */
function shotList(rooms, hasFinale) {
  const list = [{ name: '00_establishing', setup: "__hedgefly.shot('building',null,0);__hedgefly.play(true)", frames: seconds * 1.4 }];
  rooms.forEach((r, k) => list.push({ name: `${String(k + 1).padStart(2, '0')}_${r}`,
    setup: `__hedgefly.shot('room','${r}',0);__hedgefly.play(true)`, frames: seconds }));
  list.push({ name: `${String(rooms.length + 1).padStart(2, '0')}_hero_cam`, setup: "__hedgefly.shot('hero');__hedgefly.play(true)", frames: seconds * 2 });
  if (hasFinale) list.push({ name: `${String(rooms.length + 2).padStart(2, '0')}_finale`, finale: true,
    setup: `__hedgefly.shot('room','vault',0);__hedgefly.play(false);__hedgefly.gen(__hedgefly.generations()-1);__hedgefly.sel(1);__hedgefly.open(0)`, frames: seconds });
  return list.filter(s => !only || only.some(o => s.name.includes(o)));
}

async function record(shape) {
  const [w, h] = SHAPES[shape];
  const extra = 'window.__HEDGEFLY_VCLOCK__=0;window.__HEDGEFLY_VCLOCK_DRIVEN__=true;';
  const { html } = inlinePage('visuals/hq2/index.html', arg('data', 'visuals/hq/runs.json'), extra);
  const file = join(tmpdir(), `hedgefly-record-${process.pid}-${shape}.html`);
  writeFileSync(file, html);
  const b = await launch(w, h);
  try {
    const loaded = b.once('Page.loadEventFired');
    await b.page('Page.navigate', { url: `file://${file}?record&clean${shape === 'vertical' ? '&vertical' : ''}` });
    await loaded;
    for (let k = 0; k < 200 && !(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++) await new Promise(r => setTimeout(r, 100));
    const rooms = await b.evaluate('__hedgefly.rooms()'), hasFinale = await b.evaluate('__hedgefly.hasFinale()');
    const ffmpeg = findFfmpeg(), made = [];
    for (const shot of shotList(rooms, hasFinale)) {
      const dir = join(out, shape, shot.name); rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
      await b.evaluate(shot.setup);
      const n = Math.round(shot.frames * fps);
      // Playwright's ffmpeg reads only piped JPEGs (image2pipe + mjpeg), so the VP8 preview is fed
      // a JPEG of every frame while the lossless PNG frames go to disk for the edit.
      let pipe = null, piped = null;
      if (ffmpeg && !ffmpeg.h264) {
        const target = join(out, shape, `${shot.name}.webm`);
        pipe = spawn(ffmpeg.bin, ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-c:v', 'mjpeg', '-framerate', String(fps),
          '-i', 'pipe:0', '-an', '-c:v', 'libvpx', '-b:v', '10M', target], { stdio: ['pipe', 'ignore', 'pipe'] });
        let err = ''; pipe.stderr.on('data', d => { err += d; });
        piped = new Promise(ok => pipe.on('exit', c => ok(c === 0 ? target : `(preview failed: ${err.trim().split('\n')[0]})`)));
      }
      for (let f = 0; f < n; f++) {
        if (shot.finale) await b.evaluate(`__hedgefly.open(${Math.min(1, f / (n * .55)).toFixed(4)})`);
        await b.evaluate(`__hedgefly.step(${(1000 / fps).toFixed(4)})`);
        const { data } = await b.page('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(dir, `frame_${String(f + 1).padStart(5, '0')}.png`), Buffer.from(data, 'base64'));
        if (pipe) { const { data: jpg } = await b.page('Page.captureScreenshot', { format: 'jpeg', quality: 92 });
          await new Promise(ok => pipe.stdin.write(Buffer.from(jpg, 'base64'), ok)); }
      }
      let video = '';
      if (pipe) { pipe.stdin.end(); video = await piped; }
      else if (ffmpeg) {
        const target = join(out, shape, `${shot.name}.${ffmpeg.h264 ? 'mp4' : 'webm'}`);
        const codec = ffmpeg.h264 ? ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18'] : ['-c:v', 'libvpx', '-b:v', '12M'];
        try { execFileSync(ffmpeg.bin, ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', join(dir, 'frame_%05d.png'), ...codec, target]); video = target; }
        catch (e) { video = `(encoding failed: ${String(e.message).split('\n')[0]})`; }
      }
      made.push(`${shot.name}: ${n} frames${video ? ' -> ' + video : ''}`);
      console.log(`  ${shape} ${shot.name}: ${n} frames${video ? ', ' + video : ''}`);
    }
    return { made, ffmpeg };
  } finally {
    b.ws.close(); b.chrome.kill('SIGKILL'); rmSync(file, { force: true });
  }
}

console.log(`recording ${shapes.join(' + ')} at ${fps} fps into ${out}`);
let ffmpeg = null;
for (const shape of shapes) ({ ffmpeg } = await record(shape));
if (!ffmpeg || !ffmpeg.h264) {
  console.log(`\nNo H.264 encoder here${ffmpeg ? ' (only VP8: .webm previews were written)' : ''}. For mp4, copy results/film to a machine with ffmpeg and run, in each shot folder:`);
  console.log('  ffmpeg -framerate ' + fps + ' -i frame_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 18 shot.mp4');
  console.log('On Windows (PowerShell), for every shot at once, from results\\film:');
  console.log('  Get-ChildItem -Directory -Recurse | Where-Object { Test-Path "$($_.FullName)\\frame_00001.png" } | ForEach-Object { ffmpeg -y -framerate ' + fps + ' -i "$($_.FullName)\\frame_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 "$($_.FullName).mp4" }');
}
