# Deploy & Ops

How hosting works and — most importantly — **the exact steps to make a change and get
it live**. This is the doc you'll use most often.

---

## How hosting works

- **Repo:** https://github.com/s1l3ncy/nrl-tipping (public — required for free Actions
  minutes and Pages).
- **Compute:** GitHub Actions workflow `.github/workflows/update-nrl.yml`, on a cron
  schedule, does the scrape/rebuild/validate/publish. No local machine involved.
- **Serving:** GitHub Pages, from the `main` branch root, serves **`index.html`** plus
  `nrl_data.js`, `nrl_learned.js`, `nrl_players.js`, and `sw.js` (the service worker).
- **Live URL:** https://s1l3ncy.github.io/nrl-tipping/

### The single most important fact
**The live website is `index.html`.** `index.html` is a *generated copy* of
`nrl-tipping-guide.html`, produced by the workflow step `cp nrl-tipping-guide.html
index.html`. So:

> Editing `nrl-tipping-guide.html` changes NOTHING on the live site until a workflow
> run copies it to `index.html`. If you change the HTML, you must run the workflow
> (or edit `index.html` too) for it to appear.

---

## The workflow (`update-nrl.yml`)

Schedule (cron is in **UTC**): every 4 hours at :17, plus 05:47 Sydney daily and a
16:23 Tuesday slot for team lists, plus `workflow_dispatch` (run on demand from the
Actions tab). The exact lines live in `update-nrl.yml` — trust the file over this doc.

### The `ODDS_API_KEY` secret (required for bookmaker odds)
Odds come from **The Odds API** because nrl.com geo-blocks prices from GitHub's US
runners (`GOTCHAS.md`). One-time setup, only Josh can do it:
1. Sign up free at https://the-odds-api.com → the key arrives by email.
2. Repo → Settings → Secrets and variables → Actions → **New repository secret**.
3. Name `ODDS_API_KEY`, paste the key, Add secret.
No key / bad key / exhausted quota are **non-fatal**: the run publishes everything else
and `last_run.json` says what happened (`oddsApiState`, `oddsApiRemaining` — the free
tier is 500 requests/month, the schedule uses ~240). Never commit or log the key; the
repo is public.

Steps, in order:
1. Checkout, set up Python 3.12, `pip install requests beautifulsoup4`.
2. `python cloud_fetch.py` — scrape sources → dumps + `nrl_players.js` (env: `ODDS_API_KEY`).
3. `python parse_nrl.py … --out nrl_data.js` — rebuild the data feed (no `--weather`
   since 2026-08-04).
4. `python learn_model.py` — re-fit the learning loop.
5. **Freeze pre-kick-off tips** — `freeze_tips.mjs` (jsdom; best-effort, non-fatal)
   writes `nrl_tiplog.js`. This step exists ONLY in the live workflow history —
   never overwrite the workflow from a stale local copy or the tip log dies.
6. `python validate_data.py nrl_data.js` **and** `validate_learned.py nrl_learned.js`
   — **publish gate**; a failure fails the whole run and nothing goes live.
7. Retire the weather dump (`rm -f weather_dump.txt`, idempotent — one-time cleanup
   after the 2026-08-04 weather removal).
8. `cp nrl-tipping-guide.html index.html` — build the hosted page.
9. `git add -A && git commit && git push` — commit refreshed files back (uses the
   built-in `GITHUB_TOKEN`; `permissions: contents: write`).

`concurrency: nrl-update` prevents overlapping runs.

---

## Making a change and shipping it (step by step)

1. **Edit the file(s) locally** in this folder.
   - Front-end / model UI / injury logic → `nrl-tipping-guide.html`.
   - Scrapers / new data source → `cloud_fetch.py`.
   - Parser / schema → `parse_nrl.py` (and update `validate_data.py` if the contract changes).
   - Learning math → `learn_model.py` (and `validate_learned.py` if the contract changes).

2. **Test what you can locally.**
   - HTML: open it in a browser and check it renders + tips look right. Verify the JS
     parses (e.g. extract the `<script>` and `node --check`).
   - Python: run the script and the matching validator. Try `cloud_fetch.py`'s live
     fetch for real first — sandboxes often DO have network (`GOTCHAS.md`). But note
     odds specifically can look fine from Australia and publish nothing from GitHub
     (geo-block), so verify odds via `last_run.json` after a real run.

3. **Upload to GitHub.** Two ways:
   - **Drag-drop (reliable):** open the repo in the browser → "Add file" → "Upload
     files" → drag the changed file(s) in (this replaces same-named files) → Commit.
   - **Browser automation:** drive the upload via the Chrome tools (the extension is
     connected under Josh's account).

4. **Run the workflow:** repo → **Actions** → **"Update NRL tips"** → **Run workflow**
   (branch `main`). This rebuilds data, copies the HTML to `index.html`, validates, and
   publishes. A run takes ~20–30s.

5. **Verify** (see below).

For a data-only change you often don't need to upload anything — just run the workflow
and it re-scrapes.

---

## Verifying a deploy

- **Workflow status:** Actions tab → the latest "Update NRL tips" run should be green.
  If red, open it and read the failing step's log (validators print exactly what's wrong).
- **Raw data files** (bypass the site, see what actually got committed):
  `https://raw.githubusercontent.com/s1l3ncy/nrl-tipping/main/nrl_players.js`
  (and `nrl_data.js`, `nrl_learned.js`). **Add a cache-buster** `?v=<number>` when
  re-checking, because raw/CDN caches aggressively (e.g. `…/nrl_players.js?v=13`).
- **Useful log lines** printed by the scripts: `ratings: parsed N players`,
  `parsed N teams`, `wrote nrl_data.js`, `gamesLearned=… lowConfidence=…`.
- **Live site:** https://s1l3ncy.github.io/nrl-tipping/ — the Pages CDN can lag a
  minute or two behind a run; a hard refresh helps.

---

## Common ops tasks

- **Force an update now:** Actions → Run workflow. (Also the fix if schedules went quiet
  — GitHub pauses cron after 60 days of repo inactivity, though `keepalive.yml` re-enables it fortnightly.)
- **Change the schedule:** edit the two `cron:` lines (UTC) in `update-nrl.yml`.
- **A player's injury isn't affecting the tip:** confirm they're in `nrl_players.js`
  (only the rated players are — roughly the top few hundred; fringe players are treated
  as low-impact by design), and that the injury name matches the ratings name after
  normalisation.
- **Wrong host city:** add the venue to `VENUE_CITY` in `parse_nrl.py`.
- **The site "looks the same" after an HTML change:** you didn't run the workflow (so
  `index.html` wasn't recopied), or you're seeing CDN cache — hard refresh / wait.
- **Home-screen app shows old data/UI:** since 2026-08-04 the page refreshes itself
  while open (foreground return, 5-minute polling, the ↻ chip in the nav, and
  pull-to-refresh) — no force-quit needed. `sw.js` is network-first and additionally
  updates the shell + data on each online launch. The *first* time (or if `sw.js`
  isn't on the phone yet), remove and re-add the home-screen icon once to load the new
  shell. To force a clean slate for every visitor, bump `CACHE` in `sw.js` (`nrl-tips-vN`,
  currently v6).
- **Shipping `sw.js`:** it's a normal source file (not generated). Upload it to the repo
  root once; `git add -A` in the workflow keeps committing it, and Pages serves it.

---

## What only Josh can do
- Create/own the GitHub account and log in.
- Approve browser actions when an AI is driving Chrome.
Everything else (edits, uploads, running the workflow, verifying) can be done by an AI
assistant with the Chrome tools, or by Josh via drag-drop.
