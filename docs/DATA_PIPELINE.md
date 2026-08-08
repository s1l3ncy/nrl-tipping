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
| `draw_dump.html` | Zero Tackle fixtures/results | The **lowest round with unplayed games** → auto-advances weekly. Written only if 6–9 fixtures parse **and** the count isn't lower than the already-committed dump for that round (so a half-resolved fallback can't shrink a good file). |
| `odds_dump.txt` | **The Odds API** (primary), nrl.com draw payload (fallback) | `Home v Away: 2.52 / 1.53` decimal head-to-head prices (median across the AU books when from the API). A fixture is omitted entirely until its market opens. Fed to `parse_nrl` via `--odds`. A stale dump from a *different* round is cleared, not reused. **The API needs the `ODDS_API_KEY` repo secret** — nrl.com withholds prices from non-Australian IPs, so on GitHub's US runners the fallback alone yields nothing (see `GOTCHAS.md`). Non-fatal on every failure. |
| `odds_api_status.json` | The Odds API response headers | How the odds call went: `state` (`ok`/`no-key`/`bad-key`/`quota-exhausted`/…) + the monthly-quota counters. Folded into `last_run.json`. **Never contains the key.** |
| `draw_meta.json` | **nrl.com draw payload** | Per fixture: `venue`, `venueCity`, and the UTC kick-off. Fed to `parse_nrl` via `--draw-meta`. This is the only source of stadium + kick-off — Zero Tackle's page doesn't carry them in a parseable form. |
| `nrl_lineups.js` | Zero Tackle round team-lists article | The named squad per club. The previous copy is snapshotted to `nrl_lineups.prev.js` **before** the rewrite, so the change feed can diff named/omitted players. |
| `results_dump.txt` | Zero Tackle fixtures/results (same page) | Every **finished** game's score as `Round N` + `Home hs - Away aws` (teams+round from the `fulltime-…` slug, scores from the `FT` block). Fed to `parse_nrl` via `--results`; grows the results memory that powers form, splits and Elo. Kept if ≥ 8 games parse. |
| `injuries_dump.html` | Zero Tackle injuries & suspensions | `Team: Player (Reason) — back Round N; ...` (up to 6 per club). Return of `TBC`/unknown is left as no "— back" suffix. Kept if ≥ 6 clubs parse. Rows whose cells are all ≤2 chars are rejected, and the player cell must look like a real name (≥2 words / ≥4 letters / a `/players/` link) — a Panthers stats table once published phantom player "P" (2026-08-04). |
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
`CLUB_COLOUR`, `TEAM_HOME_CITY`, `VENUE_CITY`. Add new venues to `VENUE_CITY` if a
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
The Elo replay's MOV multiplier is winner-relative (upsets amplified). The backtest
also publishes `lockTax` (walk-forward loyalty-tax counts from pre-game Elos).
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
  round: 22,                    // int — the round being tipped
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
  backtest: { games, brier, logloss, hit, marketBrier|null,
              lockTax: {games, modelRight, rkWins} },  // walk-forward loyalty tax (2026-08-04)
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
jsdom and records `tipSide(predict(fx))` — plus the tipped side's blended win %
(`prob`) and a plain-text `whySummary()` (`why`) — for every game whose kick-off is
still in the future. Last pre-kick-off run wins; entries never change after
kick-off, **including when the feed blanks a fixture's kickoff mid-game** (nrl.com
does this while a game runs — a ko-less fresh entry never overwrites an existing
one). When a run's tip differs from the frozen one, a **flip** is recorded
(2026-08-08); the front-end surfaces flips at the top of the What's-new feed as
"Tip changed" entries. This file is what full-time grading and "Your tips" read on
every device. Generated — never hand-edit, never upload. Not gate-validated
(best-effort; front-end degrades to its localStorage snapshot + the lock rule).

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
