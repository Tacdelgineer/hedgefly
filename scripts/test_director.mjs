#!/usr/bin/env node
/* Press every director-mode key in the single-file build and check what each one did.
 *
 *     node scripts/test_director.mjs
 *     node scripts/test_director.mjs --file visuals/dist/hedgefly.html
 *
 * Director mode is for recording by hand, and the build it has to work in is the standalone
 * one - the file that gets opened by double-click and published. Reading the source only proves
 * the code is in there, so this drives the real page in headless Chrome, presses the keys over
 * the DevTools protocol, and checks the camera, the generation pointer and the UI afterwards.
 *
 * Exits non-zero on the first thing that does not work, and names it. */
import { resolve } from 'node:path';
import { repo, launch } from './pagekit.mjs';

const arg = (n, d) => { const k = process.argv.indexOf(`--${n}`); return k > 0 ? process.argv[k + 1] : d; };
const url = 'file://' + resolve(repo, arg('file', 'visuals/dist/hedgefly.html'));
const b = await launch(1600, 900);
const fails = [];
const check = (name, ok, got) => { console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : '   got: ' + got}`); if (!ok) fails.push(name); };

try {
  const loaded = b.once('Page.loadEventFired');
  await b.page('Page.navigate', { url });
  await loaded;
  for (let k = 0; k < 100 && !(await b.evaluate('!!(window.__hedgefly&&window.__hedgefly.ready)')); k++)
    await new Promise(r => setTimeout(r, 100));

  const key = async (text, code, keyCode) => {
    for (const type of ['keyDown', 'keyUp'])
      await b.page('Input.dispatchKeyEvent', { type, key: text, code, windowsVirtualKeyCode: keyCode, text: type === 'keyDown' && text.length === 1 ? text : undefined });
    await new Promise(r => setTimeout(r, 90));
  };
  const cam = () => b.evaluate('JSON.stringify({x:Math.round(cam.x),y:Math.round(cam.y),z:+cam.zoom.toFixed(3),gen:GEN,play:PLAYING,rate:RATE,hidden:document.body.classList.contains("hidden-ui")})').then(JSON.parse);

  // the legend is on screen, and lists the keys
  const legend = await b.evaluate('document.getElementById("legend").textContent.length');
  check('legend rendered with key list', legend > 80, legend);

  // number keys jump to rooms
  await key('3', 'Digit3', 51);
  const a3 = await cam();
  await key('7', 'Digit7', 55);
  const a7 = await cam();
  check('number keys jump to different rooms', a3.x !== a7.x || a3.y !== a7.y, `${JSON.stringify(a3)} vs ${JSON.stringify(a7)}`);

  // arrows pan. Measure camBase, not cam: cam carries the idle drift on top of it. Let any
  // room tween from the step above land first, so the pan is not measured mid-flight.
  await new Promise(r => setTimeout(r, 900));
  const base = () => b.evaluate('JSON.stringify({x:Math.round(camBase.x),y:Math.round(camBase.y),z:+camBase.zoom.toFixed(3)})').then(JSON.parse);
  const before = await base();
  await key('ArrowRight', 'ArrowRight', 39);
  const after = await base();
  check('arrow key pans', after.x > before.x, `${before.x} -> ${after.x}`);

  // +/- zoom
  const z0 = (await base()).z;
  await key('+', 'Equal', 187);
  const z1 = (await base()).z;
  await key('-', 'Minus', 189);
  const z2 = (await base()).z;
  check('+ zooms in', z1 > z0, `${z0} -> ${z1}`);
  check('- zooms out', z2 < z1, `${z1} -> ${z2}`);

  // [ ] step generations
  await b.evaluate('__hedgefly.gen(5)');
  await key(']', 'BracketRight', 221);
  const g1 = (await cam()).gen;
  await key('[', 'BracketLeft', 219);
  const g2 = (await cam()).gen;
  check('] steps a generation on', g1 === 6, g1);
  check('[ steps a generation back', g2 === 5, g2);

  // space plays / pauses
  const p0 = (await cam()).play;
  await key(' ', 'Space', 32);
  const p1 = (await cam()).play;
  check('space toggles play', p1 !== p0, `${p0} -> ${p1}`);

  // shift held = slow motion
  await b.page('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Shift', code: 'ShiftLeft', windowsVirtualKeyCode: 16 });
  await new Promise(r => setTimeout(r, 80));
  const rHeld = (await cam()).rate;
  await b.page('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Shift', code: 'ShiftLeft', windowsVirtualKeyCode: 16 });
  await new Promise(r => setTimeout(r, 80));
  const rFree = (await cam()).rate;
  check('holding shift slows the clock', rHeld === 0.25 && rFree === 1, `held ${rHeld}, released ${rFree}`);

  // h hides everything
  await key('h', 'KeyH', 72);
  const h1 = await cam();
  await key('h', 'KeyH', 72);
  const h2 = await cam();
  check('h hides the ui and the legend', h1.hidden === true && h2.hidden === false, `${h1.hidden} -> ${h2.hidden}`);
  const legendHiddenRule = await b.evaluate(`(()=>{const el=document.getElementById('legend');document.body.classList.add('hidden-ui');const v=getComputedStyle(el).display;document.body.classList.remove('hidden-ui');return v})()`);
  check('legend is hidden by h too', legendHiddenRule === 'none', legendHiddenRule);

  // , and . walk the rooms
  await key('1', 'Digit1', 49);
  const c0 = await cam();
  await key('.', 'Period', 190);
  const c1 = await cam();
  check('. moves to the next room', c0.x !== c1.x || c0.y !== c1.y, `${JSON.stringify(c0)} vs ${JSON.stringify(c1)}`);

  // f asks for fullscreen (headless refuses it; what matters is that it is wired and does not throw)
  const errs = await b.evaluate('window.__err||0');
  await key('f', 'KeyF', 70);
  check('f does not throw', (await b.evaluate('window.__err||0')) === errs, 'threw');

  // the room count the legend advertises matches the rooms that exist
  const n = await b.evaluate('__hedgefly.rooms().length');
  const advertised = await b.evaluate(`/all (\\d+)/.exec(document.getElementById('legend').textContent)?.[1]`);
  check('legend room count matches the world', String(n) === String(advertised), `${advertised} vs ${n}`);
  console.log(`\n${fails.length ? fails.length + ' FAILED: ' + fails.join(', ') : 'all director-mode keys work in the single-file build'}`);
} finally {
  b.ws.close(); b.chrome.kill('SIGKILL');
}
process.exit(fails.length ? 1 : 0);
