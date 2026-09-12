# Data Pipeline — scripts, files, and schemas

Every script, every file it reads/writes, and the exact shape of each data file.
For the flow overview see `ARCHITECTURE.md`; for the tip math see `MODEL.md`.

All Python here targets 3.12 and uses only `requests` + `beautifulsoup4` (installed
by the workflow). The parser/fitter are **pure and network-free**; only
`cloud_fetch.py` touches the network, and it only runs on GitHub's servers.

---

## Scripts

### `cloud_fetch.py` — scrape live sources (GitHub only)
Fetches the live pages and writes clean intermediate dumps + the ratings map.

| Produces | From | Notes |
|----------|------|-------|
| `ladder_dump.html` | Zero Tackle NRL ladder | Rebuilt `<table>` incl. home/away split tables. Aborts (keeps old) if < 17 teams. |
| `draw_dump.html` | Zero Tackle fixtures/results | The **lowest round with unplayed games** → auto-advances weekly. Written only if 6–9 fixtures parse (finals: 1..`FINALS_GAMES[rnd]`, i.e. 4/2/2/1) **and** the count isn't lower than the already-committed dump for that round (so a half-resolved fallback can't shrink a good file). Match-centre slugs name the round as `round-27` or `round-finals-week-1` / `round-preliminary-finals` / `round-grand-final` — all resolved by `parse_nrl.round_from_text()` (2026-09-07). The `<h2>` stays numeric (`Round 28`); a comment line carries the label. |
| `odds_dump.txt` | **The Odds API** (primary), nrl.com draw payload (fallback) | `Home v Away: 2.52 / 1.53` decimal head-to-head prices (median across the AU books when from the API). A fixture is omitted entirely until its market opens. Fed to `parse_nrl` via `--odds`. A stale dump from a *different* round is cleared, not reused. **The API needs the `ODDS_API_KEY` repo secret** — nrl.com withholds prices from non-Australian IPs, so on GitHub's US runners the fallback alone yields nothing (see `GOTCHAS.md`). Non-fatal on every failure. |
| `odds_api_status.json` | The Odds API response headers | How the odds call went: `state` (`ok`/`no-key`/`bad-key`/`quota-exhausted`/…) + the monthly-quota counters. Folded into `last_run.json`. **Never contains the key.** |
| `draw_meta.json` | **nrl.com draw payload** | Per fixture: `venue`, `venueCity`, and the UTC kick-off. Fed to `parse_nrl` via `--draw-meta`. This is the only source of stadium + kick-off — Zero Tackle's page doesn't carry them in a parseable form. |
| `nrl_lineups.js` | Zero Tackle round team-lists article | The named squad per club. The previous copy is snapshotted to `nrl_lineups.prev.js` **before** the rewrite, so the change feed can diff named/omitted players. Article slugs (`round-21-…`, `finals-week-1-…`, `grand-final-…`) resolve via `round_from_text()`; Origin / Pacific Championships / pre-season / NRLW articles are skipped (`NON_PREMIERSHIP_RE`). Published when ≥6 clubs parse, or ≥`FINALS_GAMES[rnd]` (half the week's clubs) in the finals. |
| `results_dump.txt` | Zero Tackle fixtures/results (same page) | Every **finished** game's score as `Round N` + `Home hs - Away aws` (teams+round from the `fulltime-…` slug, scores from the `FT` block). Fed to `parse_nrl` via `--results`; grows the results memory that powers form, splits and Elo. Kept if ≥ 8 games parse. |
| `injuries_dump.html` | Zero Tackle injuries & suspensions | `Team: Player (Reason) — back Round N; ...` (up to 6 per club). Return of `TBC`/unknown is left as no "— back" suffix. Kept if ≥ 6 clubs parse (finals: ≥ `max(2, FINALS_GAMES[rnd])` — the page only lists clubs still alive, 8/4/4/2). Rows whose cells are all ≤2 chars are rejected, and the player cell must look like a real name (≥2 words / ≥4 letters / a `/players/` link) — a Panthers stats table once published phantom player "P" (2026-08-04). |
| `nrl_players.js` | Zero Tackle **overall player ratings** | `window.NRL_PLAYERS = { "name": {pos, pct} }`. Written only if ≥ 100 players parse. |

Key internals:
- Team recognition is shared with `parse_nrl.py` via `find_short()` (alias table).
- **The nrl.com source.** `https://www.nrl.com/draw/?competition=111&round=N&season=YYYY`
  embeds a JSON blob in the `q-data` attribute of `#vue-draw`; each fixture carries
  `venue`, `venueCity`, `clock.kickOffTimeLong` (UTC) and `homeTeam/awayTeam.odds`
  (a **string**, absent before the market opens). `reconcile_draw()` decides conflicts:
  **Zero Tackle wins on which round** (it drives everything else), **nrl.com wins on
  home/away** (it's the official listing — see the "looks swapped" entry in `GOTCHAS.md`),
  and every flip is logged rather than applied silently. If nrl.com won't parse, its
  metadata is dropped and the Zero Tackle draw stands.
- Weather scraping was removed entirely on 2026-08-04 (Open-Meteo, `CITY_COORDS`,
  `fetch_weather`, `weather_dump.txt` — all gone; the workflow deletes the committed
  dump).
- `extract_ratings()` scrapes the **nine per-position pages**
  (`/nrl-player-ratings/halfback/` etc.), not `/overall/`, and takes each player's name
  from their `/players/<slug>/` **anchor**, using the href slug to pick the right half of
  the doubled anchor text. The position is implied by the URL.
  > ⚠ **This bullet used to say the opposite** — that the table has no player links and
  > that names must be read positionally by cell index. That advice was wrong and caused
  > a real multi-week outage: `/overall/` splits a name across two cells, so "the cell
  > after the rank" yields first-name-only keys (`"nathan"`, `"harry"`), which match
  > nothing in the injury feed and silently disable every injury adjustment. Do not
  > reintroduce positional parsing. Full post-mortem in `GOTCHAS.md`.
- The publish guard requires ≥100 players **and** ≥80% of keys containing a space — a
  key that isn't a full name can never match the front-end, so it *is* a failed parse.
- `norm_name()` (Python) must stay identical to `normName()` (JS in the HTML) so the
  ratings keys match the injury-feed names.

### `parse_nrl.py` — dumps → `nrl_data.js` (pure)
Two modes:
- **Full rebuild** (default): parse ladder + home/away splits + draw, apply optional
  `--odds`/`--injuries` dumps, validate 17 teams, write `nrl_data.js`.
- **`--merge`** (daily reactive refresh): load the existing `nrl_data.js` and update
  ONLY `fixture.odds`, `team.news`, and the `newsUpdated` stamp —
  ladder numbers, round, splits, and the fixtures list are left byte-for-byte.

Also, in **both** modes, it scans the draw dump (and optional `--results`) for finished
scores and **appends** them to `nrl_learned.js.results` (deduped on
**season**+round+home+away — entries without `season` default to 2026;
never deletes; aborts if the existing file is unparseable).

Reference tables live at the top of the file: `TEAMS` (short → name + aliases),
`CLUB_COLOUR`, `TEAM_HOME_CITY`, `VENUE_CITY`. **Finals helpers** (2026-09-07, imported
by `cloud_fetch.py`): `REGULAR_ROUNDS = 27`, `FINALS_START`, `FINALS_GAMES`
({28:4, 29:2, 30:2, 31:1}), `is_finals()`, `round_label()` and `round_from_text()` — the
single place any source's round naming becomes a number. `compute_bye()` returns `[]`
in a finals round. Add new venues to `VENUE_CITY` if a
heritage/regional game resolves to the wrong city.

Odds evolve into an `{open, close}` shape for CLV. **Since 2026-08-04, BOTH modes
preserve the first-seen `open`**: a full rebuild inherits the previous published
`open` for the same round + fixture pair (orientation-corrected) and only seeds
`open = fresh` on first sighting; `close` always updates. (Before this, full mode
set `open = close = fresh` on every run, and since the workflow only ever runs full
rebuilds, the open was destroyed every 4 hours and the "line moved" UI could never
fire.) Legacy flat `{home,away}` is still accepted.

### `learn_model.py` — results memory → fitted params + Elo (pure)
Reads `nrl_learned.js.results`, replays Elo, grid-searches params, backtests, and
rewrites `nrl_learned.js` with fresh `params`/`elo`/`backtest` and one appended
`history` entry. Under 30 games → conservative defaults + `lowConfidence = true`.
Grids: `eloK ∈ {10,16,24,32,40}`, `eloHGA ∈ {0,20,40,60,80,100}`,
`oddsWeight ∈ {0.0..1.0}`. **`logisticScale` is pinned at 7 and NOT in the grid**
(2026-08-04 — it's unidentifiable from win/loss outcomes; see `GOTCHAS.md`).
The Elo replay's MOV multiplier is winner-relative (upsets amplified).
*(Until 2026-09-12 the backtest also published `lockTax`, the walk-forward loyalty-tax
counts from pre-game Elos. `LOCK_TEAM`, `lock_tax_metrics()` and the assignment were
deleted with the Roosters lock; `validate_learned.py` never required the key, so the
publish gate is unchanged.)*
Never fetches; `--odds-history FILE` is optional for fitting `oddsWeight`.

### `validate_data.py` / `validate_learned.py` — publish gates
Parse the `window.NRL_DATA` / `window.NRL_LEARNED` object out of the JS wrapper and
check the contract (see schemas below). Exit 0 = pass, 1 = fail. The workflow runs
both after generation and **refuses to publish on failure**. They tolerate minor JS
artifacts (trailing `;`, comments, trailing commas) but expect clean JSON otherwise.

---

## Data file schemas

### `nrl_data.js` → `window.NRL_DATA`
```
{
  updated: "YYYY-MM-DD",        // real generation date (validated ISO)
  season: 2026,                 // int
  round: 22,                    // int — the round being tipped; finals are 28..31
  roundName: "Round 22",        // display label: "Finals Week 1" … "Grand Final" (2026-09-07)
  finals: false,                // true for round >= 28 — byeTeams is [] and the
                                // validator accepts 1–4 fixtures (2026-09-07)
  source: "zerotackle.com",
  newsUpdated: "YYYY-MM-DD",    // set by --merge runs (optional)
  generatedAt: "ISO+offset",    // this run's stamp; its ABSENCE marks a pre-change
                                // payload, which suppresses the first diff so the
                                // feed doesn't report the whole file as "changed"
  teams: [ Team, ... ],         // exactly 17
  fixtures: [ Fixture, ... ],
  byeTeams: ["XXX", ...],       // exactly 1 for a 17-team comp
  changes: [ Change, ... ],     // optional; rolling 36h window, may be empty
  changesSince: "ISO+offset",   // optional; start of the window the feed covers
  results: [ Result, ... ]      // optional
}

Team = {
  name, short, colour,
  P, W, L, PF, PA, last5,       // last5 = wins in last 5 (0..5)
  home: {P,W,L,PF,PA} | null,   // home split (null if not parsed)
  away: {P,W,L,PF,PA} | null,
  news: "Player (Reason) — back Round N; ..." | null
}

Fixture = {
  home, away,                   // team short codes
  venue, city,                  // stadium name + host city ("" if unknown)
  kickoff,                      // ISO datetime WITH UTC OFFSET, or ""
  tz: "Australia/Brisbane",     // IANA zone of the ground (optional)
  odds: { open:{home,away}, close:{home,away} }   // or legacy {home,away}, or null
       ,
  weather: null,   // ALWAYS null since 2026-08-04 (feature removed); key kept for
                   // one deploy cycle so CDN-cached old pages don't break, then droppable
  h2h: null
}

Change = {
  id,                           // stable, unique within the array
  fixture: "NQL-SYD" | null,    // null = comp-wide
  team: "SYD" | null,
  cat,                          // in | out | injury | line | time | venue | other
                                // ("weather" is legacy — no longer emitted; the
                                //  front-end filters any leftover in the 36h window)
  sev: 1|2|3,                   // 3 = changes the tip's shape, 1 = trivia
  dir: "up"|"down"|"neutral",   // effect on `team`'s chances
  text,                         // the human-readable line
  pts: number | null            // model points swing, unsigned
}

Result = { season:int, round:int, home, away, hs:int, as:int }
                                // season added 2026-08-04; entries without it are
                                // read as 2026 by every consumer (back-compat)
```

> **`kickoff` must carry its UTC offset.** A naive `"2026-07-30T19:50:00"` is read by
> `Date.parse()` as the *reader's* local wall clock, so a phone outside AEST renders the
> wrong kick-off with no warning. And a fixed `+10:00` is wrong for half the year:
> Queensland doesn't observe DST but NSW does, so Townsville and Sydney diverge every
> summer. `parse_nrl.py` resolves the offset per ground via `zoneinfo` and emits `tz`
> alongside, so the front-end can label the zone and show "your time" when it differs.

> **The change feed is a rolling window, not a per-run snapshot.** The workflow runs
> every 4 hours; replacing `changes` each run would mean an overnight injury is gone by
> breakfast. Entries accumulate, dedupe on `id` keeping the **first** sighting's
> timestamp, purge on round rollover, and age out at 36h. Truncation to `CHANGES_MAX`
> sorts by **severity first** — sorting by timestamp first once let a spine player being
> ruled out get evicted within half an hour by a pile of trivia entries.
Required top-level fields (hard fail if missing): `updated, season, round, teams,
fixtures, byeTeams`. Decimal odds must be > 1. Every team must be either fixtured or
on bye. No team twice in a round.

### `nrl_learned.js` → `window.NRL_LEARNED`
```
{
  updated: "YYYY-MM-DD",
  gamesLearned: int,
  lowConfidence: bool,          // true while < 30 games — front-end then ignores params/elo
  params: { homeAdv, logisticScale, oddsWeight, eloK, eloHGA },  // logisticScale always 7 (pinned)
  elo: { <17 team shorts>: number },   // ratings, ~1500 baseline
  backtest: { games, brier, logloss, hit, marketBrier|null },
      // `lockTax: {games, modelRight, rkWins}` lived here 2026-08-04 -> 2026-09-12,
      // removed with the Roosters lock. Readers must tolerate its absence (they always
      // did - the front-end showed nothing rather than a hindsight number).
  history: [ {date, games, brier}, ... ],   // non-empty; one per fit
  results: [ {season, round, home, away, hs, as}, ... ]   // append-only match log
}
```
Sane ranges enforced by the validator: `homeAdv ∈ [-5,20]`, `logisticScale ∈ (0,50]`,
`eloK ∈ (0,100]`, `eloHGA ∈ [-50,400]`, elo ratings `∈ [0,4000]`, probabilities
`∈ [0,1]`.

### `nrl_tiplog.js` → `window.NRL_TIPLOG`
```
{ updated: ISO,
  tips:  [ {season, round, home, away, tip, prob, why, ko: ISO|null, ts: ISO}, ... ],  // ≤250, sorted
  flips: [ {season, round, home, away, from, to, fromProb, toProb, why, ts: ISO}, ... ] }  // ≤20, ≤48h
```
The **official pre-kick-off tip** per game, frozen by `freeze_tips.mjs` (workflow,
after `learn_model.py`): it runs the real `nrl-tipping-guide.html` + fresh data in
jsdom — **including the PRIOR committed `nrl_tiplog.js`** (2026-08-21: the comp
simulator reads the tiplog via `gradedTip()` and the incumbency tie-break, so a
tiplog-less page computes different tips than real browsers; see `GOTCHAS.md` "The
freeze must LOAD the prior tiplog") — and records `tipSide(predict(fx))` — plus the tipped side's blended win %
(`prob`) and a plain-text `whySummary()` (`why`) — for every game whose kick-off is
still in the future. **Since 2026-09-12 the freeze also forces the SYNCHRONOUS solver
path** — it sets `window.NRL_SYNC_PLAN` before the page's scripts and calls
`compPlanSync()` before reading tips. A browser may show a provisional plan for ~400ms
while the exact finals solver runs on an idle callback; the freeze publishes to every
device, so a provisional answer there would be the wrong tip everywhere.
Last pre-kick-off run wins; entries never change after
kick-off, **including when the feed blanks a fixture's kickoff mid-game** (nrl.com
does this while a game runs — a ko-less fresh entry never overwrites an existing
one). When a run's tip differs from the frozen one, a **flip** is recorded
(2026-08-08); the front-end surfaces flips at the top of the What's-new feed as
"Tip changed" entries. This file is what full-time grading and "Your tips" read on
every device. Generated — never hand-edit, never upload. Not gate-validated
(best-effort; front-end degrades to its `nrl_snap_v2` localStorage snapshot, and beyond
that says "no pre-game tip on record" — the lock rule that used to be the last fallback
was removed 2026-09-12).

### `nrl_comp.js` → `window.NRL_COMP`
```
{ round,                 // the round these picks/standings are for
  finishRound,           // last round of the comp (31 in 2026)
  fetched: ISO,
  roundIndexed: true,    // NEW 2026-09-12 — see below. Load-bearing.
  members: [ {
    name,                // footytips DISPLAY name only, never a surname
    me,                  // name === FOOTYTIPS_ME. The page re-derives this by name.
    rank, mv,            // ladder position, "up"|"down"|""
    roundScore,          // this round's score (null if not scored yet)
    totalScore,          // season points
    totalMargin,         // season CUMULATIVE MARGIN ERROR — the countback. LOWER wins.
    aff: {SHORT: [picked, seen], ...},   // season affinity: times tipped / times played
    margins: [ ... ],    // NEW — per-round margin ERROR.   length = round, index = round-1
    scores:  [ ... ],    // NEW — per-round score.          length = round, index = round-1
    mpreds:  [ ... ],    // NEW — the margin actually ENTERED, back-solved. same shape.
    beh: {a, b, loy, n, hit},            // NEW — fitted pick model. absent if not fitted.
    picks: {"A-B": SHORT, ...}           // unordered-pair keys, appear as games lock
  }, ... ] }
```

The family's footytips comp snapshot (public API, no auth), written by `cloud_fetch.py`
each run — standings, each member's picks for the round, and season affinity profiles
computed from rounds 1..N-1 (~23 extra GETs/run). Powers the comp-aware `tipSide()`
policy; shipping it as a data file is what makes the tip **deterministic** across the
browser and the jsdom freeze. Best-effort: failure keeps the committed copy, never
blocks a publish.

**`FOOTYTIPS_ME` = `"Brigitte"` since 2026-09-12** (it was `"Special unit"`, Josh). It
must stay in lockstep with `COMP_ME` in `nrl-tipping-guide.html`. A no-`me` file silently
disables every comp surface (`compPlan → mode:'off'` → `tipSide` degrades to `modelFav`),
so `build_comp_js` prints a stderr **WARNING** when the name matches nobody and the page
`console.warn`s on boot. Never fatal — the comp is not a publish gate.

#### The four fields added 2026-09-12 (all from data already fetched — no extra HTTP)

- **`totalMargin`** — the season cumulative margin error. footytips' `rankByMargin`
  breaks a points tie in favour of the **lower** value, and that countback is the whole
  reason the tip policy is as aggressive as it is (Brigitte 476 vs Claire 492 at the
  rebuild). Was previously only read from the raw file by `compMarginOf()`;
  `compFromFile()` and `pollComp()` both map it now, so a mid-round live poll no longer
  prices ties on a stale countback.
- **`margins[]` / `scores[]`** — per-round history, straight out of `results[].rounds[]`
  of the response the scraper already reads. Feeds `finalsTieProbs()` (the standard
  deviation of the per-round margin-error difference) and the exact per-member accuracy.
- **`mpreds[]`** — the margin each member *actually entered* per round, **back-solved**.
  footytips publishes only `|predicted − actual|`; the candidate whose sign agrees with
  the side they tipped is the number they typed (`_margin_pred()`). The round's
  designated margin game is its **first** game — verified against every member's
  published error in R24–R28. This drives the habit hint on the margin line, and it is
  how the app found that Brigitte enters **"4" every single week**. `null` where it
  could not be recovered.
- **`beh: {a, b, loy, n, hit}`** — the per-member behavioural pick model,
  `P(tips home) = sigmoid(a + b·lp + loy·(affShare(home) − affShare(away)))`, where `lp`
  is the game's Elo logit. Fitted by plain Newton with an L2 ridge (`BEH_RIDGE = 0.25`)
  on a 3×3 system in **pure Python** — the workflow runner has only `requests` +
  `beautifulsoup4`, no numpy. `n` = training rows, `hit` = in-sample hit rate.
  Members with fewer than `BEH_MIN_PICKS = 20` picks ship **no `beh` key** and the page
  falls back to `predictPick()` at that member's herd rate. 2026 values: `b` 0.31–1.60,
  `loy` 2.16–5.09, `hit` 0.70–0.83, `n` 198–204.
  > **`BEH_AFF_K` (4.0) MUST be identical in `cloud_fetch.py` and the page** — the fit
  > and the evaluation have to see one and the same covariate. Both files say so at the
  > constant. And the loyalty covariate is **leave-one-out** in the fit: a member's
  > affinity share for a team is literally the mean of their own picks in that team's
  > games, so raw it is a perfect in-sample predictor and drives `b` to exactly 0.

#### `roundIndexed: true` — why the flag exists

`margins[]`, `scores[]` and `mpreds[]` are **length `round`, index = round−1, `null`
where there is nothing to record**. They originally shipped dense (empty rounds filtered
out), which gave members different lengths — and `finalsTieProbs()` zips them
**positionally**, so one member's round 6 was compared against another's round 8. The two
formats are indistinguishable by inspection whenever no round happens to be missing, so
the flag is load-bearing: every consumer **refuses to zip without it** and falls back to
the season-total mean with sd 10 (imprecise rather than quietly wrong). Producer:
`_by_round()`; the live-poll mirror in the page is `byRound()`. Keep them identical.

### `nrl_players.js` → `window.NRL_PLAYERS`
```
{ "player name (normalised)": { pos: "Halfback", pct: 84.1 }, ... }
```
- `pos` ∈ the closed set: Fullback, Halfback, Five-eighth, Hooker, Winger, Centre,
  Second-row, Prop, Lock.
- `pct` = the player's overall rating percentage (higher = better).
- Key is the normalised full name (lowercase, accents stripped, apostrophes/hyphens
  kept) — matches the injury-feed names.
- **Not validated** by a gate script (optional, front-end degrades gracefully), but the
  workflow's `git add -A` commits it each run.

---

## Local commands (for reference)

```bash
# Full rebuild from dumps
python3 parse_nrl.py --ladder ladder_dump.html --draw draw_dump.html \
  --draw-meta draw_meta.json --odds odds_dump.txt \
  --injuries injuries_dump.html --results results_dump.txt \
  --out nrl_data.js --season 2026 --source zerotackle.com

# Daily reactive refresh (odds/news only)
python3 parse_nrl.py --merge --in nrl_data.js \
  --odds odds_dump.txt --injuries injuries_dump.html

# Re-fit the learning loop
python3 learn_model.py            # reads/writes nrl_learned.js

# Validate before publishing
python3 validate_data.py nrl_data.js
python3 validate_learned.py nrl_learned.js
```

> **Network availability varies by sandbox — check, don't assume.** This note used to
> say flatly that the editing sandbox has no outbound network and that `cloud_fetch.py`
> could only be exercised on GitHub. On 2026-07-29 a full live run (zerotackle.com,
> nrl.com and Open-Meteo) completed from the editing sandbox. Try the live fetch first;
> only fall back to saved/synthetic HTML if it genuinely fails. Believing this note
> without testing it is how the odds bug survived — nobody ran the scraper end to end.
> The pure scripts (parse/learn/validate) run fine anywhere.
