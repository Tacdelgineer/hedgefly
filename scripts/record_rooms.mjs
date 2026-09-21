#!/usr/bin/env node
/* One shot per new room, and no two shots that move the same way.
 *
 *     node scripts/record_rooms.mjs                          # everything, wide and vertical
 *     node scripts/record_rooms.mjs --shapes wide --only eye,toll
 *
 * record_hq.mjs films each room as it stands and record_extra.mjs drives the story; this one
 * is about the camera. Eight rooms, eight moves - orbit, time-lapse, macro, slow push,
 * top-down, crane, track, pan - so a cut between any two does not repeat itself.
 *
 * The projection is a fixed isometric, so a move is a path through (x, y, zoom): an "orbit" is
 * a circle around a room's centre, "top-down" is a high wide framing of its floor. Everything
 * on screen still comes from visuals/hq/runs.json (PLAN.md rule 8); these shots only choose
 * where the camera is and which logged generation is on.
 *
 * Output: results/film2/<shape>/<shot>/frame_00001.png ..., plus <shot>.mp4 where this machine
 * has an ffmpeg that can write H.264. */
import { execFileSync } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { repo, inlinePage, findFfmpeg, launch } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const SHAPES = { wide: [1920, 1080], vertical: [1080, 1920] };
const shapes = arg('shapes', 'wide,vertical').split(',');
const fps = +arg('fps', 30);
const only = arg('only', null)?.split(',');
const out = resolve(repo, arg('out', 'results/film2'));
const MS = (1000 / fps).toFixed(4);
const PAGE = 'visuals/hq2/index.html';

const ease = u => (u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;
const TAU = Math.PI * 2;

/* ---- the shots: room, move, length ------------------------------------------------------- */
function shotList({ generations, frame, spot }) {
  const secs = n => Math.round(n * fps);
  const last = generations - 1;
  const still = g => `__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.gen(${g})`;
  const cam = c => `__hedgefly.cam(${c.x.toFixed(2)},${c.y.toFixed(2)},${c.zoom.toFixed(4)})`;
  const list = [];

  /* 1. ORBIT - a circle around the street, the camera never changing height */
  {
    const a = frame.street, r = 210;
    list.push({ name: '30_street_orbit', frames: secs(16), setup: still(last),
      at: (f, n) => { const A = (f / n) * TAU;
        return cam({ x: a.x + Math.cos(A) * r, y: a.y + Math.sin(A) * r * .42, zoom: a.zoom * 1.5 }); } });
  }

  /* 2. TIME-LAPSE - the server room still, the whole run running through it */
  {
    const a = frame.server;
    list.push({ name: '31_server_timelapse', frames: secs(12),
      setup: `__hedgefly.play(false);__hedgefly.sel(1);${cam({ x: a.x, y: a.y, zoom: a.zoom * 1.18 })}`,
      at: (f, n) => `__hedgefly.gen(${Math.min(last, Math.floor(f / (n * .92) * generations))})` });
  }

  /* 3. MACRO - right down onto the eye's facets, and back off a little */
  {
    const a = frame.eye, eye = spot.eye;
    list.push({ name: '32_eye_macro', frames: secs(13), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(a.x, eye.x, .95), y: lerp(a.y, eye.y, .95),
                     zoom: a.zoom * lerp(1.2, 4.4, Math.sin(u * Math.PI) * .85 + u * .15) }); } });
  }

  /* 4. SLOW PUSH - one move, from the whole switchboard to the dials that flicker */
  {
    const a = frame.switchboard, panel = spot.switchboard;
    list.push({ name: '33_switchboard_push', frames: secs(15), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(a.x, panel.x, u * .8), y: lerp(a.y, panel.y, u * .8),
                     zoom: a.zoom * lerp(1, 2.6, u) }); } });
  }

  /* 5. TOP-DOWN - high and square over the toll booth's floor, drifting across the coins */
  {
    const a = frame.toll;
    list.push({ name: '34_toll_topdown', frames: secs(12), setup: still(last),
      at: (f, n) => { const u = f / (n - 1);
        return cam({ x: a.x - 90 + u * 180, y: a.y - 40, zoom: a.zoom * 1.62 }); } });
  }

  /* 6. CRANE - the boardroom from high and wide down to the table and its fallen chairs */
  {
    const a = frame.boardroom, table = spot.boardroom;
    list.push({ name: '35_boardroom_crane', frames: secs(14), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(a.x, table.x, u * .9), y: lerp(a.y - 120, table.y, u),
                     zoom: a.zoom * lerp(.92, 2.15, u) }); } });
  }

  /* 7. TRACK - straight along the corridor at a fixed distance, the way it is walked */
  {
    const a = frame.corridor, l = spot.corridor_a, r = spot.corridor_b;
    list.push({ name: '36_corridor_track', frames: secs(18), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(l.x, r.x, u), y: lerp(l.y, r.y, u) - 10, zoom: a.zoom * 2.3 }); } });
  }

  /* 8. PAN - across the lineage, oldest portrait to the living one, at one height */
  {
    const a = frame.gallery, l = spot.gallery_a, r = spot.gallery_b;
    list.push({ name: '37_gallery_pan', frames: secs(14), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(l.x, r.x, u), y: lerp(l.y, r.y, u), zoom: a.zoom * 2.05 }); } });
  }

  return list.filter(s => !only || only.some(o => s.name.includes(o)));
}

/* ---- recording ---------------------------------------------------------------------------- */
async function plan(b) {
  const generations = await b.evaluate('__hedgefly.generations()');
  const frame = {}, spot = {};
  for (const id of ['street', 'server', 'eye', 'switchboard', 'toll', 'boardroom', 'corridor', 'gallery'])
    frame[id] = await b.evaluate(`__hedgefly.frame('${id}')`);
  spot.eye = await b.evaluate("__hedgefly.spot('eye',3.9,3.1,1.9)");
  spot.switchboard = await b.evaluate("__hedgefly.spot('switchboard',4,0.2,1.6)");
  spot.boardroom = await b.evaluate("__hedgefly.spot('boardroom',4.5,3.6,0.8)");
  spot.corridor_a = await b.evaluate("__hedgefly.spot('corridor',1.6,2.5,1)");
  spot.corridor_b = await b.evaluate("__hedgefly.spot('corridor',10.6,2.5,1)");
  spot.gallery_a = await b.evaluate("__hedgefly.spot('gallery',1,0.2,1.5)");
  spot.gallery_b = await b.evaluate("__hedgefly.spot('gallery',7.4,0.2,1.5)");
  return { generations, frame, spot };
}

async function record(shape) {
  const [w, h] = SHAPES[shape];
  const extra = 'window.__HEDGEFLY_VCLOCK__=0;window.__HEDGEFLY_VCLOCK_DRIVEN__=true;';
  const { html } = inlinePage(PAGE, arg('data', 'visuals/hq/runs.json'), extra);
  const file = join(tmpdir(), `hedgefly-rooms-${process.pid}-${shape}.html`);
  writeFileSync(file, html);
  const b = await launch(w, h);
  try {
    const loaded = b.once('Page.loadEventFired');
    await b.page('Page.navigate', { url: `file://${file}?record&clean${shape === 'vertical' ? '&vertical' : ''}` });
    await loaded;
    for (let k = 0; k < 200 && !(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++)
      await new Promise(r => setTimeout(r, 100));
    const ffmpeg = findFfmpeg();
    for (const shot of shotList(await plan(b))) {
      const dir = join(out, shape, shot.name);
      rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
      await b.evaluate(shot.setup);
      const n = shot.frames;
      for (let f = 0; f < n; f++) {
        const drive = shot.at(f, n);
        if (drive) await b.evaluate(drive);
        await b.evaluate(`__hedgefly.step(${MS})`);
        const { data } = await b.page('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(dir, `frame_${String(f + 1).padStart(5, '0')}.png`), Buffer.from(data, 'base64'));
      }
      let video = '';
      if (ffmpeg) {
        const target = join(out, shape, `${shot.name}.${ffmpeg.h264 ? 'mp4' : 'webm'}`);
        const codec = ffmpeg.h264 ? ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18']
                                  : ['-c:v', 'libvpx', '-b:v', '12M'];
        try { execFileSync(ffmpeg.bin, ['-y', '-loglevel', 'error', '-framerate', String(fps),
              '-i', join(dir, 'frame_%05d.png'), ...codec, target]); video = target; }
        catch (e) { video = `(encoding failed: ${String(e.message).split('\n')[0]})`; }
      }
      console.log(`  ${shape} ${shot.name}: ${n} frames (${(n / fps).toFixed(1)} s)${video ? ', ' + video : ''}`);
    }
    return ffmpeg;
  } finally {
    b.ws.close(); b.chrome.kill('SIGKILL'); rmSync(file, { force: true });
  }
}

const t0 = Date.now();
console.log(`recording the new rooms: ${shapes.join(' + ')} at ${fps} fps into ${out}`);
let ffmpeg = null;
for (const shape of shapes) ffmpeg = await record(shape);
console.log(`\ndone in ${((Date.now() - t0) / 60000).toFixed(1)} min`);
if (!ffmpeg || !ffmpeg.h264) console.log('No H.264 encoder here; frames written, encode elsewhere.');
