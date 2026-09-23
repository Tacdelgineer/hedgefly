#!/usr/bin/env node
/* Render the poster card of every generation to PNG, wide and vertical.
 *
 *     node scripts/render_posters.mjs                          # into results/posters/<shape>/
 *     node scripts/render_posters.mjs --shapes wide --out results/posters
 *
 * The cards are visuals/posters/index.html over the same runs.json every other visual reads, so
 * each headline is the narrator's where it passed the Fact Guard (headlineFor) and every number
 * on a card is read out of the logs (PLAN.md rule 8). The Archive room hangs the same cards. */
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { repo, inlinePage, launch } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const SHAPES = { wide: [1920, 1080], vertical: [1080, 1920] };
const shapes = arg('shapes', 'wide,vertical').split(',');
const out = resolve(repo, arg('out', 'results/posters'));
const { run, html } = inlinePage('visuals/posters/index.html', arg('data', 'visuals/hq/runs.json'));
const file = join(tmpdir(), `hedgefly-posters-${process.pid}.html`);
writeFileSync(file, html);

try {
  for (const shape of shapes) {
    const [w, h] = SHAPES[shape], dir = join(out, shape);
    mkdirSync(dir, { recursive: true });
    const b = await launch(w, h);
    try {
      for (let g = 0; g < run.generations; g++) {
        const loaded = b.once('Page.loadEventFired');
        await b.page('Page.navigate', { url: `file://${file}?gen=${g}` });
        await loaded;
        for (let k = 0; k < 100 && !(await b.evaluate("document.body.dataset.ready==='1'")); k++) await new Promise(r => setTimeout(r, 50));
        const title = await b.evaluate('document.title');
        const { data } = await b.page('Page.captureScreenshot', { format: 'png' });
        const target = join(dir, `gen_${String(g).padStart(2, '0')}.png`);
        writeFileSync(target, Buffer.from(data, 'base64'));
        console.log(`  ${shape} ${target.replace(repo + '/', '')}  ${title.replace(/^Hedgefly · /, '')}`);
      }
    } finally { b.ws.close(); b.chrome.kill('SIGKILL'); }
  }
} finally { rmSync(file, { force: true }); }
