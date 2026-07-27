#!/usr/bin/env node
/**
 * smoke_test.mjs — Dev C (QA/tooling)
 *
 * Standalone Node smoke test (no dependencies). Run with:
 *   node smoke_test.mjs
 *
 * IMPORTANT: nrl-tipping-guide.html embeds the prediction model inline in a
 * <script> tag (owned by Dev B), it is not exported as a module. This test
 * replicates the CURRENT model formula from that file (rating(), prob(), and
 * the per-game tip/lock logic in render()) so it can run headlessly in Node.
 *
 * >>> If Dev B changes the model math in nrl-tipping-guide.html, the
 * >>> `rating()` / `prob()` functions below MUST be updated to match, or
 * >>> this test will silently validate the wrong model. As a best-effort
 * >>> safety net, this file also does a light regex scan of the HTML (if
 * >>> found alongside it) and warns (not fails) if the key formulas there
 * >>> look like they've drifted from what's hardcoded here.
 *
 * What is asserted:
 *   1. A tip is produced for every fixture in the round.
 *   2. Win probabilities are always within [0, 1].
 *   3. The Roosters (SYD) are always the tip in their own game (locked pick),
 *      regardless of what the model itself would have favoured.
 *   4. Bye weeks are handled (a team with no fixture doesn't crash anything,
 *      and is reported as the bye, not as a game).
 *   5. The model does not crash when the season match-log (`results[]`) is
 *      absent — i.e. the fallback avg-margin+form method must be robust to
 *      the optional field simply not being there.
 *   6. A drawn game (result logger scores it as a "push") is not counted as
 *      either a model hit or a model miss.
 *   7. Win probabilities stay within [0, 1] across a wide range of
 *      rating gaps, including extreme blowout-sized gaps.
 *   8. marketProb() (the odds -> de-vigged win-probability helper) handles
 *      null, the legacy flat {home,away} odds shape, and the new
 *      {open,close} shape (opening/closing odds for CLV) — always
 *      returning a value in [0,1] or null, using `close` when present.
 *   9. (Learning loop, v4) An Elo replay of a fixed results list is
 *      DETERMINISTIC and independent of the order the results array is
 *      given in (it must sort by round internally before replaying).
 *  10. (Learning loop, v4) A team that only ever wins ends up rated above
 *      a team that only ever loses.
 *  11. (Learning loop, v4) A walk-forward Brier score computed while
 *      replaying results stays within [0,1].
 *
 * >>> NOTE ON FRONT-END CHANGES (draws-as-push, accuracy tracker): the HTML
 * >>> is gaining a result-logger scoring change where a drawn game counts as
 * >>> a "push" (neither a hit nor a miss) when comparing the model's tip (or
 * >>> the Roosters lock) against the final score, plus an accuracy tracker
 * >>> that compares model-vs-lock hit rates on the same denominator. If Dev B
 * >>> changes that scoring logic in nrl-tipping-guide.html, the scoreResult()
 * >>> mirror below MUST be kept in sync, the same as rating()/prob().
 */

// ---- Mirrors nrl-tipping-guide.html's rating()/prob() (avg margin + form) ----
const LOCK = "SYD"; // Roosters always tipped, per SPEC.md

function rating(t, formWeight = 1.2) {
  const base = (t.PF - t.PA) / Math.max(1, t.P);
  const form = (t.last5 - 2.5) * formWeight;
  return base + form;
}

function prob(margin) {
  return 1 / (1 + Math.exp(-margin / 7));
}

/**
 * Compute tips for a round. Mirrors the per-game loop inside render() in
 * the HTML: predicted margin = home rating - away rating + HGA; higher-rated
 * side (after HGA) is the model tip; the Roosters game's *displayed* tip is
 * always overridden to SYD regardless of what the model favours (that's the
 * "locked pick" feature), while modelAgrees records whether the model's own
 * unlocked pick matched.
 */
function computeTips({ teams, fixtures, byeTeams = [] }, { hga = 3, formWeight = 1.2 } = {}) {
  const byShort = Object.fromEntries(teams.map((t) => [t.short, t]));
  const tips = [];

  for (const f of fixtures) {
    const h = byShort[f.home];
    const a = byShort[f.away];
    if (!h || !a) {
      throw new Error(`Fixture references unknown team: ${f.home} v ${f.away}`);
    }
    const rh = rating(h, formWeight);
    const ra = rating(a, formWeight);
    const margin = rh - ra + hga; // positive => home favoured
    const pHome = prob(margin);
    const homeFav = margin >= 0;
    const modelTip = homeFav ? h.short : a.short;

    const isLockGame = h.short === LOCK || a.short === LOCK;
    const finalTip = isLockGame ? LOCK : modelTip;

    tips.push({
      home: h.short,
      away: a.short,
      pHome,
      pAway: 1 - pHome,
      modelTip,
      finalTip,
      isLockGame,
      modelAgreesWithLock: isLockGame ? modelTip === LOCK : null,
    });
  }

  // teams that played neither home nor away and aren't declared as bye
  const playing = new Set(fixtures.flatMap((f) => [f.home, f.away]));
  const unaccounted = teams
    .map((t) => t.short)
    .filter((s) => !playing.has(s) && !byeTeams.includes(s));

  return { tips, unaccounted };
}

/**
 * Mirrors the (new) result-logger scoring rule in nrl-tipping-guide.html:
 * a drawn game (homeScore === awayScore) is a "push" — it counts toward
 * neither hits nor misses for whoever was tipped (model or lock). Any
 * non-draw game is a hit if the tipped team's short matches the winner,
 * else a miss.
 */
function scoreResult(tippedShort, homeShort, awayShort, homeScore, awayScore) {
  if (homeScore === awayScore) {
    return "push";
  }
  const winner = homeScore > awayScore ? homeShort : awayShort;
  return tippedShort === winner ? "hit" : "miss";
}

/**
 * marketProb(odds) — mirrors nrl-tipping-guide.html's odds -> de-vigged
 * home-win-probability helper, EXTENDED for the new opening/closing odds
 * shape (fixture.odds = {open:{home,away}|null, close:{home,away}|null})
 * that enables closing-line-value (CLV) tracking, while still supporting
 * the legacy flat {home,away} shape and null.
 *
 * Rule (must match the front-end exactly): use `close` when present, else
 * the legacy flat {home,away} shape, else null.
 *
 * >>> This function MUST be kept in sync with marketProb() in
 * >>> nrl-tipping-guide.html (owned by Dev B) the same way rating()/prob()/
 * >>> scoreResult() above are. If Dev B's marketProb() changes which odds
 * >>> field it prefers, update this mirror to match or this test will
 * >>> silently validate the wrong rule.
 */
function marketProb(odds) {
  if (!odds) return null;
  if (Object.prototype.hasOwnProperty.call(odds, "open") ||
      Object.prototype.hasOwnProperty.call(odds, "close")) {
    // New {open,close} shape: use the latest (close) price. An open-only
    // fixture (no close yet) has no "current" market read, so falls to null.
    const pair = odds.close;
    if (!pair || !(pair.home > 1) || !(pair.away > 1)) return null;
    const h = 1 / pair.home, a = 1 / pair.away;
    return h / (h + a);
  }
  // Legacy flat {home,away} shape.
  if (!(odds.home > 1) || !(odds.away > 1)) return null;
  const h = 1 / odds.home, a = 1 / odds.away;
  return h / (h + a);
}

// ---------------------------------------------------------------------
// Test harness (tiny, dependency-free)
// ---------------------------------------------------------------------
let pass = 0;
let fail = 0;
const failures = [];

function assert(cond, msg) {
  if (cond) {
    pass++;
  } else {
    fail++;
    failures.push(msg);
  }
}

// ---- Fixture dataset (small, hand-built, mirrors the shape of nrl_data.js) ----
const sampleTeams = [
  { name: "Panthers", short: "PEN", P: 18, W: 14, L: 4, PF: 539, PA: 255, last5: 2 },
  { name: "Roosters", short: "SYD", P: 18, W: 13, L: 5, PF: 449, PA: 364, last5: 4 },
  { name: "Warriors", short: "NZW", P: 18, W: 12, L: 6, PF: 496, PA: 306, last5: 3 },
  { name: "Sharks", short: "CRO", P: 17, W: 11, L: 6, PF: 488, PA: 363, last5: 4 },
  { name: "Dolphins", short: "DOL", P: 18, W: 11, L: 7, PF: 488, PA: 404, last5: 3 },
  { name: "Rabbitohs", short: "SOU", P: 18, W: 10, L: 8, PF: 510, PA: 432, last5: 3 },
  { name: "Dragons", short: "STI", P: 17, W: 2, L: 15, PF: 256, PA: 503, last5: 2 },
];

const sampleFixtures = [
  { home: "PEN", away: "STI" }, // heavy home favourite
  { home: "SOU", away: "SYD" }, // Roosters as away underdog-ish -> tests the lock override
  { home: "CRO", away: "DOL" },
];
const sampleBye = ["NZW"];

// Test 1-3: tip produced for every game, probabilities in range, Roosters locked
{
  const { tips, unaccounted } = computeTips(
    { teams: sampleTeams, fixtures: sampleFixtures, byeTeams: sampleBye },
    { hga: 3, formWeight: 1.2 }
  );

  assert(tips.length === sampleFixtures.length, "a tip is produced for every fixture");

  for (const t of tips) {
    assert(
      Number.isFinite(t.pHome) && t.pHome >= 0 && t.pHome <= 1,
      `pHome in [0,1] for ${t.home} v ${t.away} (got ${t.pHome})`
    );
    assert(
      Number.isFinite(t.pAway) && t.pAway >= 0 && t.pAway <= 1,
      `pAway in [0,1] for ${t.home} v ${t.away} (got ${t.pAway})`
    );
    assert(!!t.finalTip, `a non-empty tip exists for ${t.home} v ${t.away}`);
  }

  const roostersGame = tips.find((t) => t.home === "SYD" || t.away === "SYD");
  assert(!!roostersGame, "Roosters game found in fixture list");
  assert(
    roostersGame && roostersGame.finalTip === "SYD",
    "Roosters (SYD) are always the tip in their own game, regardless of model favourite"
  );

  // bye handling: NZW has no fixture and is declared as bye -> should not be "unaccounted"
  assert(
    unaccounted.length === 0,
    `bye team accounted for correctly (unaccounted: ${JSON.stringify(unaccounted)})`
  );
}

// Test 4: bye weeks handled even when Roosters themselves are on bye (no lock game that round)
{
  const teamsNoSyd = sampleTeams.filter((t) => t.short !== "SYD");
  // Rebuild fixtures without SYD, byeTeams includes SYD
  const fixturesNoBye = [
    { home: "PEN", away: "STI" },
    { home: "SOU", away: "CRO" },
  ];
  let threw = false;
  let result;
  try {
    result = computeTips(
      { teams: sampleTeams, fixtures: fixturesNoBye, byeTeams: ["SYD", "NZW", "DOL"] },
      { hga: 3, formWeight: 1.2 }
    );
  } catch (e) {
    threw = true;
  }
  assert(!threw, "computing tips for a round where Roosters are on bye does not crash");
  const hasLockGame = result && result.tips.some((t) => t.isLockGame);
  assert(!hasLockGame, "no locked-pick game exists when Roosters have the bye");
}

// Test 5: model does not crash when results[] (season match-log) is absent
{
  const dataWithoutResults = {
    teams: sampleTeams,
    fixtures: sampleFixtures,
    byeTeams: sampleBye,
    // no `results` key at all — matches SPEC.md's "results[] is optional"
  };
  let threw = false;
  try {
    const { tips } = computeTips(dataWithoutResults, { hga: 3, formWeight: 1.2 });
    assert(tips.length === sampleFixtures.length, "tips still computed with results[] absent");
  } catch (e) {
    threw = true;
  }
  assert(!threw, "model does not crash when results[] (season match-log) is missing");
}

// Test 6: unknown team in a fixture is a hard error, not a silent wrong tip
{
  let threw = false;
  try {
    computeTips(
      { teams: sampleTeams, fixtures: [{ home: "PEN", away: "XXX" }], byeTeams: [] },
      {}
    );
  } catch (e) {
    threw = true;
  }
  assert(threw, "an unknown team short in a fixture raises rather than silently mis-tipping");
}

// Test 7: a drawn game is scored as a "push" — not a model hit or a miss
{
  const push = scoreResult("PEN", "PEN", "STI", 18, 18);
  assert(push === "push", `a 18-18 draw is scored as 'push', got '${push}'`);
  assert(push !== "hit" && push !== "miss", "a draw is never counted as a hit or a miss");

  const hit = scoreResult("PEN", "PEN", "STI", 24, 12);
  assert(hit === "hit", "a genuine home win for the tipped team is still scored as a hit");

  const miss = scoreResult("PEN", "PEN", "STI", 6, 24);
  assert(miss === "miss", "a loss for the tipped team is still scored as a miss");

  // Sanity-check across a small batch of results including a draw, mirroring
  // an accuracy-tracker style tally: pushes should not appear in either the
  // hit or miss bucket, and the three buckets should account for every game.
  const batch = [
    scoreResult("PEN", "PEN", "STI", 20, 10), // hit
    scoreResult("SYD", "SOU", "SYD", 12, 12), // push (draw)
    scoreResult("CRO", "CRO", "DOL", 8, 30), // miss
  ];
  const tally = { hit: 0, miss: 0, push: 0 };
  for (const r of batch) tally[r]++;
  assert(tally.push === 1, "exactly one push counted in the sample batch");
  assert(tally.hit + tally.miss + tally.push === batch.length, "every game lands in exactly one bucket");
}

// Test 8: win probabilities stay within [0, 1] across a wide range of rating gaps
{
  const gaps = [-1000, -100, -50, -21, -7, -3, -1, 0, 1, 3, 7, 21, 50, 100, 1000];
  for (const gap of gaps) {
    const p = prob(gap);
    assert(
      Number.isFinite(p) && p >= 0 && p <= 1,
      `prob(${gap}) stays within [0,1] (got ${p})`
    );
  }

  // Same check driven through the full computeTips() path with an artificially
  // lopsided team (huge PF/PA gap) to exercise a large rating gap end-to-end.
  const lopsidedTeams = [
    { name: "Blowout FC", short: "BLO", P: 18, W: 18, L: 0, PF: 900, PA: 50, last5: 5 },
    { name: "Wooden Spoon", short: "WSP", P: 18, W: 0, L: 18, PF: 50, PA: 900, last5: 0 },
    { name: "Roosters", short: "SYD", P: 18, W: 9, L: 9, PF: 400, PA: 400, last5: 2 },
  ];
  const { tips: lopsidedTips } = computeTips(
    { teams: lopsidedTeams, fixtures: [{ home: "BLO", away: "WSP" }], byeTeams: ["SYD"] },
    { hga: 3, formWeight: 1.2 }
  );
  for (const t of lopsidedTips) {
    assert(
      t.pHome >= 0 && t.pHome <= 1 && t.pAway >= 0 && t.pAway <= 1,
      `probabilities stay in [0,1] even for a lopsided blowout matchup (got pHome=${t.pHome}, pAway=${t.pAway})`
    );
  }
}

// Test 9: marketProb() handles null, legacy flat, and the new {open,close}
// odds shape, always returning a value in [0,1] or null (never NaN/throws).
{
  const cases = [
    { label: "null odds", odds: null, expectNull: true },
    { label: "legacy flat valid", odds: { home: 1.85, away: 1.95 }, expectNull: false },
    { label: "legacy flat invalid (<=1)", odds: { home: 1, away: 1.95 }, expectNull: true },
    { label: "open+close both present -> uses close", odds: { open: { home: 2.0, away: 1.8 }, close: { home: 1.5, away: 2.6 } }, expectNull: false },
    { label: "open only, close null -> null (no current market read)", odds: { open: { home: 1.85, away: 1.95 }, close: null }, expectNull: true },
    { label: "open+close both null", odds: { open: null, close: null }, expectNull: true },
    { label: "close invalid (<=1)", odds: { open: { home: 1.85, away: 1.95 }, close: { home: 1, away: 2 } }, expectNull: true },
  ];

  for (const c of cases) {
    let p, threw = false;
    try {
      p = marketProb(c.odds);
    } catch (e) {
      threw = true;
    }
    assert(!threw, `marketProb() does not throw for case: ${c.label}`);
    if (c.expectNull) {
      assert(p === null, `marketProb() returns null for case: ${c.label} (got ${p})`);
    } else {
      assert(
        Number.isFinite(p) && p >= 0 && p <= 1,
        `marketProb() returns a value in [0,1] for case: ${c.label} (got ${p})`
      );
    }
  }

  // Sanity: close price should be the one actually used when open/close differ.
  const usesClose = marketProb({ open: { home: 2.0, away: 1.8 }, close: { home: 1.5, away: 2.6 } });
  const fromCloseDirectly = marketProb({ home: 1.5, away: 2.6 });
  assert(
    Math.abs(usesClose - fromCloseDirectly) < 1e-9,
    "marketProb() with open+close present matches the result of the close price alone (uses close, not open)"
  );
}

// ---------------------------------------------------------------------
// Learning loop (v4): Elo replay + walk-forward Brier
//
// NOTE: `learn_model.py` does not exist yet in this checkout (it's the
// pipeline half of the learning loop, owned elsewhere, out of scope for
// this QA/tooling file). The functions below are a minimal, self-contained
// mirror of the Elo replay + walk-forward backtest contract documented in
// SPEC.md's "Learning loop (v4)" section (standard logistic Elo, base 10,
// scale 400, K-factor + home-ground-advantage in Elo points, sorted by
// round before replay). They exist so this suite can assert the CONTRACT
// (determinism, order-independence, winners > losers, Brier in [0,1])
// without needing the real pipeline. >>> Once learn_model.py exists and
// nrl_learned.js is real, prefer testing its actual output; keep this
// mirror in sync with learn_model.py's real Elo formula the same way
// rating()/prob()/scoreResult()/marketProb() above mirror the HTML.
// ---------------------------------------------------------------------

function replayElo(results, { k = 20, hga = 50, initial = 1500 } = {}) {
  const sorted = [...results].sort((a, b) => a.round - b.round);
  const ratings = {};
  const get = (short) => (short in ratings ? ratings[short] : (ratings[short] = initial));

  for (const g of sorted) {
    const rh = get(g.home);
    const ra = get(g.away);
    const expectedHome = 1 / (1 + Math.pow(10, -((rh + hga - ra) / 400)));
    const actualHome = g.hs > g.as ? 1 : g.hs < g.as ? 0 : 0.5;
    ratings[g.home] = rh + k * (actualHome - expectedHome);
    ratings[g.away] = ra + k * (1 - actualHome - (1 - expectedHome));
  }
  return ratings;
}

function walkForwardBrier(results, { k = 20, hga = 50, initial = 1500 } = {}) {
  const sorted = [...results].sort((a, b) => a.round - b.round);
  const ratings = {};
  const get = (short) => (short in ratings ? ratings[short] : (ratings[short] = initial));

  let sumSq = 0;
  let n = 0;
  for (const g of sorted) {
    const rh = get(g.home);
    const ra = get(g.away);
    const pHome = 1 / (1 + Math.pow(10, -((rh + hga - ra) / 400)));

    if (g.hs !== g.as) {
      const outcome = g.hs > g.as ? 1 : 0;
      sumSq += (pHome - outcome) ** 2;
      n++;
    }

    // walk-forward: predict first (above), THEN update ratings on the result
    const actualHome = g.hs > g.as ? 1 : g.hs < g.as ? 0 : 0.5;
    ratings[g.home] = rh + k * (actualHome - pHome);
    ratings[g.away] = ra + k * (1 - actualHome - (1 - pHome));
  }
  return n > 0 ? sumSq / n : null;
}

// Test 10: Elo replay is deterministic and independent of input array order
{
  const gamesInOrder = [
    { round: 1, home: "PEN", away: "STI", hs: 24, as: 12 },
    { round: 1, home: "SYD", away: "SOU", hs: 20, as: 18 },
    { round: 2, home: "STI", away: "SYD", hs: 10, as: 30 },
    { round: 2, home: "SOU", away: "PEN", hs: 14, as: 22 },
    { round: 3, home: "PEN", away: "SYD", hs: 18, as: 16 },
  ];
  // Same games, deliberately shuffled out of round order.
  const shuffled = [gamesInOrder[3], gamesInOrder[0], gamesInOrder[4], gamesInOrder[1], gamesInOrder[2]];

  const ratingsA = replayElo(gamesInOrder);
  const ratingsB = replayElo(shuffled);

  assert(
    Object.keys(ratingsA).length === Object.keys(ratingsB).length &&
      Object.keys(ratingsA).every((s) => Math.abs(ratingsA[s] - ratingsB[s]) < 1e-9),
    `Elo replay is order-independent (sorts by round internally): ` +
      `${JSON.stringify(ratingsA)} vs ${JSON.stringify(ratingsB)}`
  );

  // Running it again on the same (still-shuffled) input reproduces the exact
  // same ratings — i.e. the replay is deterministic, not just order-agnostic.
  const ratingsC = replayElo(shuffled);
  assert(
    Object.keys(ratingsB).every((s) => Math.abs(ratingsB[s] - ratingsC[s]) < 1e-12),
    "Elo replay is deterministic across repeated runs on the same input"
  );
}

// Test 11: a team that only ever wins ends up rated above a team that only ever loses
{
  const games = [
    { round: 1, home: "WIN", away: "LOS", hs: 30, as: 10 },
    { round: 2, home: "LOS", away: "WIN", hs: 8, as: 26 },
    { round: 3, home: "WIN", away: "LOS", hs: 22, as: 14 },
    { round: 4, home: "LOS", away: "WIN", hs: 6, as: 40 },
  ];
  const ratings = replayElo(games);
  assert(
    ratings.WIN > ratings.LOS,
    `an always-winning team ends up rated above an always-losing team (WIN=${ratings.WIN}, LOS=${ratings.LOS})`
  );
}

// Test 12: walk-forward Brier score stays within [0, 1]
{
  const games = [
    { round: 1, home: "PEN", away: "STI", hs: 24, as: 12 },
    { round: 1, home: "SYD", away: "SOU", hs: 20, as: 18 },
    { round: 2, home: "STI", away: "SYD", hs: 10, as: 30 },
    { round: 2, home: "SOU", away: "PEN", hs: 14, as: 22 },
    { round: 3, home: "PEN", away: "SYD", hs: 18, as: 16 },
    { round: 3, home: "SOU", away: "STI", hs: 26, as: 8 },
    { round: 4, home: "PEN", away: "SOU", hs: 30, as: 6 },
    { round: 4, home: "SYD", away: "STI", hs: 12, as: 12 }, // draw, excluded from Brier's n
  ];
  const brier = walkForwardBrier(games);
  assert(
    typeof brier === "number" && Number.isFinite(brier) && brier >= 0 && brier <= 1,
    `walk-forward Brier score is in [0,1] (got ${brier})`
  );

  // A single-game, near-guaranteed-outcome sanity check: a huge pre-existing
  // rating gap should predict the eventual (correct) winner with high
  // confidence, keeping the per-game squared error small.
  const lopsided = walkForwardBrier(
    [{ round: 1, home: "PEN", away: "STI", hs: 40, as: 4 }],
    { initial: 1500 }
  );
  assert(
    typeof lopsided === "number" && lopsided >= 0 && lopsided <= 1,
    `walk-forward Brier score for a single game is also in [0,1] (got ${lopsided})`
  );
}

// ---- Best-effort drift check against nrl-tipping-guide.html (warn-only) ----
try {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const htmlPath = path.join(new URL(".", import.meta.url).pathname, "nrl-tipping-guide.html");
  if (fs.existsSync(htmlPath)) {
    const html = fs.readFileSync(htmlPath, "utf8");
    const hasBaseFormula = html.includes("(t.PF - t.PA)");
    const hasLogistic = html.includes("Math.exp(-margin/7)") || html.includes("Math.exp(-margin / 7)");
    const hasLock = html.includes('LOCK = "SYD"') || html.includes("LOCK='SYD'");
    if (!hasBaseFormula || !hasLogistic || !hasLock) {
      console.log(
        "WARN: nrl-tipping-guide.html's formulas may have drifted from the ones " +
          "replicated in smoke_test.mjs — update rating()/prob()/LOCK here to match."
      );
    }
  }
} catch {
  // best-effort only; never fail the suite because of this check
}

// ---------------------------------------------------------------------
console.log("-".repeat(60));
if (fail === 0) {
  console.log(`PASS: ${pass}/${pass} checks passed.`);
  process.exit(0);
} else {
  console.log(`FAIL: ${fail}/${pass + fail} checks failed:`);
  for (const f of failures) console.log(`  - ${f}`);
  process.exit(1);
}
