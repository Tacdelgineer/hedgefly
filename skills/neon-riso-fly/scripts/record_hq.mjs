#!/usr/bin/env node
/* Film a neon riso world headless: PNG frames always, mp4 where this machine can encode.
 *
 *     node scripts/record_hq.mjs --page visuals/world/index.html --data visuals/world/data.json
 *     node scripts/record_hq.mjs --page visuals/world/index.html --shapes wide --only vault --seconds 10
 *
 * Shots, in order: an establishing shot of the whole building; then every room the page
 * declares, with the world advancing so anything that changes per stage happens on camera;
 * then any extra shots the page offers through __hedgefly.shots().
 *
 * It drives headless Chrome over the DevTools protocol with Node's own WebSocket (no packages),
 * and steps the page's virtual clock one frame at a time (?record, window.__hedgefly.step), so
 * a recording is exact, repeatable, and never drops a frame however slowly the capture runs.
 *
 * Output: <out>/<shape>/<shot>/frame_00001.png ... always, plus <shot>.mp4 when an ffmpeg that
 * can write H.264 is available (apt install ffmpeg; winget install ffmpeg on Windows). Without
 * one it writes VP8 .webm previews and prints the command to encode the frames elsewhere.
 * $HEDGEFLY_FFMPEG overrides the choice, $HEDGEFLY_CHROME the browser.
 *
 * The page must expose window.__hedgefly - see SKILL.md, "The control surface a page must
 * expose". Everything on screen comes from --data; this script never invents a number. */
import { spawn, execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { repo, inlinePage, findFfmpeg, launch } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const SHAPES = { wide: [1920, 1080], vertical: [1080, 1920] };
const page = arg('page', 'visuals/world/index.html');
const data = arg('data', 'visuals/world/data.json');
const shapes = arg('shapes', 'wide,vertical').split(',');
const fps = +arg('fps', 30), seconds = +arg('seconds', 6);
const only = arg('only', null)?.split(',');
const out = resolve(repo, arg('out', 'results/film'));

/* ---- the shots ----------------------------------------------------------------------------
   Built from what the page says it has, so a project with different rooms needs no edit here.
   A page may add its own with __hedgefly.shots() returning [{name, setup, seconds}]. */
function shotList(rooms, extra) {
  const list = [{ name: '00_establishing', frames: seconds * 1.4,
                  setup: "__hedgefly.shot('building',null,0);__hedgefly.play&&__hedgefly.play(true)" }];
  rooms.forEach((r, k) => list.push({
    name: `${String(k + 1).padStart(2, '0')}_${r}`, frames: seconds,
    setup: `__hedgefly.shot('room','${r}',0);__hedgefly.play&&__hedgefly.play(true)` }));
  (extra || []).forEach((s, k) => list.push({
    name: s.name || `${String(rooms.length + k + 1).padStart(2, '0')}_extra`,
    frames: s.seconds || seconds, setup: s.setup }));
  return list.filter(s => !only || only.some(o => s.name.includes(o)));
}

async function record(shape) {
  const [w, h] = SHAPES[shape];
  if (!w) throw new Error(`unknown shape "${shape}": use wide or vertical`);
  const extraJs = 'window.__HEDGEFLY_VCLOCK__=0;window.__HEDGEFLY_VCLOCK_DRIVEN__=true;';
  const { html } = inlinePage(page, data, extraJs);
  const file = join(tmpdir(), `neonriso-record-${process.pid}-${shape}.html`);
  writeFileSync(file, html);
  const b = await launch(w, h);
  try {
    const loaded = b.once('Page.loadEventFired');
    await b.page('Page.navigate', { url: `file://${file}?record&clean${shape === 'vertical' ? '&vertical' : ''}` });
    await loaded;
    for (let k = 0; k < 200 && !(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++)
      await new Promise(r => setTimeout(r, 100));
    if (!(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')))
      throw new Error(`${page} never reported __hedgefly.ready - check its data loaded (see SKILL.md)`);

    const rooms = await b.evaluate('__hedgefly.rooms()');
    const extra = await b.evaluate('__hedgefly.shots?__hedgefly.shots():null');
    const ffmpeg = findFfmpeg();
    for (const shot of shotList(rooms, extra)) {
      const dir = join(out, shape, shot.name);
      rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
      await b.evaluate(shot.setup);
      const n = Math.round(shot.frames * fps);

      // Playwright's ffmpeg reads only piped JPEGs, so the VP8 preview is fed a JPEG of every
      // frame while the lossless PNG frames go to disk for the edit.
      let pipe = null, piped = null;
      if (ffmpeg && !ffmpeg.h264) {
        const target = join(out, shape, `${shot.name}.webm`);
        pipe = spawn(ffmpeg.bin, ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-c:v', 'mjpeg',
          '-framerate', String(fps), '-i', 'pipe:0', '-an', '-c:v', 'libvpx', '-b:v', '10M', target],
          { stdio: ['pipe', 'ignore', 'pipe'] });
        let err = ''; pipe.stderr.on('data', d => { err += d; });
        piped = new Promise(ok => pipe.on('exit', c => ok(c === 0 ? target : `(preview failed: ${err.trim().split('\n')[0]})`)));
      }
      for (let f = 0; f < n; f++) {
        await b.evaluate(`__hedgefly.step(${(1000 / fps).toFixed(4)})`);
        const { data: png } = await b.page('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(dir, `frame_${String(f + 1).padStart(5, '0')}.png`), Buffer.from(png, 'base64'));
        if (pipe) {
          const { data: jpg } = await b.page('Page.captureScreenshot', { format: 'jpeg', quality: 92 });
          await new Promise(ok => pipe.stdin.write(Buffer.from(jpg, 'base64'), ok));
        }
      }
      let video = '';
      if (pipe) { pipe.stdin.end(); video = await piped; }
      else if (ffmpeg) {
        const target = join(out, shape, `${shot.name}.${ffmpeg.h264 ? 'mp4' : 'webm'}`);
        const codec = ffmpeg.h264 ? ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18']
                                  : ['-c:v', 'libvpx', '-b:v', '12M'];
        try {
          execFileSync(ffmpeg.bin, ['-y', '-loglevel', 'error', '-framerate', String(fps),
            '-i', join(dir, 'frame_%05d.png'), ...codec, target]);
          video = target;
        } catch (e) { video = `(encoding failed: ${String(e.message).split('\n')[0]})`; }
      }
      console.log(`  ${shape} ${shot.name}: ${n} frames${video ? ', ' + video : ''}`);
    }
    return ffmpeg;
  } finally {
    b.ws.close(); b.chrome.kill('SIGKILL'); rmSync(file, { force: true });
  }
}

console.log(`recording ${page} (${data}): ${shapes.join(' + ')} at ${fps} fps into ${out}`);
let ffmpeg = null;
for (const shape of shapes) ffmpeg = await record(shape);
if (!ffmpeg || !ffmpeg.h264) {
  console.log(`\nNo H.264 encoder here${ffmpeg ? ' (only VP8: .webm previews were written)' : ''}.`);
  console.log(`For mp4, install ffmpeg, or copy the frames to a machine that has it and run, in each shot folder:`);
  console.log(`  ffmpeg -framerate ${fps} -i frame_%05d.png -c:v libx264 -pix_fmt yuv420p -crf 18 shot.mp4`);
  console.log('On Windows (PowerShell), every shot at once, from the film folder:');
  console.log(`  Get-ChildItem -Directory -Recurse | Where-Object { Test-Path "$($_.FullName)\\frame_00001.png" } | ForEach-Object { ffmpeg -y -framerate ${fps} -i "$($_.FullName)\\frame_%05d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 "$($_.FullName).mp4" }`);
}
