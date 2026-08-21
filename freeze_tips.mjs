#!/usr/bin/env node
/* freeze_tips.mjs — freeze each game's tip BEFORE kick-off, server-side.
 *
 * WHY THIS EXISTS: full-time grading must never grade a recomputed tip — after a
 * game, the Elo already contains that game's result and the market price is gone,
 * so the "tip" can flip to the winner with hindsight (see docs/GOTCHAS.md,
 * 2026-08-02). Grading therefore reads a frozen pre-kick-off tip. Freezing it in
 * the browser (localStorage) worked but was per-device; THIS script freezes it in
 * the pipeline instead, so every device sees the same record, automatically.
 *
 * HOW: it does NOT reimplement the model (a Python mirror is exactly the drift
 * risk GOTCHAS.md warns about). It loads the real nrl-tipping-guide.html with the
 * freshly generated data files into jsdom and asks the page's own predict() /
 * tipSide() what it is telling users right now. Zero divergence by construction:
 * if the front-end model changes, this freezes the changed model's tips.
 *
 * Output: nrl_tiplog.js -> window.NRL_TIPLOG = { updated, tips: [
 *   {season, round, home, away, tip, ko, ts}, ... ] }
 * An entry is (re)written on every run while its kick-off is still in the
 * future — the last pre-kick-off run wins. Once the game starts the entry is
 * never touched again. Entries for past rounds are kept (the season's record);
 * the log is pruned to the newest 250 entries. Best-effort: any failure leaves
 * the committed file untouched and exits 0 (a missing freeze must never block a
 * publish — the front-end falls back to its localStorage snapshot + the lock rule).
 */
import fs from 'fs';
import { JSDOM } from 'jsdom';

const PAGE = 'nrl-tipping-guide.html';
const OUT  = 'nrl_tiplog.js';
const DATA = ['nrl_data.js', 'nrl_learned.js', 'nrl_players.js', 'nrl_lineups.js', 'nrl_comp.js',
              'nrl_tiplog.js'];   // the PRIOR committed tiplog — see the note in main()

function readTiplog() {
  try {
    const raw = fs.readFileSync(OUT, 'utf8');
    const m = raw.match(/window\.NRL_TIPLOG\s*=\s*(\{[\s\S]*\})\s*;?\s*$/);
    const d = JSON.parse(m[1]);
    return { tips: Array.isArray(d.tips) ? d.tips : [],
             flips: Array.isArray(d.flips) ? d.flips : [] };
  } catch (e) { return { tips: [], flips: [] }; }
}

function main() {
  let html = fs.readFileSync(PAGE, 'utf8');
  // Inline the data files in place of their <script src> tags so the page runs
  // exactly as deployed, against exactly this run's data.
  for (const f of DATA) {
    const tag = new RegExp(`<script src="${f.replace('.', '\\.')}"></script>`);
    const body = fs.existsSync(f) ? fs.readFileSync(f, 'utf8') : '';
    html = html.replace(tag, `<script>${body}</script>`);
  }
  // The PRIOR committed tiplog now LOADS into the evaluation (2026-08-21;
  // until then it was stripped "to keep the freeze independent of its own
  // output" — a rationale from 2026-08-08 that the comp simulator has since
  // invalidated). simComp() reads the tiplog through gradedTip() (is my
  // perfect-round +2 still alive on this round's already-resolved games?) and
  // through the incumbency tie-break (frozen splits stay armed). Without it,
  // the freeze modelled the bonus as dead from a round's first result onward
  // and priced splits differently from every real browser — R25 SOU–NZW froze
  // the straight favourite while the site showed the split, and a phantom
  // "tip changed" flip announced it. Loading the prior copy is exactly what a
  // browser sees pre-run, and the merge below still reads the committed file
  // from disk independently, so the freeze cannot feed back into itself.

  const dom = new JSDOM(html, {
    url: 'https://localhost/', runScripts: 'dangerously', pretendToBeVisual: true,
  });
  const w = dom.window;

  // Ask the page what it is tipping for every game that hasn't kicked off.
  const fresh = w.eval(`(function(){
    const out=[];
    fixtures.forEach(f=>{
      if(!T(f.home)||!T(f.away)) return;
      const p=predict(f);
      if(fixtureResult(p)) return;                      // already has a score
      const ko=f.kickoff?Date.parse(f.kickoff):NaN;
      if(!isNaN(ko) && Date.now()>=ko) return;          // under way — too late
      const tip=tipSide(p);
      // prob + drivers ride along (2026-08-08) so a later run that flips the
      // tip can say WHAT it was and WHY it is what it is now. whySummary()
      // returns HTML; textContent strips it to plain text for the feed.
      const pr=Math.round((tip===p.h ? p.pHome : 1-p.pHome)*100);
      // de-vigged market prob of the tipped side (odds-history foundation —
      // the audit's #1 unblock: oddsW can't be fitted until this accumulates)
      const mk=(p.mkt===null||p.mkt===undefined)?null:Math.round((tip===p.h?p.mkt:1-p.mkt)*100);
      let why='';
      try{ const el=document.createElement('div');
           el.innerHTML=whySummary(p,f)||''; why=(el.textContent||'').trim().slice(0,220); }catch(e){}
      out.push({season:SRC.season, round:SRC.round, home:f.home, away:f.away,
                tip:tip.short, prob:pr, mkt:mk, why:why, ko:f.kickoff||null});
    });
    return out;
  })()`);

  const now = new Date().toISOString();
  const prior = readTiplog();
  const log = prior.tips;
  // Unordered-pair key (2026-08-04, audit A9): if the draw's designated home
  // side flips between runs, the orientation-sensitive key held TWO entries
  // for one game and myRecord() graded both. The stored entry keeps its
  // home/away orientation for display; only the dedupe key is unordered.
  const key = (t) => `${t.season}-${t.round}-${[t.home, t.away].sort().join('-')}`;
  const byKey = {};
  log.forEach((t) => { byKey[key(t)] = t; });
  let changed = 0;
  // Tip FLIPS (2026-08-08): when this run's tip differs from the last frozen
  // one, record it — the front-end surfaces these at the top of What's new.
  // Only pre-kick-off entries ever reach this loop, so a flip can never be a
  // post-game hindsight artefact. Kept 48h / 20 entries; the front-end shows
  // its own rolling 36h window on top.
  const flips = prior.flips.filter((f) => {
    const t = Date.parse(f && f.ts || '');
    return !isNaN(t) && (Date.now() - t) < 48 * 3600 * 1000;
  });
  fresh.forEach((t) => {
    const k = key(t);
    const cur = byKey[k];
    // A fixture with NO kickoff on the feed is almost always a game IN PLAY —
    // nrl.com blanks a fixture's kickoff while it's running (seen twice on
    // 2026-08-08, and run #84 already overwrote one entry mid-game before this
    // guard existed). With no clock to check, the only safe move is to leave
    // an existing frozen entry completely alone: grading with a slightly stale
    // PRE-GAME tip is always legitimate; a mid-game overwrite is graded
    // hindsight — the exact bug this file exists to prevent. No flip either.
    // Updates resume when the feed carries a kickoff again; a fixture with no
    // entry yet still gets one (better a lightly-anchored tip than none).
    if (cur && !t.ko) return;
    if (!cur || cur.tip !== t.tip) changed++;
    if (cur && cur.tip !== t.tip) {
      flips.push({ season: t.season, round: t.round, home: t.home, away: t.away,
        from: cur.tip, to: t.tip,
        fromProb: (typeof cur.prob === 'number') ? cur.prob : null,
        toProb: (typeof t.prob === 'number') ? t.prob : null,
        why: t.why || '', ts: now });
    }
    byKey[k] = { ...t, ts: now };            // pre-kick-off: last run wins
  });
  while (flips.length > 20) flips.shift();
  let tips = Object.values(byKey);
  tips.sort((a, b) => (a.season - b.season) || (a.round - b.round) || a.home.localeCompare(b.home));
  if (tips.length > 250) tips = tips.slice(tips.length - 250);

  const out = `/* Auto-generated by freeze_tips.mjs — DO NOT hand-edit (overwritten each run).
 * The official pre-kick-off tip for each game, frozen by the pipeline so
 * full-time grading is identical on every device and can never use hindsight.
 * An entry stops changing the moment its game kicks off. */
window.NRL_TIPLOG = ${JSON.stringify({ updated: now, tips, flips }, null, 1)};
`;
  const tmp = OUT + '.tmp';
  fs.writeFileSync(tmp, out);
  fs.renameSync(tmp, OUT);
  console.log(`[freeze_tips] froze ${fresh.length} upcoming tip(s) (${changed} new/changed), log now ${tips.length} entries, ${flips.length} flip(s) on record.`);
  // The page now schedules a 5-minute refresh interval (2026-08-04 freshness
  // work); jsdom timers are real Node timers and would keep this process alive
  // forever. Close the window so the run terminates the moment we're done.
  dom.window.close();
}

try { main(); }
catch (e) {
  console.error(`[freeze_tips] WARNING: freeze failed (${e && e.message}) — keeping the committed ${OUT}; front-end falls back to local snapshots + the lock rule.`);
  process.exit(0);   // best-effort by design: never block a publish
}
