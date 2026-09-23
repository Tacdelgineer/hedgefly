#!/usr/bin/env node
/* One shot per new room, and one per new point of view.
 *
 *     node scripts/record_new.mjs                              # everything, wide and vertical
 *     node scripts/record_new.mjs --shapes wide --only tree,replay
 *
 * The five rooms the family tree, the barcode, the tape, the replay and the eye added, plus the
 * three ways of looking at the whole building: the blueprint plan, the dollhouse section, and
 * the night-to-day light that follows the generation. Each gets a move of its own, and no two
 * moves here are the same - climb, track, locked-off, push, dolly, drift, orbit, hold.
 *
 * Every number on screen still comes out of visuals/hq/runs.json (PLAN.md rule 8); a shot only
 * chooses where the camera is, which generation is on, and which view is open.
 *
 * Output: results/film3/<shape>/<shot>/frame_00001.png ..., plus <shot>.mp4 where this machine
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
const out = resolve(repo, arg('out', 'results/film3'));
const MS = (1000 / fps).toFixed(4);
const PAGE = 'visuals/hq2/index.html';

const ease = u => (u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;
const TAU = Math.PI * 2;

/* ---- the shots: room or view, move, length ------------------------------------------------ */
function shotList({ generations, frame, spot }) {
  const secs = n => Math.round(n * fps);
  const last = generations - 1;
  const still = g => `__hedgefly.view('rooms',0);__hedgefly.daylight(false);__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.gen(${g})`;
  const cam = c => `__hedgefly.cam(${c.x.toFixed(2)},${c.y.toFixed(2)},${c.zoom.toFixed(4)})`;
  const list = [];

  /* 1. CLIMB - up the tree of life as the generations it is made of arrive under the camera */
  {
    const a = frame.tree, top = spot.tree_top, foot = spot.tree_foot;
    list.push({ name: '40_tree_climb', frames: secs(16),
      setup: `${still(0)};${cam({ x: foot.x, y: foot.y, zoom: a.zoom * 1.9 })}`,
      at: (f, n) => { const u = f / (n - 1), e = ease(u);
        return `__hedgefly.gen(${Math.min(last, Math.floor(u * generations))});` +
          cam({ x: lerp(foot.x, top.x, e), y: lerp(foot.y, top.y, e), zoom: a.zoom * lerp(1.9, 1.15, e) }); } });
  }

  /* 2. TRACK - sideways across the barcode, one tribe's block to the other's, at one height */
  {
    const a = frame.barcode, l = spot.barcode_a, r = spot.barcode_b;
    list.push({ name: '41_barcode_track', frames: secs(14), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(l.x, r.x, u), y: lerp(l.y, r.y, u), zoom: a.zoom * 2.15 }); } });
  }

  /* 3. LOCKED OFF - the tape hall, camera nailed down; the only thing moving is the tape */
  {
    const a = frame.tape, wall = spot.tape_wall;
    list.push({ name: '42_tape_locked', frames: secs(15),
      setup: `${still(last)};${cam({ x: wall.x, y: wall.y, zoom: a.zoom * 2.0 })}`,
      at: () => null });
  }

  /* 4. PUSH - from both champions at once in to the vote that decided a bar */
  {
    const a = frame.replay, votes = spot.replay_votes;
    list.push({ name: '43_replay_push', frames: secs(16), setup: still(last),
      at: (f, n) => { const u = ease(f / (n - 1));
        return cam({ x: lerp(a.x, votes.x, u * .85), y: lerp(a.y, votes.y, u * .85),
                     zoom: a.zoom * lerp(1, 2.5, u) }); } });
  }

  /* 5. DOLLY - straight in on the compound eye, through the bars it recorded, and out again */
  {
    const a = frame.flyeye, eye = spot.flyeye;
    list.push({ name: '44_flyeye_dolly', frames: secs(14), setup: still(last),
      at: (f, n) => { const u = f / (n - 1), s = Math.sin(u * Math.PI);
        return cam({ x: lerp(a.x, eye.x, s * .92), y: lerp(a.y, eye.y, s * .92),
                     zoom: a.zoom * lerp(1.1, 3.6, s) }); } });
  }

  /* 6. DRIFT - across the blueprint, the way a plan is read: flat, slow, left to right */
  {
    list.push({ name: '45_blueprint_drift', frames: secs(14),
      setup: `__hedgefly.daylight(false);__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.gen(${last});__hedgefly.view('blueprint',0)`,
      at: (f, n) => { const u = ease(f / (n - 1)), a = frame.blueprint;
        return cam({ x: a.x + lerp(-a.span * .2, a.span * .2, u), y: a.y, zoom: a.zoom * 1.42 }); } });
  }

  /* 7. ORBIT - around the opened dollhouse, so the cut faces turn past the camera */
  {
    list.push({ name: '46_dollhouse_orbit', frames: secs(16),
      setup: `__hedgefly.daylight(false);__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.gen(${last});__hedgefly.view('dollhouse',0)`,
      at: (f, n) => { const A = (f / n) * TAU, a = frame.dollhouse, r = a.span * .13;
        return cam({ x: a.x + Math.cos(A) * r, y: a.y + Math.sin(A) * r * .4, zoom: a.zoom * 1.12 }); } });
  }

  /* 8. HOLD - the whole building, still, while the run carries it from night to day */
  {
    list.push({ name: '47_night_to_day', frames: secs(18),
      setup: `__hedgefly.view('rooms',0);__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.gen(0);` +
             `__hedgefly.daylight(true);` + cam({ x: frame.all.x, y: frame.all.y, zoom: frame.all.zoom * 1.0 }),
      at: (f, n) => `__hedgefly.gen(${Math.min(last, Math.floor(f / (n * .94) * generations))})` });
  }

  return list.filter(s => !only || only.some(o => s.name.includes(o)));
}

/* ---- recording ---------------------------------------------------------------------------- */
async function plan(b) {
  const generations = await b.evaluate('__hedgefly.generations()');
  const frame = {}, spot = {};
  for (const id of ['tree', 'barcode', 'tape', 'replay', 'flyeye'])
    frame[id] = await b.evaluate(`__hedgefly.frame('${id}')`);
  // the tree climbs: aim at its floor first and its crown last
  spot.tree_foot = await b.evaluate("__hedgefly.spot('tree',5.5,4.6,0.3)");
  spot.tree_top = await b.evaluate("__hedgefly.spot('tree',5.5,3.8,3.0)");
  // the barcode's two blocks live on the 'i' wall, which stands at j ~ 0
  spot.barcode_a = await b.evaluate("__hedgefly.spot('barcode',1.6,0.2,1.6)");
  spot.barcode_b = await b.evaluate("__hedgefly.spot('barcode',8.2,0.2,0.9)");
  spot.tape_wall = await b.evaluate("__hedgefly.spot('tape',4.6,0.2,1.2)");
  spot.replay_votes = await b.evaluate("__hedgefly.spot('replay',2.6,0.2,1.5)");
  spot.flyeye = await b.evaluate("__hedgefly.spot('flyeye',3.5,3.4,2.2)");
  // the two whole-building views have to be measured with that view OPEN: the dollhouse moves
  // every room, so its framing is not the framing of the building as it normally stands.
  for (const [key, view] of [['blueprint', 'blueprint'], ['dollhouse', 'dollhouse'], ['all', 'rooms']]) {
    await b.evaluate(`__hedgefly.view('${view}',0)`);
    frame[key] = JSON.parse(await b.evaluate(`(()=>{const B=buildingBounds();
      const f=framing(B);return JSON.stringify({x:f.x,y:f.y,zoom:f.zoom,span:B[2]-B[0]})})()`));
  }
  await b.evaluate("__hedgefly.view('rooms',0)");
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
console.log(`recording the new rooms and views: ${shapes.join(' + ')} at ${fps} fps into ${out}`);
let ffmpeg = null;
for (const shape of shapes) ffmpeg = await record(shape);
console.log(`\ndone in ${((Date.now() - t0) / 60000).toFixed(1)} min`);
if (!ffmpeg || !ffmpeg.h264) console.log('No H.264 encoder here; frames written, encode elsewhere.');
