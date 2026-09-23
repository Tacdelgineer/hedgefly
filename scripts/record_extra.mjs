#!/usr/bin/env node
/* The second reel: shots that move, cut from the same rooms and the same run data.
 *
 *     node scripts/record_extra.mjs                              # everything, wide and vertical
 *     node scripts/record_extra.mjs --shapes wide --only push,vault
 *
 * record_hq.mjs films each room as it stands. These shots drive the room instead: the camera
 * pushes in over a shot's whole length, generations advance on a beat the shot chooses, the
 * selection event runs at a quarter of its speed, and the vault door opens three times from
 * three framings. Every frame still comes from visuals/hq2/index.html and visuals/hq/runs.json,
 * so nothing here invents a number (PLAN.md rule 8); the title cards are the one exception and
 * they carry no numbers at all, only the film's own headings.
 *
 * A shot is {name, page, setup, frames, at(f, n, api)}: `setup` runs once, and `at` runs before
 * every frame with the frame index, the shot's length and a small helper for building
 * expressions. The HQ's clock is stepped by hand (?record, window.__hedgefly.step), so a
 * recording is exact and repeatable however slowly the capture runs.
 *
 * Output: results/film-extra/<shape>/<shot>/frame_00001.png ..., plus <shot>.mp4 when this
 * machine has an ffmpeg that can write H.264 (apt install ffmpeg). */
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
const out = resolve(repo, arg('out', 'results/film-extra'));
const MS = (1000 / fps).toFixed(4);

/* eased 0..1 across a shot, so a move starts and ends at rest instead of snapping */
const ease = u => (u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const lerp = (a, b, t) => a + (b - a) * t;

/* ---- the shots ---------------------------------------------------------------------------
   `plan` is given the page's own answers (room framings, generation count, reply count) once,
   before recording, so a shot can be built out of the run rather than out of guesses. */
function shotList({ generations, replies, hasFinale, frame, spot }) {
  const list = [];
  const secs = n => Math.round(n * fps);

  /* 1. the hero's desk: one slow push, nothing else moving but the room */
  {
    const a = frame.hero, target = spot.hero_desk;
    list.push({ name: '20_hero_push', frames: secs(14),
      setup: `__hedgefly.play(false);__hedgefly.gen(${generations - 1});__hedgefly.sel(1)`,
      at: (f, n) => { const u = ease(f / (n - 1)), z = lerp(a.zoom, a.zoom * 2.35, u);
        return `__hedgefly.cam(${lerp(a.x, target.x, u * .82).toFixed(2)},${lerp(a.y, target.y, u * .82).toFixed(2)},${z.toFixed(4)})`; } });
  }

  /* 2. the pile: every generation of eliminations, one unbroken take, camera still */
  {
    const a = frame.pile;
    list.push({ name: '21_pile_fills', frames: secs(generations * 1.5),
      setup: `__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.cam(${a.x.toFixed(2)},${a.y.toFixed(2)},${(a.zoom * 1.06).toFixed(4)})`,
      at: (f, n) => `__hedgefly.gen(${Math.min(generations - 1, Math.floor(f / n * generations))})` });
  }

  /* 3. the selection event, at a quarter of the speed the HQ plays it */
  {
    const a = frame.floor;
    list.push({ name: '22_selection_quarter', frames: secs(12),
      setup: `__hedgefly.play(false);__hedgefly.gen(${Math.floor(generations / 2)});` +
             `__hedgefly.cam(${a.x.toFixed(2)},${a.y.toFixed(2)},${(a.zoom * 1.15).toFixed(4)})`,
      // the HQ runs SEL 0 -> 1 inside one generation; here it takes the whole shot
      at: (f, n) => `__hedgefly.sel(${Math.min(1, f / (n * .88)).toFixed(4)})` });
  }

  /* 4. the model's office: a 10-second loop through the replies the run logged */
  if (replies > 0) {
    const a = frame.model;
    list.push({ name: '23_model_replies', frames: secs(10), loop: true,
      setup: `__hedgefly.play(false);__hedgefly.gen(${generations - 1});__hedgefly.sel(1);` +
             `__hedgefly.cam(${a.x.toFixed(2)},${a.y.toFixed(2)},${(a.zoom * 1.3).toFixed(4)})`,
      // every reply in the log gets equal time, and the last frame lands back on the first
      at: (f, n) => `__hedgefly.reply(${Math.floor(f / n * replies) % replies})` });
  }

  /* 5. the vault door, opened three times from three framings */
  if (hasFinale) {
    const a = frame.vault, door = spot.vault_door, board = spot.vault_board;
    // the projection is a fixed isometric, so an "angle" here is a framing: how close, and on
    // what. The door swings out to the left as it opens, so its shot tracks left with it.
    const angles = [
      ['wide', () => ({ x: a.x, y: a.y, zoom: a.zoom * 1.02 })],
      ['door', u => ({ x: door.x - 46 - 64 * u, y: door.y + 6, zoom: a.zoom * lerp(1.7, 1.5, u) })],
      ['board', u => ({ x: board.x + 30, y: board.y - 4, zoom: a.zoom * lerp(1.35, 1.5, u) })],
    ];
    angles.forEach(([tag, at], k) => list.push({
      name: `24_vault_${k + 1}_${tag}`, frames: secs(8),
      setup: `__hedgefly.play(false);__hedgefly.gen(${generations - 1});__hedgefly.sel(1);__hedgefly.open(0)`,
      at: (f, n) => { const u = f / (n - 1), c = at(ease(u));
        return `__hedgefly.open(${Math.min(1, f / (n * .6)).toFixed(4)});` +
               `__hedgefly.cam(${c.x.toFixed(2)},${c.y.toFixed(2)},${c.zoom.toFixed(4)})`; } }));
  }

  /* 6. the overfit room: the two pairs of curves drawn one generation at a time */
  {
    const a = frame.overfit;
    list.push({ name: '25_overfit_draws', frames: secs(generations * 1.2),
      setup: `__hedgefly.play(false);__hedgefly.sel(1);__hedgefly.cam(${a.x.toFixed(2)},${a.y.toFixed(2)},${(a.zoom * 1.24).toFixed(4)})`,
      at: (f, n) => `__hedgefly.gen(${Math.min(generations - 1, Math.floor(f / (n * .9) * generations))})` });
  }

  /* 7. three title cards, from the cards page, same pen and inks as the rooms */
  for (const [k, card] of ['project', 'control', 'vault'].entries())
    list.push({ name: `26_title_${k + 1}_${card}`, page: 'visuals/titles/index.html',
      frames: secs(5), setup: `__hedgefly.card('${card}')`, at: () => null });

  return list.filter(s => !only || only.some(o => s.name.includes(o)));
}

/* ---- recording ---------------------------------------------------------------------------- */
async function open(browser, page, shape) {
  const extra = 'window.__HEDGEFLY_VCLOCK__=0;window.__HEDGEFLY_VCLOCK_DRIVEN__=true;';
  const { html } = inlinePage(page, arg('data', 'visuals/hq/runs.json'), extra);
  const file = join(tmpdir(), `hedgefly-extra-${process.pid}-${shape}-${page.replace(/\W/g, '')}.html`);
  writeFileSync(file, html);
  const loaded = browser.once('Page.loadEventFired');
  await browser.page('Page.navigate', { url: `file://${file}?record&clean${shape === 'vertical' ? '&vertical' : ''}` });
  await loaded;
  for (let k = 0; k < 200 && !(await browser.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++)
    await new Promise(r => setTimeout(r, 100));
  return file;
}

async function plan(browser) {
  const generations = await browser.evaluate('__hedgefly.generations()');
  const hasFinale = await browser.evaluate('__hedgefly.hasFinale()');
  const replies = await browser.evaluate('__hedgefly.replies?__hedgefly.replies():0');
  const frame = {}, spot = {};
  for (const id of ['hero', 'pile', 'floor', 'model', 'vault', 'overfit'])
    frame[id] = await browser.evaluate(`__hedgefly.frame('${id}')`);
  spot.hero_desk = await browser.evaluate("__hedgefly.spot('hero',3.4,3.2,1.2)");
  spot.vault_door = await browser.evaluate("__hedgefly.spot('vault',3.5,0.2,1.42)");
  spot.vault_board = await browser.evaluate("__hedgefly.spot('vault',3.5,0.2,1.4)");
  return { generations, hasFinale, replies, frame, spot };
}

async function record(shape) {
  const [w, h] = SHAPES[shape];
  const b = await launch(w, h);
  const files = [];
  try {
    files.push(await open(b, 'visuals/hq2/index.html', shape));
    const built = shotList(await plan(b));
    const ffmpeg = findFfmpeg();
    let current = 'visuals/hq2/index.html';
    for (const shot of built) {
      const page = shot.page || 'visuals/hq2/index.html';
      if (page !== current) { files.push(await open(b, page, shape)); current = page; }
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
    b.ws.close(); b.chrome.kill('SIGKILL');
    for (const f of files) rmSync(f, { force: true });
  }
}

console.log(`recording the second reel: ${shapes.join(' + ')} at ${fps} fps into ${out}`);
let ffmpeg = null;
for (const shape of shapes) ffmpeg = await record(shape);
if (!ffmpeg || !ffmpeg.h264)
  console.log('\nNo H.264 encoder here; frames were written and can be encoded elsewhere.');
