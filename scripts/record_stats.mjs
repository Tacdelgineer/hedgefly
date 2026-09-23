#!/usr/bin/env node
/* Record the finale's stat cards (visuals/statcards/) to H.264 mp4, wide and vertical.
 *
 *     node scripts/record_stats.mjs                              # all seven, into results/film-stats
 *     node scripts/record_stats.mjs --only S1,S7 --shapes wide --seconds 6
 *
 * Each card counts its number up and then holds it. The page reads runs.json's finale block,
 * copied by scripts/export_for_visuals.py from runs/<run>/finale.json, so every figure on a card
 * is a logged one (PLAN.md rule 8). The clock is stepped one frame at a time, as in the other
 * recorders, and the frames go straight into ffmpeg; the last frame of each card is also kept
 * as a PNG beside its mp4. Needs an ffmpeg with libx264 ($HEDGEFLY_FFMPEG or PATH). */
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { repo, inlinePage, findFfmpeg, launch } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const SHAPES = { wide: [1920, 1080], vertical: [1080, 1920] };
const NAMES = { S1: 'S1_real_vs_buy_and_hold', S2: 'S2_real_vs_scrambled', S3: 'S3_trades',
                S4: 'S4_momentum_and_random', S5: 'S5_local_ai', S6: 'S6_no_fees', S7: 'S7_end_card' };
const shapes = arg('shapes', 'wide,vertical').split(',');
const only = arg('only', null)?.split(',');
const fps = +arg('fps', 30), seconds = +arg('seconds', 6);
const out = resolve(repo, arg('out', 'results/film-stats'));
const ffmpeg = findFfmpeg();
if (!ffmpeg || !ffmpeg.h264) throw new Error('no ffmpeg with libx264: set $HEDGEFLY_FFMPEG');

const extra = 'window.__HEDGEFLY_VCLOCK__=0;window.__HEDGEFLY_VCLOCK_DRIVEN__=true;';
const { html } = inlinePage('visuals/statcards/index.html', arg('data', 'visuals/hq/runs.json'), extra);
const file = join(tmpdir(), `hedgefly-stats-${process.pid}.html`);
writeFileSync(file, html);

try {
  for (const shape of shapes) {
    const [w, h] = SHAPES[shape], dir = join(out, shape);
    mkdirSync(dir, { recursive: true });
    const b = await launch(w, h);
    try {
      const loaded = b.once('Page.loadEventFired');
      await b.page('Page.navigate', { url: `file://${file}?record${shape === 'vertical' ? '&vertical' : ''}` });
      await loaded;
      for (let k = 0; k < 200 && !(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++) await new Promise(r => setTimeout(r, 100));
      const cards = (await b.evaluate('__hedgefly.cards()')).filter(c => !only || only.includes(c));
      for (const card of cards) {
        await b.evaluate(`__hedgefly.card('${card}')`);
        const target = join(dir, `${NAMES[card] || card}.mp4`), n = Math.round(seconds * fps);
        const enc = spawn(ffmpeg.bin, ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-c:v', 'png', '-framerate', String(fps), '-i', 'pipe:0',
          '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-r', String(fps), '-movflags', '+faststart', target],
          { stdio: ['pipe', 'ignore', 'pipe'] });
        let err = ''; enc.stderr.on('data', d => { err += d; });
        const done = new Promise((ok, fail) => enc.on('exit', c => c === 0 ? ok() : fail(new Error(`ffmpeg: ${err.trim()}`))));
        let last = null;
        for (let f = 0; f < n; f++) {
          await b.evaluate(`__hedgefly.step(${(1000 / fps).toFixed(4)})`);
          const { data } = await b.page('Page.captureScreenshot', { format: 'png' });
          last = Buffer.from(data, 'base64');
          await new Promise(ok => enc.stdin.write(last, ok));
        }
        enc.stdin.end(); await done;
        writeFileSync(target.replace(/\.mp4$/, '.png'), last);
        console.log(`  ${shape} ${card}: ${n} frames -> ${target.replace(repo + '/', '')}`);
      }
    } finally { b.ws.close(); b.chrome.kill('SIGKILL'); }
  }
} finally { rmSync(file, { force: true }); }
