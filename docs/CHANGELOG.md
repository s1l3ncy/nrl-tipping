# Changelog & decision log

Dated record of the significant changes and *why* they were made, so a future reader
understands the reasoning, not just the diff. Newest first.

---

## 2026-07-30 (pm2) — Full UI rebuild: tab-bar app, new cards, a real app icon

Josh: "full redesign… a proper full rebuild that looks more modern and different…
happy with a different layout altogether", plus "the home-screen icon is a black N".
All in `nrl-tipping-guide.html` + `sw.js` + two new PNGs; the render pipeline, model
maths, element IDs and all data files are untouched.

- **It's an app now, not a page.** Four screens behind a fixed bottom tab bar — Tips
  (hero, game cards, quick list), What's new (the change feed, with a red unread-count
  badge on the tab), Ladder (table + advanced settings, no longer collapsed), Model
  (accuracy, Roosters tax, learning panel). Screens are plain show/hide wrappers; every
  `render()` target ID is where it always was, so the whole render pipeline is
  untouched. Last tab remembered in localStorage (`nrl_tab_v1`); a card's "⟳ N changes"
  badge switches to What's new and anchors to that game; print flattens all screens.
- **The game card is rebuilt.** Kick-off + venue topline, crest-led matchup, and a
  full-width win-probability bar that fills from the TIPPED side — **gold for the locked
  Roosters game, red otherwise** — then a TIP pill and one confidence line. The
  ring/three-column layout is gone (its CSS remains as dead rules; the classes left the
  markup). Below the fold nothing changed: odds bars, injuries, venue, the why ledger.
- **Visual system**: aurora-lit navy, frosted-glass surfaces, tricolour hairlines, big
  gradient display titles. Colour meaning is strict: red = tip/brand, gold = the lock
  only, green = genuinely good news, blue = market, amber = doubt.
- **A real app icon.** Geometric rooster head (red comb/wattle, white face, gold beak,
  navy field, tricolour base hoop) drawn as SVG, shipped as `apple-touch-icon.png`
  (180px) + `favicon-32.png` and linked from the HTML — replaces iOS's fallback letter
  tile. `sw.js` CACHE bumped v3→v4 and precaches both; existing home-screen installs
  may need a remove/re-add to refresh the icon (iOS caches them).

Tested: 60/60 smoke, 9/9 injury-logic assertions, both script blocks `node --check`
clean, headless-Chromium pass over all four screens (8 cards, 8 bars, 1 gold, badge
= feed count, zero console errors).

---

## 2026-07-30 (pm) — The feed and the "why" box read like logs; now they read like sentences

Josh, after the odds/weather ship went live: the change feed is "a very long list…
clutters things up", the "since 2:55am" clock isn't visibly AEST, and "why the model
leans this way" is too much roster arithmetic — "a short summary should be better".
All three in `nrl-tipping-guide.html`; no data-format changes.

- **The feed folds.** The top ~8 rows (already sorted severity-first, so the fold can't
  hide a sev-3) render as before; everything else — including the minor-updates tally —
  sits behind a native `<details>` ("36 more updates — show"). No JS state, no
  localStorage, works offline. A leftover of ≤2 rows just shows rather than folding.
- **The clock is pinned to Sydney and says so.** `fmtClock()` used the *viewer's* local
  zone with no label — right for Josh at home, silently wrong on any device set
  elsewhere. Now `Australia/Sydney` via `Intl`, labelled AEST/AEDT (DST-correct), with
  "yesterday"/weekday prefixes when the window opened on an earlier day.
- **The "why" box leads with words, not rows.** New `whySummary()` writes one–two
  sentences naming the biggest drivers by size — strength/form, home ground, team news,
  weather trim, and whether the bookies agree — e.g. *"Mostly Storm rating the stronger
  side, plus the home-ground edge. The bookies read it the same way."* The full itemised
  ledger (engine caption, rows, weather/odds modifiers, net line, check line) is intact
  behind "Show the working". **The 🔒 lock line stays outside the fold** — it must never
  be hidden.

Tested: `node --check` clean; harnessed `whySummary`/`fmtClock` across engines, doubt
states and zones; full headless-Chromium render against the live data files — 8 cards,
8 summaries, ledger folded, feed capped at 8 rows, zero console errors.

---

## 2026-07-30 — Odds were geo-blocked; weather was for the wrong day; a doubt during a live game

Josh's Thursday-night report: "no bookmaker price yet, usually drops Tuesday" (on a
Thursday), and Tom Dearden shown as a *doubt* under team news while the Cowboys game he
wasn't playing in was actually underway.

**1. Odds never arrived because nrl.com geo-blocks them (`cloud_fetch.py`,
`update-nrl.yml`, `parse_nrl.py`).** The 2026-07-29 odds scrape was verified working from
an Australian machine and produced *nothing* in production: workflow run #28 committed a
perfect `draw_meta.json` (venue + kick-off 8/8) and no `odds_dump.txt` at all, from the
same code against the same endpoint in the same minute. The difference is the egress IP —
GitHub's runners are US-based and **nrl.com withholds bookmaker prices from non-Australian
traffic** (as Australia's gambling-advertising rules require of it). An Australian sandbox
cannot reproduce this failure. Odds now come from **The Odds API**
(`api.the-odds-api.com`, aggregates the AU books, geo-independent) as the primary source,
with nrl.com kept as a costless fallback. Requires the `ODDS_API_KEY` repo secret
(Settings → Secrets and variables → Actions); free tier is 500 requests/month against
~240 used. Missing/bad key/exhausted quota are all **non-fatal**: the run logs why, odds
stay null, everything else publishes. `odds_api_status.json` (never the key) is folded
into `last_run.json` so quota burn is visible. *This work was actually written on
2026-07-29 but sat unshipped and undocumented in the local folder — the batch that went
up carried only the code that works from Australia.*

**2. A doubt is an OUT once the team list says so (`nrl-tipping-guide.html`).** The
injury feed listed "Tom Dearden (Ankle)" with no timeframe → a doubt at half weight. But
the Round 22 team lists were long published and he wasn't in the Cowboys' 17 — the app
knew, and still called him a doubt, because `namedSquad()` was only used one-way (a named
player cancels his injury entry). Now, once a club's squad for the round being tipped is
published, an unconfirmed doubt who is NOT in it counts as a confirmed absence at full
weight, badged **NOT NAMED**. Pre-Tuesday (no squad yet) nothing changes; dated returns
and suspensions were always full weight and are untouched.

**3. Weather now describes the day the game is played (`cloud_fetch.py`,
`parse_nrl.py`).** "Wettest of the next ~6 days" predates having kick-off times; with
real kick-offs on every fixture it was showing (and shrinking the model by) Saturday's
rain for a Thursday game — every fixture in Round 22 carried a forecast for a wrong day.
`fetch_weather()` now resolves each game's local date from its kick-off (via the API's
own `utc_offset_seconds`, no tz table) and emits `City|YYYY-MM-DD:` lines;
`apply_weather()` matches city + kick-off date, falling back to the legacy dateless
`City:` line (still emitted per city) so old dumps and kickoff-less fixtures degrade
unchanged. Also: a per-city Open-Meteo timeout now *keeps* that city's committed dump
line instead of blanking the forecast for 4 hours (which also re-fired the change feed's
"first forecast" entry on return) — the same keep-if-thin courtesy every other dump had.

**4. Change-feed polish (`parse_nrl.py`, `nrl-tipping-guide.html`).** Two fixtures in
the same city on the same day emitted the identical "Forecast for Sydney updated"
sentence twice; a shared forecast is now ONE comp-wide entry keyed on city+day+band. And
the odds box only promises "prices usually land around Tuesday" while kick-off is more
than 48h away — past that it says plainly there's no price for this game.

Tested: full live pipeline (fetch → parse → learn → both validators, PASS) in a scratch
dir; 9/9 targeted injury-logic assertions; smoke_test 60/60; `node --check` clean.
*Also discovered: the 2026-07-29 batch's `docs/` pack, CLAUDE.md and HANDOFF.md were
never actually uploaded — this batch carries them.*

---

## 2026-07-29 — The Roosters lock was cosmetic; the change feed evicted its own signal

Two blockers found by review of the four front-end changes, plus four smaller fixes.

**1. The lock didn't lock (`nrl-tipping-guide.html`).** Four surfaces each computed the
tip as `p.pHome>=0.5?p.h:p.a` and then merely *annotated* the Roosters game. Latent while
the heuristic engine happened to favour the Roosters — but on the Elo engine (which the
model flips to at ~30 games) the model favours the Cowboys in Round 22, and **"Copy tips"
emitted `Cowboys v Roosters → Cowboys (locked)`**: the opponent, labelled as the locked
pick, straight into Josh's tipping comp. The ledger also painted the case *for the
opponent* green ("for") and the Roosters' own edge amber, directly above the line "🔒
Locked: the Roosters are tipped". And the "Roosters tax" was comparing the model against
a lock that was never applied. Fixed with one shared helper, `tipSide(p)` (see MODEL.md
§6), routed through quicklist, `cardHTML`, `copyTips` and `whyHTML`. `lockHero`,
`rationale()`, `oddsHTML`'s `fav`/`keen` and `modelFavoursHome()` were left alone **on
purpose** — those describe the *model*, and that honesty is what makes "⚠ Risky this week"
and the tax meaningful.

**2. The change feed shed signal, not trivia (`parse_nrl.py`).** `merge_changes()` sorted
by `(ts, sev)`, so severity only broke ties inside the same second and gave no protection
at all against the `CHANGES_MAX = 60` truncation. Compounding it, `build_changes()`
emitted a weather entry on *any* forecast-string difference (a 1°C wobble) and id'd it by
a hash of that string, so every wobble minted a new entry: 8 fixtures × 6 runs a day = up
to 48 sev-1 rows a day against a 60-slot window. Reproduced over 16 runs at the real
4-hour cadence: a sev-3 "Cleary is out of the 17" entry was **evicted 16 hours into its
36-hour window**. Now sorted `(sev, ts)` — the cap sheds trivia — and weather is emitted
only when the rain figure crosses a **20-point band** (the threshold `weatherEffect()`
actually uses), keyed by band so re-forecasts inside a band collapse instead of
accumulating. Same simulation: the injury survives all ten runs of its window and ages out
exactly on time; weather entries drop from 30 to 0. Display order is unaffected — the
front-end re-sorts and groups for itself (DESIGN_SPEC §2.4).

**Also fixed:** the ledger's check line now sums the values **as printed** (`+0.1 − 4.3 =
−4.1` and rows hidden by the 0.15 filter are gone; 12,000 randomised cards, 0 mismatches);
`resolveOdds()` validates a close price before preferring it, so a half-written close no
longer throws away a good open (a string price used to crash `toFixed`); `oddsHTML` only
claims "money came for X" when exactly one side shortened; the dead `injurySentence()` —
the file's last unescaped interpolation of scraped player names — is deleted;
`cloud_fetch.py`'s draw gate now refuses to shrink the committed dump for the same round
(a 6-of-8 partial parse used to overwrite it); `changesSince` no longer reads "18 updates
since 8:42 pm" on a run at 8:42 pm; and `changes:null` gets the same empty state as a
missing field. The model's numbers are byte-identical before and after across both
engines (3,216 fixture-rows checked).

---

## 2026-07-28 (pm5) — Team-list parser rewritten (it was reading the footer menu)

First live run of pm4 confirmed the big fixes: **524 rated players, 100% full-name keys**
(injuries actually move tips now) and **17 clubs of injury news** (was silently returning
`{}`). But team lists came back as `1 clubs — WST: 15 named v PAR`.

Cause: **the squads are `<table>`s; the article contains no `<ul>`/`<li>` at all.** The
parser was written against a markdown rendering of the page, which displays the table rows
as `- ` bullets. So seven of the eight games found nothing, and the eighth — having no
following heading to stop its forward scan — ran off the end of the article into the site's
**footer mega-menu** and accepted `/players/oldest-youngest/`-style links as a squad. The
"15 Wests Tigers players" were menu labels like "Off Contract 2026".

Rewritten with the traversal inverted: find squad containers first by what they *contain*
(≥13 player links **and** ≥13 bare jersey numbers — the number requirement is what makes a
nav menu structurally impossible to mistake for a team list), then attach each to its
nearest *preceding* heading. Row parsing dropped entirely in favour of a `.descendants`
token walk, because Zero Tackle leaves `<tr>` unclosed and `html.parser` therefore nests
every row inside the previous one. Home/away decided by number-before vs number-after
orientation rather than document order, so a half-published game still lands on the right
club. Squads cut at the `RESERVES` separator, **not** at jersey ≤ 17 — Parramatta named #22
at centre in Round 21 while #11 and #14 were on the bench.

Tested against a byte-faithful fixture of the real Round 22 article: 16/16 clubs, reciprocal
opponents, 19–22 names each, zero menu junk, and `{}` for empty / pre-release / menu-only
pages so the existing guard keeps the committed file. File: `cloud_fetch.py`.

---

## 2026-07-28 (pm4) — Injuries were silently inert; schedule was dropping runs; injuries UI rebuilt

Three problems, investigated together because they presented as one ("team lists came out
and nothing changed").

**1. `nrl_players.js` was corrupt, so no injury has moved a tip in weeks.** Every key in
the published file was a **first name only** (`"nathan"`, `"harry"`, `"payne"`). Cause:
`extract_ratings()`'s primary path read `cells[1]` as the name, but the `/overall/` ratings
page splits a player's name across **two** cells — so it captured just the given name. The
front-end looks players up by full normalised name, so *every* lookup missed and every
injured player fell through to the 0.6pt fringe fallback. Melbourne losing Munster **and**
Grant scored 1.4 — identical to a club missing two rotation forwards. And because the
primary path still returned >50 rows, the (correct) text fallback never ran.
Fix: ratings now come from the **nine per-position pages** (`/nrl-player-ratings/halfback/`
etc), where the position is implied by the URL and the name is taken from the
`/players/<slug>/` **anchor**, never a cell index. A punctuation-free alias is emitted
alongside each key (`sean osullivan` next to `sean o'sullivan`) for free matching.
Verified: MEL with Munster + Grant out now scores **5.9**, not 1.4.

**2. The publish guard was volume-only, which is what let it run for weeks.**
`if len(players) >= 100` was true for a page of garbage keys. Now it also requires **≥80%
of keys to contain a space**, and failure prints an explicit ERROR saying injuries won't be
weighted until it's fixed. A key that isn't a full name can never match the front-end, so
it is a failed parse by definition.

**3. `extract_injuries()` was returning `{}`.** Zero Tackle labels each club on the
injuries page with a bare `<a>` to its team page — **not** a heading — so heading-tracking
never set `current` and the whole parse fell through to the committed file every run. Now
each table is attributed to the **nearest preceding team link** (`club_before()`), with
heading-tracking kept only as a fallback. Also dropped `"team list"` from `NOISE` (verified:
the only occurrence on that page is the site-nav link, which the parser never reads).

**4. Team lists were never scraped at all.** New `extract_teamlists()` finds the newest
`/round-N-team-lists-2026-<id>/` article from the section index and parses the named 1–17
per club into a new generated file, **`nrl_lineups.js`**. The front-end uses it to cancel an
injury-table entry for anyone actually **named in the side** — without it a season-long
"TBC" kept a fit player permanently half-out. Deliberately a *separate* file rather than a
new `nrl_data.js` field, so the schema, `parse_nrl.py` and `validate_data.py` are untouched.
`namedSquad()` ignores lineups whose round doesn't match the round being tipped, so stale
data can never leak into a tip.

**5. The schedule wasn't broken — GitHub was dropping it.** The workflow is `active`, on
`main`, and has never failed. But of the only two cron slots that existed, the 06:00 one ran
**3h44m late** and the noon one **never fired**. Both were on minute `:00`, the most
congested minute on GitHub's best-effort queue. Now: **every 4 hours at `:17`**, plus an
early-morning slot and a **Tuesday 16:23 Sydney** slot timed for the ~4pm team-list drop.
Running often is also immune to the AEST/AEDT switch that used to drag "6am" to 7am for half
the year. Added a **`last_run.json` heartbeat** that changes every run, so "no commit" now
unambiguously means "the job didn't run" rather than "it ran and nothing changed" — that
ambiguity is precisely what hid this for weeks. Added an **auto-filed issue on failure**, and
a `keepalive.yml` that re-enables the workflow fortnightly (bot pushes via `GITHUB_TOKEN`
do **not** reset the 60-day inactivity timer).

**6. Injuries UI rebuilt.** `injuryPenalty()` already produced a ranked list with name,
position, impact and confirmed-vs-doubt — and then discarded it, printing the raw news
string **twice per card** plus a third summary sentence. With the real scraper's output
that's ~500 characters of undifferentiated amber prose on the front of all 8 cards. Now the
card front is a **pill strip** shown only when injuries actually move the model, and the
details panel is a **ranked roster list** (name / position / OUT|DOUBT pill, one cost number
per team). Raw source string kept once as a footnote. Also added `looksLikePlayer()`, which
stops prose fragments like "near full strength" being scored as phantom doubtful players
worth ~0.3pts each — a real, if small, tip correction.

Files: `cloud_fetch.py`, `nrl-tipping-guide.html`, `sw.js` (cache `v2` + new file),
`.github/workflows/update-nrl.yml`, `.github/workflows/keepalive.yml`, `nrl_lineups.js` (new).

---

## 2026-07-28 (pm3) — Fix stale form dots (localStorage key collision)

After the backfill lit up real form, the dots still showed grey on already-open installs.
Cause: the front-end cached team data in `localStorage` under a **date-based** key, and the
workflow runs several times a day under the same date — so an earlier same-day snapshot
(form=0, pre-backfill) was restored and **shadowed the fresh data**, while the Elo number
(read straight from `nrl_learned.js`) updated regardless. That's the exact "50% + grey dots"
symptom. Fix: the key now includes a **content signature** of the data (`dataSig`), so any
real change invalidates the cache and the fresh file wins; stale keys are pruned.
File: `nrl-tipping-guide.html`.

Also confirmed this run: the results backfill worked — **156 games** in memory,
`lowConfidence: false`, so the model is now running its fitted **Elo** engine. The Rd22
NQL v SYD game grading ~50% is the Elo model's genuine read (Roosters better but away, with
more confirmed injuries than the Cowboys), not a fault.

---

## 2026-07-28 (pm2) — Scrape finished results → real form, real splits, growing model

Found the deeper cause of the empty form dots: **the results memory wasn't growing at
all.** The draw dump only carries the upcoming round's fixtures (no scores), so
`parse_nrl` never had finished games to append — the learning loop was frozen at its
7-game seed, and the form/splits derived from it were near-empty.

**Fix.** `cloud_fetch.py` now scrapes every finished game's score from the Zero Tackle
fixtures/results page (`extract_results` / `emit_results`) into a new `results_dump.txt`,
and the workflow feeds it to `parse_nrl` via `--results`. That backfills the whole season
into the results memory, which (a) makes `last5` form and home/away splits real, and
(b) grows the memory past the ~30-game threshold so the learning loop switches from the
hand-tuned heuristic into its fitted **Elo** model — a big but intended upgrade that will
shift the numbers across every game.

**Files.** `cloud_fetch.py`, `.github/workflows/update-nrl.yml`; new generated file
`results_dump.txt`. **First-run check:** the Actions log should print
`wrote results_dump.txt: N finished games…`, and after `learn_model` runs, `nrl_learned.js`
should show `lowConfidence: false` once >30 games are in memory.

---

## 2026-07-28 (pm) — Audit fixes: revived form + splits, injury confidence, history dedup

A full audit (`docs/AUDIT.md`) found several model inputs silently receiving no data.

- **Recent form + home/away splits were never fed.** `cloud_fetch.py` emitted an empty
  form cell and no split tables, so `last5` was always 0 and `home`/`away` always null —
  the form nudge and venue-adjustment did nothing. Now derived in `parse_nrl.py` from the
  append-only results memory (`derive_form_and_splits`); partial early, sharpening as the
  season logs games, with `splitWeight` keeping thin samples from dominating.
- **Injuries now weight confidence.** Confirmed absences (dated return / long-term /
  suspension) count in full; a player merely listed with no timeframe counts at half
  weight (`UNCONFIRMED_WEIGHT = 0.5`). This alone moves the Rd22 NQL v SYD game from
  ~72% to ~63% — the principled version of the number Josh expected, because Dearden and
  Mahoney were unconfirmed knocks.
- **Learned history no longer duplicates.** `learn_model.py` records a new trend point
  only when games/brier change, and collapses existing consecutive duplicates.

**Files.** `parse_nrl.py`, `nrl-tipping-guide.html`, `learn_model.py`, plus `docs/AUDIT.md`.

---

## 2026-07-28 — Fresh-data fixes: correct dates + an auto-updating home-screen app

**Problems.** (1) The site showed a date one day behind after the early run. (2) The
iPhone "Add to Home Screen" app kept replaying stale data and wouldn't refresh even on
a force-quit.

**Root causes.** (1) `parse_nrl.py` stamped `updated` with `datetime.date.today()`,
which on GitHub's **UTC** runners returns the previous calendar day for the 06:00 Sydney
cron (it fires at 20:00 UTC the day before). (2) There was no service worker and the data
files were plain `<script src>` tags; iOS standalone web apps keep their own aggressive
cache that a force-quit doesn't clear.

**Fixes.**
- *Date:* new `local_today_iso()` helper in `parse_nrl.py` stamps dates in
  `Australia/Sydney` via `zoneinfo`; the workflow also pins `TZ: Australia/Sydney` for
  the whole job, so `learn_model.py` and `cloud_fetch.py` are correct too.
- *Freshness (runtime):* the front-end still loads data instantly from `<script src>`
  for offline/first paint, but on each online launch `refreshFromNetwork()` re-pulls the
  three data files with a `?v=<ts>` cache-buster and re-renders. Derived state was made
  re-computable via `hydrateData()`.
- *Freshness (shell):* added **`sw.js`**, a network-first service worker that
  auto-updates the shell + data whenever online and falls back to cache offline.
  Registered only over http(s), so opening the page as a local file is unchanged.

**Files touched.** `parse_nrl.py`, `.github/workflows/update-nrl.yml`,
`nrl-tipping-guide.html`, new `sw.js`.

**One-time step.** Because the *old* cached shell has no service worker, the phone must
load the new HTML once (re-add to home screen, or open in Safari) after deploying. From
then on the worker keeps everything current automatically.

**Also (same day).** UI declutter pass — tighter palette (green = the tip, red reserved
for the Roosters lock), unified type weights, roomier game cards.

---

## 2026-07-27 — Injuries and weather now genuinely affect the tip (position × rating)

**Motivation.** Josh asked, correctly, why injuries barely moved the pick and insisted a
star going down should swing the tip far more than a bench player. The old
`injuryPenalty` only fired on keywords like "ruled out" and never matched the scraped
`Player (Reason) — back Round N` format, so injuries were effectively inert; weather was
display-only.

**Expert-panel decision.** Three "expert" perspectives (an NRL football analyst, a
betting quant, and a calibration data scientist) converged on a method:
- Count only players **actually out for this round** (via the expected-return round).
- Weight each by **role** (spine heaviest → edge → forward) with **diminishing returns**
  on stacking and a **per-team cap**.
- Apply to the **model margin before the odds blend** so bookmakers don't double-count.
- **Weather shrinks confidence, never picks a side** (no per-team wet-weather data).
- Parse defensively; anything unparseable is a no-op.

**The data gap and how it was solved.** The injury feed has no position, so true role
weighting looked impossible. Solution: scrape Zero Tackle's **overall player-ratings**
page (which lists every player's position *and* a rating) into a new `nrl_players.js`
map, and weight each injury by the real player: `base(position) × quality(rating)`, with
diminishing returns `[1,0.65,0.4,0.25,0.12]` and a team cap of 6.5. Net effect: Nathan
Cleary (spine, 84) out ≈ −4.3 pts; a bench prop ≈ −0.9. Weather reads rain % and shrinks
the margin up to −22%.

**Files touched.** `nrl-tipping-guide.html` (`injuryPenalty` rewrite + `playerImpact`,
`normName`, `weatherEffect`, `predict` wiring), `cloud_fetch.py` (new `extract_ratings`
+ `emit_players` + ratings fetch; injuries cap raised 3→6), new `nrl_players.js`.

**Gotcha found & fixed during rollout.** First ratings run produced first-name-only keys
because the parser looked for player-profile links that don't exist on that table; fixed
by reading the row cells positionally. See `GOTCHAS.md`. Verified live: ~380 players with
correct full names, positions and ratings; injury names match the map.

**Also produced.** This documentation pack (`HANDOFF.md` + `docs/`).

---

## Earlier milestones (condensed)

The project was built up in stages before the dated entry above. Roughly in order:

- **Core app.** Single-file HTML tipping guide with the hard **Roosters-always-tipped**
  rule; heuristic team ratings (season margin + home/away split + recent form) → win
  probability; power-ratings ladder.
- **Auto-updating data pipeline.** `parse_nrl.py` (dumps → `nrl_data.js`) with graceful
  degradation and a 17-team validity gate; `validate_data.py` as the publish gate.
- **Hosting so the Mac can be off.** GitHub Actions + Pages; `cloud_fetch.py` scrapes
  Zero Tackle (ladder/fixtures/injuries) + Open-Meteo (weather) on GitHub's servers;
  auto-advancing round; commit-back via `GITHUB_TOKEN`.
- **Richer per-game detail (schema v3).** Added club colours, home/away splits, injury
  `news`, host city, weather, and bookmaker odds; odds later extended to an
  `{open, close}` shape for **closing-line-value (CLV)** tracking.
- **Reactive daily refresh.** `parse_nrl.py --merge` updates only odds/news/weather
  without rebuilding the ladder/round; schedule set to 06:00 + 12:00 Sydney.
- **Learning loop.** Append-only match memory in `nrl_learned.js`; `learn_model.py`
  replays Elo, grid-searches params, backtests (Brier/log-loss/hit), appends a history
  snapshot; `lowConfidence` guardrail under ~30 games; `validate_learned.py` gate; a
  "what it's learned" panel in the UI.
- **UI redesign.** Dark "Apple Sports"-style, iPhone-optimised (safe-area insets, PWA
  metas), auto-selected round (no round picker), "Copy tips", upset-of-the-week,
  "Roosters tax" stat, model-vs-lock accuracy tracker, draws counted as pushes.

For the fuller original write-ups see `README.md`, `SPEC.md`, `MODEL_IMPROVEMENTS.md`,
and `WEEKLY_UPDATE.md`. Where those disagree with the current code (e.g. the older
injury description), the `docs/` pack and the code are authoritative.
