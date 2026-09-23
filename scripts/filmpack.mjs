#!/usr/bin/env node
/* Render the film pack: neon riso charts for the edit, 3840x2160 PNGs in results/filmpack/.
 *
 *     node scripts/filmpack.mjs                       # every chart
 *     node scripts/filmpack.mjs --only fitness,overfit --size 1920x1080
 *
 * Each chart is visuals/filmpack/?chart=<name> drawn from visuals/hq/runs.json, the export of
 * the logs (PLAN.md rule 8); a chart whose data has not landed renders as a "pending" card. No
 * server: the page, its core and the data are inlined into one temporary file. */
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { repo, inlinePage, findChrome } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const CHARTS = ['fitness', 'trades', 'overfit', 'finale', 'finale_curves'];
const only = arg('only', CHARTS.join(',')).split(',');
const [w, h] = arg('size', '3840x2160').split('x').map(Number);
const out = resolve(repo, arg('out', 'results/filmpack'));
mkdirSync(out, { recursive: true });

const { run, html } = inlinePage('visuals/filmpack/index.html', arg('data', 'visuals/hq/runs.json'));
const page = join(tmpdir(), `hedgefly-filmpack-${process.pid}.html`);
writeFileSync(page, html);
const chrome = findChrome();
console.log(`run ${run.run_id}${run.finale ? `, finale from ${run.finale.run}` : ''}; ${w}x${h}; chrome ${chrome}`);
for (const name of only) {
  const png = join(out, `${name}.png`);
  execFileSync(chrome, ['--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars', '--allow-file-access-from-files',
    `--window-size=${w},${h}`, '--virtual-time-budget=15000', `--screenshot=${png}`, `file://${page}?chart=${name}`],
    { stdio: ['ignore', 'ignore', 'ignore'], timeout: 180_000 });
  console.log(`  ${png}`);
}
rmSync(page, { force: true });
