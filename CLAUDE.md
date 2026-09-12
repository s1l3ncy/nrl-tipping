# Project instructions — NRL Footy Tipping app

**New here? Read `HANDOFF.md` first, then the relevant file in `docs/`.** This file is
the quick operating brief; `HANDOFF.md` + `docs/` are the full detail.

## What this is
A personal NRL footy-tipping web app. One self-contained HTML page
(`nrl-tipping-guide.html`) + three generated JS data files, scraped and rebuilt twice a
day by a GitHub Actions job and hosted free on GitHub Pages, so it stays current with
the owner's Mac off.

- Live site: https://s1l3ncy.github.io/nrl-tipping/
- Repo: https://github.com/s1l3ncy/nrl-tipping (public — keep it public)
- **Owner: Josh** (GitHub `s1l3ncy`) — he owns the repo, the GitHub account, the
  `ODDS_API_KEY` and every deploy. Roosters supporter.
- **User: Brigitte** (Josh's wife; footytips display name exactly `Brigitte`) — since
  2026-09-12 the app plays *for her*. She has no club loyalties: *"she really wants to
  win."* Josh is now just another rival in the comp ("Special unit").
- Season: 2026.

## Golden rules (do not break these)
1. **The objective is P(Brigitte finishes 1st) in the footytips comp — nothing else.**
   No top-3 term, no top-4 term, **no team is ever force-tipped**. `LOCK_MODE` is
   `"off"`; its only other setting, `"tiebreak"`, prefers the Roosters *only* on exact
   indifference and is verified to cost nothing. Never reintroduce a loyalty pick.
   *(Superseded 2026-09-12: rule 1 used to read "The Sydney Roosters (`SYD`) are ALWAYS
   tipped in their own game. Never 'fix' it." That was Josh's app. Tipping the Roosters
   in the R28 qualifying final was measured at **−6.5 points of comp-win chance** — the
   single most expensive decision on the board.)*
2. **The live site is `index.html`, a generated copy of `nrl-tipping-guide.html`.**
   Editing the guide changes nothing live until the workflow runs `cp … index.html`.
   So after any HTML change, **run the workflow**.
3. **Never hand-edit generated files:** `index.html`, `nrl_data.js`, `nrl_learned.js`,
   `nrl_players.js`, `nrl_tiplog.js` — they're overwritten each run.
   3b. **Finals are rounds 28–31 and every round is a NUMBER in the data** — the
   human name (`roundName`) is display-only. Any new parser must read rounds via
   `parse_nrl.round_from_text()`, never its own `round\s+(\d+)` regex (that is exactly
   what stranded the app on Round 27 on finals week). See GOTCHAS.
4. **Front-end stays single-file and dependency-free** (no CDNs, `localStorage` only) —
   it must work offline.
5. **Best-effort fields (odds/news) may be `null`** — that's normal, not a bug.
   (Weather was removed entirely on 2026-08-04; `fixture.weather` ships as an
   always-null key for one deploy cycle, then the key can be dropped.)
6. **Never re-add `viewport-fit=cover` to the viewport meta** while WebKit bug 301994
   exists (iOS sizes the standalone view 62px short and top-anchors it — dead black
   band at the bottom that our dark theme merely hides). Removed 2026-08-18; the JS
   safe-area backstops + `test_ios_viewport.py` depend on it staying gone. See
   `docs/GOTCHAS.md` "iOS 62px dead strip". Changing it is per-install: delete and
   re-add the home-screen icon.
7. **`update docs for upload/` is a staging folder, not an archive. WIPE IT FIRST.**
   Any time you finish work that needs uploading: delete everything in it, then stage the
   current batch. Do this automatically — Josh should never have to ask. A folder that
   accumulates batches is worse than useless: he can't tell which files are the new ones,
   and a leftover file from a previous batch gets uploaded by mistake. (This has already
   happened once — a stale `nrl_lineups.js`, a generated data file that must never be
   uploaded, sat in the folder across batches.) Then rewrite `READ ME FIRST.md` from
   scratch for the new batch; never leave the old one in place.
   - **Stage only files that genuinely differ from what's live.** Check each against
     `https://raw.githubusercontent.com/s1l3ncy/nrl-tipping/main/<path>` — don't assume.
   - **Never stage a generated file**: `index.html`, `nrl_data.js`, `nrl_learned.js`,
     `nrl_players.js`, `nrl_lineups.js`, `nrl_tiplog.js`, or any `*_dump.*`. The workflow rebuilds them,
     and the live copies are usually ahead of the local ones.
   - Mirror the repo layout: `repo-root/`, `docs/`, `github-workflows/`.
   - If `rm` fails with "Operation not permitted", call `allow_cowork_file_delete` —
     don't report it as impossible or work around it by leaving files behind.

## How Josh wants the work done (stated 2026-09-12, during the Brigitte rebuild)
These are process rules, not preferences to weigh up. They came out of a night where a
rebuild had to be shipped between two finals kick-offs.

1. **Dry-run before anything touches a real account.** Nothing gets entered on
   footytips, pushed to GitHub, or run against a live comp until it has been executed
   end to end somewhere harmless first (a clone, jsdom, `--dry-run`) and the output
   shown to him. He decides; the agent does not "just do it because it's obviously right".
2. **An independent adversarial audit before shipping.** Anything that changes the tip
   gets re-derived by a second, independent implementation whose job is to *break* it —
   not a re-read of the same code. The 2026-09-12 audit is the model: it wrote its own
   solver from the brief and found the panel printing "chance of winning the comp:
   **100%**" while Brigitte was mathematically eliminated. Budget for it.
3. **Update the docs in the SAME task as the change.** Not "later", not a follow-up
   ticket. A doc pass that lags one batch behind is how `docs/MODEL.md` §5 spent a whole
   deploy describing a lock the code no longer had.
4. **Apps should just work — no narration of background jobs.** Brigitte should never
   see "recomputing…", a spinner, or a progress line for the solver. If something takes
   400 ms, show the last good answer and quietly correct it (that is exactly why
   `compPlan()` returns a provisional plan and solves on an idle callback). Same rule in
   conversation: report the outcome, not the machinery.

## Where things live
- `nrl-tipping-guide.html` — the app (HTML + CSS + all model JS). Source of truth.
- `sw.js` — network-first service worker (hosted only): keeps the home-screen app
  auto-updating (shell + data) + offline-capable. Upload once; not regenerated.
- `cloud_fetch.py` — scrapes sources → dump files + `nrl_players.js` (GitHub-only; has network).
- `parse_nrl.py` — dumps → `nrl_data.js`; grows the results memory. Has `--merge` mode.
- `learn_model.py` — results memory → fitted params + Elo in `nrl_learned.js`.
- `validate_data.py` / `validate_learned.py` — publish gates.
- `test_ios_viewport.py` — headless (Playwright) iOS layout suite: safe-area
  backstops, both standalone geometries, and the no-`viewport-fit=cover` guard.
- `reference_finals_solver.py` — **reference only, frozen 2026-09-12.** A standalone
  Python implementation of the finals maths, written the same day as the in-page DP so
  the two could be compared. Never imported by anything; never run in the workflow.
- `reference/crosscheck.mjs` — dev tool: boots the real page in jsdom and compares the
  in-page solver's P(1st) for every tip vector against the Python reference. Run from
  the repo root (`node reference/crosscheck.mjs`; `COMPFILE=…` for a fitted-`beh`
  `nrl_comp.js`). Run it after ANY change to the solver.
- `.github/workflows/update-nrl.yml` — the automation (every 4h at :17, plus 05:47 daily,
  16:23 Tuesday for team lists, and since 2026-08-14 four pre-game odds slots: Thu 18:43,
  Fri 19:07, Sat 16:33, Sun 13:07 AEST, and since 2026-09-12 five FINALS slots:
  Sat 15:35, Sat 19:07, Sun 15:35, Sun 18:45 AEST + a second Sunday-evening line at
  17:45 AEST / 18:45 **AEDT** because DST starts on Grand Final day, Sun 4 Oct 2026).
  Includes the freeze-tips step and (since
  2026-08-04) no `--weather` flag. **Always edit from the LIVE copy** (raw URL), never
  a possibly-stale local one.

## The deep docs (read as needed)
- `HANDOFF.md` — orientation + file map + mental model. **Start here.**
- `docs/MODEL.md` — exactly how a tip is computed (Elo/form/injuries/odds/learning).
- `docs/DATA_PIPELINE.md` — scripts + every data-file schema.
- `docs/DEPLOY_AND_OPS.md` — hosting + **the exact steps to make a change and ship it**.
- `docs/ARCHITECTURE.md` — the whole system + data flow.
- `docs/FRONTEND.md` — HTML structure, element IDs to preserve, caching.
- `docs/GOTCHAS.md` — landmines already hit. **Read before deploying.**
- `docs/STRATEGY.md` — **new 2026-09-12.** The comp rules as verified from the API, the
  standings, how the finals solver reasons (plain English then the maths), the adaptive
  "enter tips game by game" advice, the margin-habit finding, the sensitivity table, and
  what to re-check each finals week. Written for Josh and Brigitte, not just for agents.
- `docs/CHANGELOG.md` — dated changes + reasoning.
- Older context: `README.md`, `SPEC.md`, `WEEKLY_UPDATE.md`, `MODEL_IMPROVEMENTS.md`,
  `sources.md`. Where they disagree with the code, the `docs/` pack + code win.

## How to make a change (short version)
1. Edit locally. 2. Test what you can — **including the live scrape**. (This used to say
the sandbox has no network; that's often false. Try `cloud_fetch.py` for real first.)
3. Upload changed file(s) to GitHub (drag-drop or drive Chrome). 4. Actions → "Update
NRL tips" → Run workflow. 5. Verify via raw file URLs with a `?v=N` cache-buster + the
live site. Full detail in `docs/DEPLOY_AND_OPS.md`.

## Current state
Live and self-updating. The Elo engine is live (200+ games, `lowConfidence: false`);
the heuristic path is the fallback. Injuries move the tip (position × rating); the
round's team list both clears named players and rules out unnamed doubts — all
before the odds blend. Weather is gone. **The 2026 finals are on** (rounds 28–31 =
Finals Week 1–3 + Grand Final; footytips comp ends round 31). **The app plays for
Brigitte and optimises P(1st) exactly** — no team is locked.

**Changed 2026-09-12 — THE BRIGITTE REBUILD** (full detail in `docs/CHANGELOG.md`
2026-09-12 and `docs/STRATEGY.md`; this block supersedes every objective/lock claim
in the older blocks below):
- **New user, new objective.** `COMP_ME` / `FOOTYTIPS_ME` = `Brigitte`. The utility is
  `w.first/SIM_N` — **pure P(1st)**. `top3`/`top4` are still counted for display but
  never enter the utility. Josh ("Special unit", 10 back) is modelled as a rival.
  Identity is derived from `COMP_ME` **by name**, with the file's `me` flag only as a
  fallback, so a stale `nrl_comp.js` can't make the freeze tip for one person while
  browsers tip for another. `nrl_adh_v1→_v2`, `nrl_snap_v1→_v2` (the old keys hold the
  previous owner's adherence and the old *locked* snapshots).
- **The Roosters lock is gone end-to-end.** `tipSide()` no longer short-circuits on
  `SYD`; `LOCK_MODE="off"` (`"tiebreak"` = exact-indifference only, verified byte-
  identical). Removed with it: the three `g.lock` sim branches, the "never the Roosters
  game" split filter, the `ledlock` loyalty line, the gold/🐓/🔒 cosmetics, `copyTips()`'s
  "(locked)", the Model tab's "Roosters season W-L" tile and `#rkTax`, and
  `learn_model.py`'s `LOCK_TEAM` / `lock_tax_metrics()` / `backtest.lockTax`.
  `gradedTip()` no longer invents a tip — and the same edit fixed `myResolvedOK`, which
  would otherwise have modelled the +2 perfect-round bonus as dead for the whole round.
- **An EXACT finals solver replaces Monte-Carlo in rounds 28–31.** `finalsPlan()`:
  full enumeration + backward induction over the real NRL bracket (QF1 1v4, QF2 2v3,
  EF1 5v8, EF2 6v7; semis hosted by the QF **losers**, prelims by the QF **winners**,
  GF neutral), rivals from a per-member logistic (`beh`) fitted in `cloud_fetch.py`
  plus a latent per-round strategic layer (`STRAT_AWARE=0.25`), footytips' margin
  **countback** priced as P(her cumulative error < theirs), and the +2 bonus alive-aware.
  ~330 ms, no PRNG, no EPS. `FINALS_MAX_RIVALS=3`. Falls back to `simComp()` if the
  bracket can't be resolved. Non-finals MC: `SIM_N` 3,000 → 8,000, `EPS` derived from it.
- **First paint never waits for the solver.** `compPlan()` returns a provisional plan
  (localStorage plan cache for this exact stamp → the pipeline's frozen tiplog →
  favourites) and solves on `requestIdleCallback`. `planStamp()` now folds in results,
  `dataSig(SRC)`, `gamesLearned`, `TIPLOG.length` and `PLAN_VER`. **The freeze never
  defers** (`window.NRL_SYNC_PLAN` + `compPlanSync()`).
- **Pipeline**: `nrl_comp.js` gains `totalMargin`, round-indexed `margins[]`/`scores[]`/
  `mpreds[]`, `beh{a,b,loy,n,hit}` and `roundIndexed: true` — all from data it already
  fetched, no extra HTTP. `BEH_AFF_K` **must** stay identical in `cloud_fetch.py` and
  the page.
- **Audit fixes (same day, adversarial, independent solver)**: one-sided aliveness
  filter (it printed "chance of winning the comp: 100%" while she was eliminated),
  favourites-first tie-break, splits only when strictly positive, `pctChance()` (never
  rounds a live number into a certainty), "level with X, behind on the countback",
  results in `planStamp()`, `COMP_ME` name-miss warning, `copyTips()` keeps frozen tips
  after kick-off, and a fifth Sunday cron for the AEDT shift on Grand Final day.
- **This weekend's recommendation (R28): Dolphins / Sharks / Panthers, P(1st) ≈ 45%.**
  Tipping the Roosters on Sunday would have cost ~6.5 points of win chance.
  `sw.js` CACHE v23. Verification: independent DP bit-identical, crosscheck OK,
  smoke 59/59, `test_ios_viewport.py` 20/20, both validators PASS, Chromium == jsdom.

**Changed 2026-09-07** (full detail in `docs/CHANGELOG.md`):
- **Finals support end-to-end.** The app sat on Round 27 because every scraper
  regex wanted `round-(\d+)` and the sources had moved to "finals-week-1" /
  "Finals Week 1". All round naming now goes through `parse_nrl.round_from_text()`
  (finals = rounds 28–31, ONE numeric round everywhere; `nrl_data.js` adds
  `roundName` + `finals`, `byeTeams` is `[]` in finals). Publish gates that count
  clubs/fixtures shrink with the finals (`FINALS_GAMES`); non-premiership team-list
  articles are skipped. Front-end: "Finals Week N" labels, and **"back Finals"
  during the finals is a doubt, not long-term OUT** (suspensions = available).
  Validator accepts 1–4 fixtures + no byes in a finals round. `sw.js` CACHE v22.
  See GOTCHAS "Finals are rounds 28–31". `REGULAR_ROUNDS` (27) is per-season.
  *(Still current, except: the verification line "4/4 tips, SYD locked v PEN" describes
  the lock, removed 2026-09-12; and from 2026-09-12 the finals rounds are solved
  exactly rather than simulated.)*

**Changed 2026-08-21, later batch** (full detail in `docs/CHANGELOG.md`):
- **What's new shows only the LATEST tip flip per game** (Josh: "it should just
  show one") — `chgList()` dedupes flips on the unordered pair, newest `ts` wins;
  the full history stays in `nrl_tiplog.js`. Both feed group sorts gained a
  newest-first time tie-break (`chgTs`) — same-sev/same-cat rows used to keep
  file order, which put the OLDER of two flips on top. Front-end only, tips
  untouched. `sw.js` CACHE v21. See GOTCHAS "Tip flips in the feed".

**Changed 2026-08-21** (full detail in `docs/CHANGELOG.md`):
- **Freeze/browser tip divergence fixed: `freeze_tips.mjs` now inlines the prior
  committed `nrl_tiplog.js` into its jsdom page** like the other data files. It used
  to strip it ("independent of its own output", 2026-08-08) — but the simulator
  reads the tiplog (`gradedTip()` → is the perfect-round +2 alive on resolved games;
  the incumbency tie-break), so from a round's first result the freeze priced splits
  on wrong inputs, froze a different tip than every browser showed, and announced
  its own artefact as a flip (R25 SOU–NZW: feed said "now Warriors", Tips page said
  Rabbitohs — the Tips page was right). Merge still reads the committed file from
  disk; no feedback loop. Script-only change: no HTML edit, no `sw.js` bump, model
  untouched. See GOTCHAS "The freeze must LOAD the prior tiplog".

**Changed 2026-08-18** (full detail in `docs/CHANGELOG.md`):
- **iOS 62px dead strip fixed: `viewport-fit=cover` removed** (WebKit bug 301994 —
  with cover, iOS 26.5.2+/26.6 sizes the standalone view 62px short and top-anchors
  it; the dark theme hid the dead black band, the tab bar sat 62px above the real
  screen edge). Safe-area insets are now `:root` vars (`--sat`/`--sab`/`--sal`/
  `--sar` — use these, never inline `env()`, which reports 0 without cover), restored
  by measured JS backstops (iOS+standalone gated, env-wins, self-undoing; letterboxed
  → 0/34, full-bleed → 62/34). New `test_ios_viewport.py` guards it all (20 checks,
  11 mutations killed). Diagnosed in the Fit booking tool project same day. Golden
  rule 6 added. Per-install: delete + re-add the home-screen icon. No visual
  redesign; model/pipeline untouched (freeze 0-change, smoke 60/60). `sw.js` CACHE v20.

**Changed 2026-08-15** — *PARTLY SUPERSEDED 2026-09-12: the objective is no longer
`P(top4)+P(top3)+P(1st)` but pure P(1st), and there is no lock to "always tip", so the
unlocked-Roosters fix and the top-4 term are both history. The perfect-round +2 pricing
and the "tip favourites" baseline survive and are now computed exactly.*
(full detail in `docs/CHANGELOG.md`):
- **Simulator now prices the +2 perfect-round bonus for the CURRENT round**
  (you + rivals; only while the round's live, alive-aware of games already
  played), fixes the unlocked-Roosters pick (you always tip the lock, not the
  favourite), adds **top 4 to the objective** (`P(top4)+P(top3)+P(1st)` — your
  stated goal, less MC noise), and swaps the panel baseline to **"tip
  favourites all season"** (honest floor ~0.3% top 4 vs strategy ~1.5%) from
  the misleading same-round comparison. A single round's split is ~neutral; the
  season-long policy is the edge (tie-breaks carry it). `predict()` untouched,
  freeze 0-change. `sw.js` CACHE v19. See GOTCHAS "perfect-round bonus".

**Changed 2026-08-13, night batch** — *PARTLY SUPERSEDED 2026-09-12: `simComp()` is now
the FALLBACK only; finals rounds are solved exactly by `finalsPlan()` (no PRNG, no EPS).
The objective it describes (BALANCED, `P(top3)+P(1st)`) is gone — pure P(1st). The
countback and margin-game advice survive; "TIED 447 with Thorners" was Josh's ladder.*
(full detail in `docs/CHANGELOG.md`):
- **Splits are now priced by an in-page Monte-Carlo season simulator**
  (`simComp()`; Josh's objective: BALANCED — U = P(top3)+P(1st)). 3,000
  deterministic sims (seed on season+round, keyed per-game draws — browser ==
  freeze), rivals herd-fitted to season accuracy, future-me plays this same
  policy, EPS tie-breaks: incumbent frozen splits → top-2 policy candidates →
  fewer. Need bands remain as candidate filter (θ floor 0.65) + fallback.
  Comp panel adds the honest chances line (1st ~0.1% / top-3 ~0.5% at ship),
  margin countback column + median margin-game advice (lower countback wins
  ties — Josh is TIED 447 with Thorners), and the "You vs the machine"
  adherence tally. Read MODEL.md top section + GOTCHAS "comp simulator"
  before touching. `sw.js` CACHE v17.

**Changed 2026-08-13** (two earlier batches — full detail in `docs/CHANGELOG.md`):
- **Comp picks grouped by side as PLAIN TEXT** (`.cgrp`, no pills — two
  iterations: Josh rejected person-chips, then grouped chips): crest dot +
  bold code + first names per side, home first, ✓/✗ per side at FT; Predicted
  strip matches. **iOS double-tap zoom is dead**: `touch-action:manipulation`
  in the universal `*` rule (keep universal — GOTCHAS; pinch untouched).
- **Live-poll fix**: kickoff-less fixtures now poll on a ±36h game-day window
  (was ±12h — failed when the blanked mid-game PEN–SYD was the day's only
  game and the live score vanished) and `pollLive` adds today's date to the
  ESPN query for them. Recommended-not-implemented: parse-side kickoff
  carry-forward (CHANGELOG). No model/tip changes (freeze verified 0 flips
  both batches). `sw.js` CACHE v16.

**Changed 2026-08-10, audit batch** — *PARTLY SUPERSEDED 2026-09-12: `tipSide()` is no
longer "lock → need-banded split → favourite". The lock is gone and the need bands are a
candidate filter/fallback only; in the finals the split set comes from the exact solver.
oddsW 0.75, the `.mkt` logging and the estimation-only `predict()` all stand.*
(full detail in `docs/CHANGELOG.md`):
- **The tip now optimises WINNING THE COMP** (3-specialist audit): `tipSide()`
  = lock → need-banded split policy (`compPlan()`, data from `nrl_comp.js`
  incl. rival profiles — pipeline-computed for freeze determinism) → blended
  favourite. oddsW default 0.75 (+`oddsWeightLearned`); `tiplog .mkt` logs
  market probs. 🎯 pill marks splits with an honesty line. `predict()` stays
  estimation-only. See MODEL.md "THE OBJECTIVE CHANGED" + GOTCHAS. `sw.js` v14.

**Changed 2026-08-10, strategy batch** — *PARTLY SUPERSEDED 2026-09-12: "never the
Roosters game" is gone (that game is now the most valuable decision on the board), and
in the finals the rival predictor is the fitted per-member `beh` logistic plus a
strategic layer, not loyalty alone. Strategy stays ALWAYS ON — for Brigitte now.*
(full detail in `docs/CHANGELOG.md`):
- **Comp strategy mode** (ALWAYS ON at Josh's direction; re-gate via
  getStrat() if needed): predicts every rival's pick from season history (84% backtested,
  validated 8/8 live), shows a "Predicted" strip on pre-lock cards, and marks
  ≤2 gap-aware 🎯 split picks when trailing. Never the Roosters game. See
  FRONTEND "Comp strategy mode" + GOTCHAS. `sw.js` CACHE v13.

**Changed 2026-08-09** (full detail in `docs/CHANGELOG.md`):
- **Friends' footytips comp on the Tips screen.** The comp API is public (no
  auth, CORS open) so the PAGE fetches it directly — no pipeline step, no
  secrets. Comp strip on locked cards + mini ladder (`#compPanel`).
  `compLocked()` gates all pick display (footytips seals a round's tips
  server-side until the round starts — an early-picks toggle was added and
  removed 2026-08-10, see GOTCHAS). Display names only;
  `COMP_ID`/`COMP_LADDER`/`COMP_ME` constants configure it, `COMP_ID=0`
  kills it. `sw.js` CACHE v12.

**Changed 2026-08-08, evening batch** (full detail in `docs/CHANGELOG.md`):
- **Roosters hero banner removed** — the SYD card sits in normal bucket order
  (still gold-locked). **Tip changes now lead the What's-new feed**: freeze
  records flips (`NRL_TIPLOG.flips`) with win % + plain-text why; ko-less
  entries never re-freeze mid-game. **Quick list + copyTips in week order**
  (`weekOrder()`); `CARD_ORDER` deleted. **↻ chip removed** (pull-to-refresh
  stays). `sw.js` CACHE v9. `freeze_tips.mjs` changed — it's SOURCE, upload it.

**Changed 2026-08-08, later batch** (full detail in `docs/CHANGELOG.md`):
- **Tips screen is ordered by "what matters now"**: On now (live) → Up next
  (soonest kickoff, top card carries "· in 3 hours") → Played (most recent
  first), with conditional `.gsec` dividers; quick list + copyTips follow the
  same frozen order (`CARD_ORDER`). Score ticks never reorder; bucket changes
  re-sort on foreground return or within the 15s post-render grace window
  (boot mid-game). Sort lives ONLY at the top of `render()` — see
  `docs/GOTCHAS.md` before "simplifying".

**Changed 2026-08-08** (full detail in `docs/CHANGELOG.md`):
- **Live in-play scores.** While a game is on, the open page polls ESPN's public
  scoreboard (the only NRL score source with CORS headers; nrl.com's JSON has
  none) every 45s and shows a live card — pulsing LIVE badge, clock, score, the
  frozen tip and whether it's in front — plus live rows in the hero, quick list
  and round schedule. Full time shows instantly (ESPN `post`) until the pipeline's
  official result lands, which always wins. Display-only overlay: grading, the
  results memory, tip log and model never read it. Score ticks re-render
  surgically (`renderLiveBits`), never via `render()`. `sw.js` CACHE v7.
  See `docs/GOTCHAS.md` "Live scores (2026-08-08)" before touching it.

**Changed 2026-08-04** (full detail in `docs/CHANGELOG.md`):
- **Desktop gets its own UI at ≥1024px** (top pill nav — same `.tabbar` element,
  restyled — 1140px layout, 2-up cards, 2-column Model, Quick-list rail at ≥1280px).
  Phone ≤640px unchanged. `docs/FRONTEND.md` has the tier table.
- **The app keeps itself fresh while open**: foreground-return refresh, 5-minute
  polling, a ↻ chip in the nav, and pull-to-refresh — no more force-quitting the
  home-screen app. No-op (no re-render) when data hasn't changed. `sw.js` CACHE v6.
- **What's new redesigned**: status line, Today feed + folded "Earlier", crest dots
  and "view game →" links, and a full round-schedule panel — no more empty screen.
- **Weather removed end-to-end** (scraper, parser, model, UI, change feed, workflow).
- **Nine audit fixes** from the sports/gambling specialist audit: opening odds
  preserved across full rebuilds, winner-relative Elo MOV, `logisticScale` pinned
  at 7 (unlearnable — never re-add to the grid), loyalty tax computed walk-forward
  server-side (`backtest.lockTax`), phantom injury-name guards, season-aware
  results memory, line-move attribution fixed, dead calibration code removed,
  unordered-pair grading keys. See `docs/GOTCHAS.md` "2026-08-04 batch".
- **The audit's judgement-call recommendations** (home-advantage refit, odds-history
  persistence, higher odds weight, grid regularisation, stale-odds visibility,
  frozen probability in the tiplog, travel/bye/spread variables) are recorded in
  `docs/CHANGELOG.md` awaiting Josh's approval — not implemented.

**Changed 2026-07-30 (later)**: full UI rebuild — bottom tab bar (Tips / What's new /
Ladder / Model), rebuilt game cards (win-probability bar, gold = the lock), aurora/glass
visual system, and a real rooster app icon (`apple-touch-icon.png` + `favicon-32.png`,
`sw.js` CACHE v4). Render pipeline and element IDs untouched — see `docs/FRONTEND.md`.

**Changed 2026-07-30** (shipped, live, `ODDS_API_KEY` secret set):
- **Odds actually work now — via The Odds API.** nrl.com geo-blocks prices from
  non-Australian IPs, so the 2026-07-29 scrape that tested perfectly from Australia
  published nothing from GitHub's US runners. The Odds API (free tier, `ODDS_API_KEY`
  repo secret, non-fatal without it) is primary; nrl.com stays as fallback. Quota and
  state are visible in `last_run.json`.
- **A doubt becomes an OUT once the team list is published** and the player isn't in his
  club's 17 (badge: NOT NAMED, full weight). Tom Dearden was showing as a half-weight
  "doubt" during a game he wasn't playing in.
- **Weather is for the game's own day** (matched on kick-off date; dump lines are now
  `City|YYYY-MM-DD:`), not "wettest of the next ~6 days" — which was shrinking a
  Thursday game by Saturday's rain. Failed city fetches keep their committed line.
- **Feed/wording polish:** same-city-same-day forecasts emit one comp-wide entry, not
  two identical rows; the odds box stops promising "Tuesday" once kick-off is <48h out.
- **Also:** the 2026-07-29 batch's `docs/` pack, CLAUDE.md and HANDOFF.md never actually
  made it to GitHub — this batch re-carries them.

If anything here looks stale, trust the code and update these docs.
