# Architecture

How the whole system fits together, end to end. For the tip math see
`MODEL.md`; for scripts/schemas see `DATA_PIPELINE.md`; for hosting see
`DEPLOY_AND_OPS.md`; for the comp strategy in plain English see `STRATEGY.md`.

> **Since 2026-09-12** the app plays for **Brigitte** (Josh still owns the repo, the
> GitHub account and the deploys) and its objective is exactly **P(she finishes 1st)**
> in the footytips comp. No team is force-tipped. That changes one thing structurally:
> the front-end no longer just estimates and displays — it *solves*, in-page, and in the
> finals it does so exactly. See stage 5 and `MODEL.md` §5.

---

## Design goals (why it's built this way)

1. **Runs with the owner's Mac off.** (Josh's — he owns the infrastructure; Brigitte is
   the user and never touches it.) All the work happens on GitHub's servers on a
   schedule, not on a local machine. That drove the choice of GitHub Actions
   (compute) + GitHub Pages (hosting), both free on a public repo.
2. **Self-contained, offline-capable front-end.** The app is one HTML file with no
   external dependencies (no CDNs, no build step, no framework). It can be opened
   as a local file and still works. All "smarts" run in the browser.
3. **Data as plain JS files.** Instead of a database or an API, the data ships as
   three tiny `window.NRL_*` assignment files the HTML loads with `<script src>`.
   Easy to diff, easy to validate, easy to serve statically.
4. **Never publish broken data.** Validators gate every publish. Best-effort feeds
   (odds/news/ratings) never block; only a broken ladder/draw does.
5. **Honest about uncertainty.** The learning loop won't trust itself until it has
   enough history (a `lowConfidence` guardrail), and the UI surfaces this.

---

## The data flow, stage by stage

### Stage 0 — Sources (public web)
- **Zero Tackle** (`zerotackle.com`): NRL ladder (with home/away split tables),
  fixtures/results, injuries & suspensions, and the **player ratings** pages.
- **nrl.com** draw payload: venues, host cities, UTC kick-offs (+ odds fallback).
- **The Odds API**: bookmaker head-to-head prices (primary odds source).
- (Open-Meteo weather was a source until 2026-08-04 — removed entirely.)

See `sources.md` for exact URLs and expected shapes.

### Stage 1 — `cloud_fetch.py` (GitHub only; has network)
Scrapes the live sources with `requests` + `BeautifulSoup` and writes clean
intermediate **dump files** that `parse_nrl.py` knows how to read, plus the player
ratings map directly:
- `ladder_dump.html` — rebuilt ladder table (incl. home/away splits).
- `draw_dump.html` — the next unplayed round's fixtures (auto-advances each week).
- `injuries_dump.html` — `Team: Player (Reason) — back Round N; ...` lines.
- `nrl_players.js` — `window.NRL_PLAYERS = { "name": {pos, pct} }` (all rated players).

Everything is best-effort and defensive: if a source won't parse confidently, the
previously committed dump is left untouched rather than wiped. For the draw that means
two gates, not one: a plausible fixture count (6–9) **and** never fewer fixtures than the
committed dump already holds for that same round — a partial parse (Zero Tackle down and
nrl.com resolving only 6 of 8 nicknames) passed the bare range check and shrank a good
8-fixture dump.

### Stage 2 — `parse_nrl.py` (pure, no network)
Reads the dump files and emits **`nrl_data.js`** (`window.NRL_DATA`): the 17 teams
with ladder + home/away splits + injury `news`, the current round's fixtures with
`odds`, and `byeTeams`. It also scans for finished-game scores and
**appends** them to the results memory in `nrl_learned.js` (append-only, deduped
on season+round+teams). Has a `--merge` mode that refreshes only the fast-moving
fields (odds/news) without rebuilding the ladder/round.

### Stage 3 — `learn_model.py` (pure, no network)
Reads the results memory in `nrl_learned.js`, replays an **Elo** rating for every
team (winner-relative MOV multiplier), grid-searches the model parameters
(home-ground advantage, Elo K/HGA, odds weight — the logistic scale is pinned at 7,
see `MODEL.md`) to minimise walk-forward error, **backtests** itself
(Brier/log-loss/hit-rate; the walk-forward loyalty tax `lockTax` was removed 2026-09-12
with the Roosters lock), and rewrites
`nrl_learned.js` with fresh params + Elo + one appended history snapshot.
Guardrail: under ~30 games it holds conservative defaults and flags `lowConfidence`.

### Stage 4 — Validate + publish (in the workflow)
`validate_data.py` and `validate_learned.py` must both pass. Then the workflow does
`cp nrl-tipping-guide.html index.html` and commits everything back with the
built-in `GITHUB_TOKEN`. GitHub Pages serves `index.html` + the three data files.

### Stage 5 — The browser (front-end)
`nrl-tipping-guide.html` loads `nrl_data.js`, `nrl_learned.js`, `nrl_players.js`,
`nrl_lineups.js`, `nrl_tiplog.js` and `nrl_comp.js`, then does **two** things in-page:

1. **Estimate** — for each fixture, a win probability (`predict()`: Elo/form + injuries
   + home edge, blended with the market).
2. **Decide** — which set of tips maximises P(Brigitte finishes 1st), given the comp
   standings, the margin countback and a model of what each rival will tip
   (`compPlan()` → `tipSide()`). No team is ever force-tipped (the Roosters lock was
   removed 2026-09-12). In the finals (rounds 28–31) this is not a simulation:
   `finalsPlan()` enumerates the remaining bracket and solves it by backward induction,
   ~330 ms, once per `planStamp`. First paint doesn't wait for it — a provisional plan
   comes from a stamped `localStorage` cache or the frozen tiplog, and the real solve
   runs on an idle callback (`MODEL.md` §5.8).

That second step is the reason `nrl_comp.js` is a *pipeline-generated data file* rather
than something the page fetches for itself: the jsdom freeze and every browser must read
identical inputs, or they compute different tips. Since 2026-08-04 the page also
**keeps itself fresh while open**
(foreground-return, 5-minute polling, a manual refresh chip and pull-to-refresh —
see `FRONTEND.md`), and serves a genuinely different layout on desktop (≥1024px)
vs phone. Users can log results locally (`localStorage`) between official refreshes.

---

## Why three separate data files

- `nrl_data.js` changes weekly (ladder/draw) + daily (odds/news).
- `nrl_learned.js` is an append-only match log plus fitted numbers; it grows slowly
  and must never be clobbered by a bad run (atomic writes + parse-or-abort).
- `nrl_comp.js` is the comp snapshot — standings, picks, per-round margin/score
  history and the fitted rival model. It is a **determinism device**: everything the tip
  depends on has to ship in a file so the freeze and the browser agree byte for byte.
  The page live-refreshes the current round from the public API on top of it, but never
  fetches anything that feeds `tipSide()` and isn't in the file.
- `nrl_players.js` is a large-ish lookup refreshed every run, independent of the
  others. Keeping it separate means the front-end can treat it as optional (falls
  back gracefully if missing) and the other generators don't need to know about it.

---

## Trust & safety properties baked in

- **Atomic writes**: generators write to a temp file then `os.replace()`, so an
  interrupted run can't leave a half-written file that clobbers good data.
- **Parse-or-abort**: if an existing `nrl_data.js`/`nrl_learned.js` can't be parsed,
  the generator refuses to write rather than destroying history.
- **Graceful degradation**: missing draw → reuse previous fixtures; missing
  odds/news/ratings → leave those fields null / fall back to flat weighting;
  missing `nrl_data.js` at runtime → the HTML uses a baked-in seed so the page never
  shows blank.
- **Publish gate**: validators fail the workflow before anything goes live.

---

## Hosting topology

- **Compute:** GitHub Actions (Ubuntu runner) on a cron schedule — no always-on
  server, no local machine needed.
- **Storage:** the git repo itself is the datastore; each run commits the refreshed
  data files.
- **Serving:** GitHub Pages (static) from the repo root on `main`, serving
  `index.html` + the `nrl_*.js` files.
- **Cost:** $0 on a public repo.
