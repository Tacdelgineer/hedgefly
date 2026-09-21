#!/usr/bin/env node
/* Draw every room and every view once, and fail on the first thing that throws.
 *
 *     node scripts/smoke_rooms.mjs [--file visuals/dist/hedgefly.html]
 *
 * A room that throws is caught per room in draw(), so the page keeps running and the room
 * simply comes out empty - which is easy to miss in a 12-minute recording and impossible to
 * miss here. This drives the real standalone build in headless Chrome, steps the virtual clock
 * through each room and each point of view, and reports anything Chrome logged. */
import { resolve } from 'node:path';
import { repo, launch } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const url = 'file://' + resolve(repo, arg('file', 'visuals/dist/hedgefly.html')) + '?record';
const b = await launch(1600, 900);
const errors = [];
let fails = 0;

try {
  const loaded = b.once('Page.loadEventFired');
  await b.page('Page.navigate', { url });
  await loaded;
  for (let k = 0; k < 150 && !(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++)
    await new Promise(r => setTimeout(r, 100));

  // Every room's draw() is wrapped in a try, so errors land in console.error rather than here.
  // Count them in the page instead, by wrapping console.error before anything is drawn.
  await b.evaluate('window.__errs=[];const _e=console.error;console.error=function(){window.__errs.push([...arguments].map(String).join(" "));_e.apply(console,arguments)};1');

  const rooms = JSON.parse(await b.evaluate('JSON.stringify(window.__hedgefly.rooms())'));
  const views = JSON.parse(await b.evaluate('JSON.stringify(window.__hedgefly.views?window.__hedgefly.views():["rooms"])'));
  const gens = +(await b.evaluate('window.__hedgefly.generations()'));

  for (const room of rooms) {
    await b.evaluate(`window.__hedgefly.shot('room',${JSON.stringify(room)},0)`);
    for (let f = 0; f < 6; f++) await b.evaluate('window.__hedgefly.step(83.3333)');
    const errs = JSON.parse(await b.evaluate('JSON.stringify(window.__errs)'));
    const mine = errs.filter(e => e.includes(room));
    console.log(`  ${mine.length ? 'FAIL' : 'ok  '} room ${room}${mine.length ? '   ' + mine[0] : ''}`);
    if (mine.length) fails++;
    await b.evaluate('window.__errs=[]');
  }

  // each generation drawn once, in the room that changes most between them
  await b.evaluate("window.__hedgefly.shot('room','tree',0)");
  for (let g = 0; g < gens; g++) {
    await b.evaluate(`window.__hedgefly.gen(${g})`);
    await b.evaluate('window.__hedgefly.step(83.3333)');
  }
  let errs = JSON.parse(await b.evaluate('JSON.stringify(window.__errs)'));
  console.log(`  ${errs.length ? 'FAIL' : 'ok  '} ${gens} generations drawn${errs.length ? '   ' + errs[0] : ''}`);
  if (errs.length) fails++;
  await b.evaluate('window.__errs=[]');

  for (const view of views) {
    await b.evaluate(`window.__hedgefly.view(${JSON.stringify(view)},0)`);
    for (let f = 0; f < 6; f++) await b.evaluate('window.__hedgefly.step(83.3333)');
    errs = JSON.parse(await b.evaluate('JSON.stringify(window.__errs)'));
    console.log(`  ${errs.length ? 'FAIL' : 'ok  '} view ${view}${errs.length ? '   ' + errs[0] : ''}`);
    if (errs.length) fails++;
    await b.evaluate('window.__errs=[]');
  }
  await b.evaluate("window.__hedgefly.view('rooms',0);window.__hedgefly.daylight(true)");
  for (let f = 0; f < 6; f++) await b.evaluate('window.__hedgefly.step(83.3333)');
  errs = JSON.parse(await b.evaluate('JSON.stringify(window.__errs)'));
  console.log(`  ${errs.length ? 'FAIL' : 'ok  '} daylight wash${errs.length ? '   ' + errs[0] : ''}`);
  if (errs.length) fails++;
} finally {
  b.ws.close(); b.chrome.kill('SIGKILL');
}
console.log(fails ? `\n${fails} thing(s) threw while drawing` : '\nevery room and view drew clean');
process.exit(fails ? 1 : 0);
