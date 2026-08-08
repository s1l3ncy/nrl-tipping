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
- Owner: Josh (GitHub `s1l3ncy`), Roosters supporter. Season: 2026.

## Golden rules (do not break these)
1. **The Sydney Roosters (`SYD`) are ALWAYS tipped** in their own game. Never "fix" it.
2. **The live site is `index.html`, a generated copy of `nrl-tipping-guide.html`.**
   Editing the guide changes nothing live until the workflow runs `cp … index.html`.
   So after any HTML change, **run the workflow**.
3. **Never hand-edit generated files:** `index.html`, `nrl_data.js`, `nrl_learned.js`,
   `nrl_players.js`, `nrl_tiplog.js` — they're overwritten each run.
4. **Front-end stays single-file and dependency-free** (no CDNs, `localStorage` only) —
   it must work offline.
5. **Best-effort fields (odds/news) may be `null`** — that's normal, not a bug.
   (Weather was removed entirely on 2026-08-04; `fixture.weather` ships as an
   always-null key for one deploy cycle, then the key can be dropped.)
6. **`update docs for upload/` is a staging folder, not an archive. WIPE IT FIRST.**
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

## Where things live
- `nrl-tipping-guide.html` — the app (HTML + CSS + all model JS). Source of truth.
- `sw.js` — network-first service worker (hosted only): keeps the home-screen app
  auto-updating (shell + data) + offline-capable. Upload once; not regenerated.
- `cloud_fetch.py` — scrapes sources → dump files + `nrl_players.js` (GitHub-only; has network).
- `parse_nrl.py` — dumps → `nrl_data.js`; grows the results memory. Has `--merge` mode.
- `learn_model.py` — results memory → fitted params + Elo in `nrl_learned.js`.
- `validate_data.py` / `validate_learned.py` — publish gates.
- `.github/workflows/update-nrl.yml` — the automation (every 4h at :17, plus 05:47 daily
  and 16:23 Tuesday for team lists). Includes the freeze-tips step and (since
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
Live and self-updating. The Elo engine is live (160+ games, `lowConfidence: false`);
the heuristic path is the fallback. Injuries move the tip (position × rating); the
round's team list both clears named players and rules out unnamed doubts — all
before the odds blend. Weather is gone.

**Changed 2026-08-08** (this batch — full detail in `docs/CHANGELOG.md`):
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
