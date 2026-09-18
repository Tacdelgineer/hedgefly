/* Shared by the headless tools: find a Chrome, and turn a served page into one self-contained file.
 *
 * A page under visuals/ loads ../lib/neon-riso.js and fetches ../hq/runs.json. inlinePage() puts
 * both inside the page, so it can be opened from a temporary file with no server - which is what an
 * unattended job wants. Every "<" inside inlined data is written as < so nothing inlined can
 * close a script block early. */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

export const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const LIB = /<!--NEON-RISO-->[\s\S]*?<!--\/NEON-RISO-->/;

export function inlinePage(pagePath, dataPath = 'visuals/hq/runs.json', extra = '') {
  let page = readFileSync(resolve(repo, pagePath), 'utf8');
  const lib = readFileSync(resolve(repo, 'visuals/lib/neon-riso.js'), 'utf8');
  const run = JSON.parse(readFileSync(resolve(repo, dataPath), 'utf8'));
  if (!LIB.test(page)) throw new Error(`${pagePath} has no <!--NEON-RISO--> block to inline`);
  if (/<\/script/i.test(lib)) throw new Error('the neon riso core contains a closing script tag');
  const data = JSON.stringify(run).replace(/</g, '\\u003c');
  return { run, html: page.replace(LIB, () => `<script>window.__HEDGEFLY_RUN__=${data};${extra}</script>\n<script>\n${lib}\n</script>`) };
}

/* A headless Chrome: $HEDGEFLY_CHROME, else the newest Playwright headless shell, else PATH. */
export function findChrome() {
  if (process.env.HEDGEFLY_CHROME) return process.env.HEDGEFLY_CHROME;
  const cache = join(homedir(), '.cache', 'ms-playwright');
  if (existsSync(cache)) {
    const shells = readdirSync(cache).filter(d => d.startsWith('chromium_headless_shell-')).sort().reverse();
    for (const d of shells) for (const sub of readdirSync(join(cache, d))) {
      const bin = join(cache, d, sub, 'chrome-headless-shell');
      if (existsSync(bin)) return bin;
    }
  }
  return 'chromium';
}
