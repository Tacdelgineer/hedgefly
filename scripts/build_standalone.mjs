#!/usr/bin/env node
/* Build visuals/dist/hedgefly.html: the whole HQ in one file that opens by double-click.
 *
 *     node scripts/build_standalone.mjs
 *     node scripts/build_standalone.mjs --data visuals/hq/runs.json --out visuals/dist/hedgefly.html
 *
 * No server, no network, no dependencies. It takes visuals/hq2/index.html, inlines the neon
 * riso core it loads, inlines the run data it would have fetched, and carries the fly terminal
 * along as a string for the optional inset. Every "<" inside an inlined string is written as
 * <, so nothing inlined can ever close a script block early.
 *
 * The data is the same runs.json the served pages read (visuals/hq/data-contract.md, v2), so
 * the file shows exactly the numbers the logs hold (PLAN.md rule 8). */
import { readFileSync, writeFileSync, mkdirSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { hostname, userInfo } from 'node:os';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (name, fallback) => { const k = process.argv.indexOf(`--${name}`); return k > 0 ? process.argv[k + 1] : fallback; };
const dataPath = resolve(repo, arg('data', 'visuals/hq/runs.json'));
const outPath = resolve(repo, arg('out', 'visuals/dist/hedgefly.html'));

const read = p => readFileSync(resolve(repo, p), 'utf8');
const LS = String.fromCharCode(0x2028), PS = String.fromCharCode(0x2029);   // JS line terminators inside JSON
const inlineString = s => JSON.stringify(s).replace(/</g, '\\u003c').split(LS).join('\\u2028').split(PS).join('\\u2029');

const run = JSON.parse(readFileSync(dataPath, 'utf8'));
if (run.contract_version !== 2) throw new Error(`${dataPath} is data contract v${run.contract_version || 1}; hq2 reads v2`);

const LIB = /<!--NEON-RISO-->[\s\S]*?<!--\/NEON-RISO-->/;
let page = read('visuals/hq2/index.html');
if (!LIB.test(page)) throw new Error('visuals/hq2/index.html has no <!--NEON-RISO--> block to inline');
const lib = read('visuals/lib/neon-riso.js');
if (/<\/script/i.test(lib)) throw new Error('the neon riso core contains a closing script tag');
const terminal = read('visuals/terminal/index.html');
if (!terminal.includes('<!--HEDGEFLY-DATA-->')) throw new Error('visuals/terminal/index.html lost its data marker');

const payload = `<script>
/* inlined by scripts/build_standalone.mjs from ${dataPath.replace(repo + '/', '')} */
window.__HEDGEFLY_RUN__=${JSON.stringify(run).replace(/</g, '\\u003c')};
window.__HEDGEFLY_TERMINAL__=${inlineString(terminal)};
</script>
<script>
${lib}
</script>`;
page = page.replace(LIB, () => payload)
           .replace('<title>Natural Selection Capital HQ</title>',
                    `<title>Natural Selection Capital HQ · ${run.run_id}${run.fake ? ' (fake data)' : ''}</title>`);

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, page);
const kb = (statSync(outPath).size / 1024).toFixed(0);
console.log(`${outPath}\n  ${run.generations} generation(s) of run ${run.run_id}${run.fake ? ' (FAKE DATA)' : ''}, ${kb} KB, no server needed`);
console.log(`\nTo copy it to a Windows machine, run this there (PowerShell; OpenSSH ships with Windows 10+):`);
console.log(`  scp ${userInfo().username}@${arg('host', hostname())}:${outPath} "$env:USERPROFILE\\Desktop\\hedgefly.html"`);
console.log(`then double-click hedgefly.html on the Desktop.`);
