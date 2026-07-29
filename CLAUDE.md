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
   `nrl_players.js` — they're overwritten each run.
4. **Front-end stays single-file and dependency-free** (no CDNs, `localStorage` only) —
   it must work offline.
5. **Best-effort fields (odds/news/weather) may be `null`** — that's normal, not a bug.

## Where things live
- `nrl-tipping-guide.html` — the app (HTML + CSS + all model JS). Source of truth.
- `sw.js` — network-first service worker (hosted only): keeps the home-screen app
  auto-updating (shell + data) + offline-capable. Upload once; not regenerated.
- `cloud_fetch.py` — scrapes sources → dump files + `nrl_players.js` (GitHub-only; has network).
- `parse_nrl.py` — dumps → `nrl_data.js`; grows the results memory. Has `--merge` mode.
- `learn_model.py` — results memory → fitted params + Elo in `nrl_learned.js`.
- `validate_data.py` / `validate_learned.py` — publish gates.
- `.github/workflows/update-nrl.yml` — the automation (every 4h at :17, plus 05:47 daily
  and 16:23 Tuesday for team lists — **not** the "06:00 + 12:00" this line used to claim).

## The deep docs (read as needed)
- `HANDOFF.md` — orientation + file map + mental model. **Start here.**
- `docs/MODEL.md` — exactly how a tip is computed (Elo/form/injuries/weather/odds/learning).
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
Live and self-updating. Injuries move the tip, weighted by each player's real position ×
rating (from `nrl_players.js`); weather shrinks confidence; both applied before the odds
blend. The learning loop is **past** `lowConfidence` (156 games as of 2026-07-29), so the
Elo engine is live — the heuristic path is now the fallback, not the default.

**Changed 2026-07-29** (needs a workflow run to reach the live site):
- **Bookmaker odds now exist.** They never had a source — `cloud_fetch.py` wrote no odds
  dump and the workflow passed no `--odds`, so `fixture.odds` was permanently `null` and
  the UI promised prices "around Tuesday" that could never arrive. Now scraped from
  nrl.com's draw payload, along with the real stadium and an offset-bearing kick-off
  (both of which `extract_draw()` used to discard).
- **A "what changed today" feed**, diffed each run over a rolling 36h window.
- **"Why the model leans this way"** is now a full itemised ledger that reconciles to the
  displayed margin.
- **The Roosters lock is now actually enforced.** It was cosmetic: `copyTips`, the
  quicklist and the card tipline all computed `pHome>=0.5?h:a` and merely *annotated* the
  Roosters game, so with the model disagreeing "Copy tips" emitted the **opponent**
  labelled `(locked)`. All tip-naming now routes through `tipSide()`. `lockHero` still
  reports honestly when the model disagrees — that part was always right.

If anything here looks stale, trust the code and update these docs.
