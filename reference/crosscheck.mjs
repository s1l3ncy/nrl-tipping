#!/usr/bin/env node
/* crosscheck.mjs — the in-page exact finals DP vs the Python reference solver.
 *
 * Boots nrl-tipping-guide.html in jsdom with the committed data files (or an
 * alternative nrl_comp.js via COMPFILE=) and prints P(Brigitte 1st) for every
 * Round 28 tip vector, next to reference_finals_solver.py's published numbers.
 *
 * The two are NOT expected to agree exactly, and the differences are known:
 *   - RIVAL MODEL. The Python solver fits ONE global logistic with no intercept
 *     over R24-R27 (a ~4.5 weight on the market/form logit), so its rivals are
 *     strongly market-following and therefore accurate. The page evaluates a
 *     PER-MEMBER intercept model fitted by cloud_fetch.py over the whole season
 *     with a leave-one-out, shrunk loyalty covariate, which leaves each rival a
 *     bit more loyalty-driven and so a bit less accurate. Less accurate rivals
 *     means a uniformly higher P(1st) for her — which is exactly the ~+2.5pt
 *     level shift seen across all eight lines.
 *   - It also moves ONE ordering: Claire sits at ~66% on the Sharks under the
 *     page's fit versus ~88% under the reference's, so the CRO-NQL split is
 *     worth less here and NZW/NQL/PEN and NZW/CRO/PEN swap 2nd and 3rd. They
 *     are 0.9pt apart in the reference and 1.2pt apart here — a coin-toss
 *     either way, and it does not touch the recommendation.
 *   - HOME EDGE. The page uses the LEARNED homeAdv (0 points this season); the
 *     reference hard-codes 2. Worth about -0.6pt (reference sensitivity §7).
 *   - COUNTBACK. sd comes from the per-round history nrl_comp.js ships, not
 *     from five hand-loaded rounds.
 * What MUST hold is the shape of the answer:
 *   1. DOL / CRO / PEN is the best line
 *   2. the same three lines fill the top three
 *   3. every line containing SYD ranks below every line without one
 *   4. no line is more than 3.5 percentage points from the reference
 *
 * Run from the repo root:  node reference/crosscheck.mjs
 */
import fs from 'fs';
import path from 'path';
import { createRequire } from 'module';
// resolve jsdom from the REPO's committed node_modules, wherever this file sits
const require = createRequire(path.join(process.cwd(), 'package.json'));
const { JSDOM, VirtualConsole } = require('jsdom');

const PY = {                       // reference_finals_solver.py, 2026-09-12
  'DOL/CRO/PEN': 44.73, 'NZW/NQL/PEN': 42.63, 'NZW/CRO/PEN': 41.74,
  'NZW/CRO/SYD': 41.23, 'DOL/NQL/PEN': 39.34, 'DOL/CRO/SYD': 38.22,
  'NZW/NQL/SYD': 36.27, 'DOL/NQL/SYD': 36.13,
};
const ORDER = ['NZW-DOL', 'CRO-NQL', 'PEN-SYD'];   // the reference's column order

const compFile = process.env.COMPFILE || 'nrl_comp.js';
let html = fs.readFileSync('nrl-tipping-guide.html', 'utf8');
for (const f of ['nrl_data.js', 'nrl_learned.js', 'nrl_players.js',
                 'nrl_lineups.js', 'nrl_comp.js', 'nrl_tiplog.js']) {
  const tag = new RegExp(`<script src="${f.replace('.', '\\.')}"></script>`);
  const src = f === 'nrl_comp.js' ? compFile : f;
  html = html.replace(tag, `<script>${fs.existsSync(src) ? fs.readFileSync(src, 'utf8') : ''}</script>`);
}
// The page defers its comp solve to an idle callback so a phone paints
// immediately (2026-09-12 audit follow-up). A cross-check must measure the REAL
// solve, not the provisional plan, so force the synchronous path — the same
// flag freeze_tips.mjs sets, for the same reason.
html = html.replace('<script>', '<script>window.NRL_SYNC_PLAN=true;</script><script>');

const boot = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => boot.push('jsdomError: ' + e.message));
vc.on('error', (...a) => boot.push('error: ' + a.join(' ')));
vc.on('warn', (...a) => boot.push('warn: ' + a.join(' ')));
const dom = new JSDOM(html, { url: 'https://localhost/', runScripts: 'dangerously',
                              pretendToBeVisual: true, virtualConsole: vc });
const w = dom.window;

const out = JSON.parse(w.eval(`(function(){
  COMP_PLAN=null;
  const t0=Date.now(); const pl=compPlanSync(); const ms=Date.now()-t0;
  return JSON.stringify({ms:ms, exact:!!(pl.sim&&pl.sim.exact), lines:(pl.sim&&pl.sim.lines)||[],
    pFirst:pl.sim&&pl.sim.pFirst, bFirst:pl.sim&&pl.sim.bFirst, tie:pl.sim&&pl.sim.tie,
    fitted:!!(COMP&&COMP.members&&COMP.members.some(m=>m.beh)),
    tips:fixtures.filter(f=>T(f.home)&&T(f.away)).map(f=>{const p=predict(f);
      return [f.home+'-'+f.away, tipSide(p).short];}),
    splits:Object.keys(pl.splits||{})});
})()`));

console.log('comp file        :', compFile);
console.log('boot console     :', boot.length ? boot.join(' | ') : '(clean)');
console.log('exact DP used    :', out.exact, ' solve time:', out.ms + 'ms');
console.log('rival model      :', out.fitted ? 'fitted per-member `beh` (shipping configuration)'
                                             : 'FALLBACK predictPick + herd rate (no `beh` in this nrl_comp.js)');
console.log('tips             :', out.tips.map(t => t.join('→')).join('  '));
console.log('countback P(win) :', (out.tie || []).map(x => (x * 100).toFixed(1) + '%').join(' / '));
console.log('');
console.log('  line              page      python     diff');
let ok = true, worst = 0;
const rank = [];
for (const ln of out.lines) {
  // print in the reference's game order regardless of the page's internal order
  const bySide = {};
  ln.tip.forEach(s => { bySide[s] = true; });
  const cols = ORDER.map(k => k.split('-').find(s => bySide[s]));
  const key = cols.join('/');
  const page = ln.p * 100, py = PY[key];
  const d = py === undefined ? NaN : page - py;
  if (!isNaN(d)) worst = Math.max(worst, Math.abs(d));
  rank.push(key);
  console.log(`  ${key.padEnd(16)} ${page.toFixed(2).padStart(6)}%  ${(py === undefined ? '  n/a' : py.toFixed(2)).padStart(6)}%  ${isNaN(d) ? '   --' : (d >= 0 ? '+' : '') + d.toFixed(2)}`);
}
console.log('');
const best = rank[0];
const check = (name, pass) => { console.log((pass ? '  PASS  ' : '  FAIL  ') + name); if (!pass) ok = false; };
const soft = (name, pass) => console.log((pass ? '  pass  ' : '  n/a   ') + name + '  (not asserted: fallback rival model)');
check('best line is DOL/CRO/PEN', best === 'DOL/CRO/PEN');
if (!out.fitted) {
  // Without a fitted `beh`, rivals collapse onto predictPick() at a flat herd
  // rate (~92%), which is both more predictable and less accurate than the
  // reference's logistic — so the levels move several points and one ordering
  // flips. The recommendation itself does not. Assert only that.
  console.log('        ^ the only check that applies without `beh`; run with');
  console.log('          COMPFILE=<a pipeline-generated nrl_comp.js> for the rest.');
  console.log('');
  console.log(ok ? 'CROSSCHECK OK (reduced: fallback rival model)' : 'CROSSCHECK FAILED');
  dom.window.close();
  process.exit(ok ? 0 : 1);
}
const TOP3 = ['DOL/CRO/PEN', 'NZW/NQL/PEN', 'NZW/CRO/PEN'];
check('the same three lines fill the top three',
  TOP3.every(k => rank.slice(0, 3).includes(k)));
if (rank[1] !== TOP3[1]) console.log('        (note: 2nd/3rd swapped vs the reference — see the header)');
const lastNonSyd = rank.map(k => k.includes('SYD')).lastIndexOf(false);
const firstSyd = rank.findIndex(k => k.includes('SYD'));
check('every SYD line ranks below every non-SYD line', firstSyd > lastNonSyd);
check(`no line more than 3.5 pts from the reference (worst ${worst.toFixed(2)})`, worst <= 3.5);
console.log('');
console.log(ok ? 'CROSSCHECK OK' : 'CROSSCHECK FAILED');
dom.window.close();
process.exit(ok ? 0 : 1);
