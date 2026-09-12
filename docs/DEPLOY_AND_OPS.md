# Deploy & Ops

How hosting works and — most importantly — **the exact steps to make a change and get
it live**. This is the doc you'll use most often.

> **Who is who (clarified 2026-09-12).** **Josh** owns the infrastructure: the GitHub
> account `s1l3ncy`, the repo, the `ODDS_API_KEY` secret, the Chrome session an agent
> drives, and every deploy. **Brigitte** (his wife) is the *user*: the app plays for her
> footytips entry and its objective is P(she finishes 1st). She never touches GitHub.
> So "only Josh can do it" below always means *infrastructure*, never *the tips* — and a
> change to the tips still has to be shipped by Josh.

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
16:23 Tuesday slot for team lists, four pre-game odds slots (2026-08-14), **five finals
slots (2026-09-12: Sat 15:35, Sat 19:07, Sun 15:35, Sun 18:45 AEST, plus 17:45 AEST /
18:45 AEDT for Grand Final day)**, plus `workflow_dispatch` (run on demand from the
Actions tab). The exact lines live in `update-nrl.yml` — trust the file over this doc.

> **Cron is UTC and Sydney is UTC+10 only until DST starts on Sun 4 Oct 2026 — Grand
> Final day.** Every Sunday line lands an hour later locally from then on. Do the
> arithmetic (and move the day-of-week field if the conversion crosses midnight) before
> adding or editing any slot. See GOTCHAS "Finals cron slots".

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

> **Step 2 must run before step 5.** `cloud_fetch.py` writes `nrl_comp.js`; the freeze
> reads it. Until it has run once with the current code the file carries no fitted `beh`,
> and the page falls back to the older rival model — **same tips, but `pFirst` reads
> ~50% instead of ~46% and a split is priced at +0.3 instead of +2.0**. The workflow
> already orders it correctly; check it still does after any workflow edit.
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
   - **If the change touches the tip at all, run the full gauntlet before uploading**
     (Josh's rule: dry-run everything, and audit adversarially before shipping):

     | Command | What it proves |
     |---|---|
     | `node reference/crosscheck.mjs` | The in-page solver agrees with `reference_finals_solver.py` on P(1st) for **every** admissible tip vector. Expect a uniform ~2.5pt level shift (the two fit their rival models differently — see MODEL.md §5.9); what must not move is the best line, and every Roosters-containing line ranking below every non-Roosters one. `COMPFILE=…` points it at an `nrl_comp.js` with fitted `beh` — that is the shipping configuration. Run from the repo root. |
     | `python3 reference_finals_solver.py` | Regenerates the reference numbers themselves (~4 min, exact full enumeration). Only needed when the *situation* changes — new results, new standings, a new week — not on every code edit. Frozen 2026-09-12; REFERENCE ONLY, nothing imports it. |
     | `node freeze_tips.mjs` **twice** | First run may report flips; the second **must** report `0 new/changed`. Churn here is churn in the What's-new feed on everyone's phone. Restore `nrl_tiplog.js` with `git checkout` afterwards. |
     | `node smoke_test.mjs` | 59/59. (Was 60/60 before 2026-09-12: two Roosters assertions became one positive one — *every* game's tip is the model's own favourite unless the solver splits.) |
     | `python3 test_ios_viewport.py` | 20 green. Cheapest possible catch for a `ReferenceError` left behind by a deletion — it boots the real page. |
     | `python3 validate_data.py nrl_data.js` / `validate_learned.py nrl_learned.js` | The publish gates, locally. |

     And, when the stakes justify it: render the page in real headless Chromium and check
     `pFirst` matches the jsdom freeze **to the last bit**. Browser ≠ freeze is the
     failure mode this whole architecture exists to prevent.

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
- **Change the schedule:** edit the `cron:` lines (UTC) in `update-nrl.yml` — there are
  twelve of them now, not two. Convert from AEST/AEDT carefully (see the DST note above).
- **The comp panel shows a number that looks wrong (e.g. "100%", or "0 behind"):** the
  three formatting/logic traps here all have entries in `GOTCHAS.md` under the
  2026-09-12 block. Check `pctChance()`, the one-sided aliveness filter, and whether
  `plan.provisional` is still true (the solver may still be running on an idle callback,
  in which case the line should read "working out the comp odds…" and not a number).
- **A tip on screen disagrees with `nrl_tiplog.js`:** first check whether the page is on
  a provisional plan (cold cache + a tiplog from before the last code change — it
  self-corrects in ~450 ms), then whether `cloud_fetch.py` has run since the last deploy,
  then diff `planStamp()` inputs. Never assume cache.
- **A player's injury isn't affecting the tip:** confirm they're in `nrl_players.js`
  (only the rated players are — roughly the top few hundred; fringe players are treated
  as low-impact by design), and that the injury name matches the ratings name after
  normalisation.
- **Wrong host city:** add the venue to `VENUE_CITY` in `parse_nrl.py`.
- **The site is stuck on the last round after the season/finals move on:** check
  `last_run.json` — `dataRound` behind, `fixturesWithKickoff: 0`,
  `oddsApiState: not-attempted` means the draw didn't advance. The sources have
  probably renamed the round (finals week / grand final); every round string must
  resolve through `parse_nrl.round_from_text()` — extend it, don't add a regex
  elsewhere (GOTCHAS "Finals are rounds 28–31"). Each March, confirm
  `REGULAR_ROUNDS` in `parse_nrl.py` / `validate_data.py` / the HTML still matches
  the new draw.
- **The site "looks the same" after an HTML change:** you didn't run the workflow (so
  `index.html` wasn't recopied), or you're seeing CDN cache — hard refresh / wait.
- **Home-screen app shows old data/UI:** since 2026-08-04 the page refreshes itself
  while open (foreground return, 5-minute polling, the ↻ chip in the nav, and
  pull-to-refresh) — no force-quit needed. `sw.js` is network-first and additionally
  updates the shell + data on each online launch. The *first* time (or if `sw.js`
  isn't on the phone yet), remove and re-add the home-screen icon once to load the new
  shell. To force a clean slate for every visitor, bump `CACHE` in `sw.js` (`nrl-tips-vN`,
  **currently v23** — bumped 2026-09-12).
- **Shipping `sw.js`:** it's a normal source file (not generated). Upload it to the repo
  root once; `git add -A` in the workflow keeps committing it, and Pages serves it.

---

## What only Josh can do
- Create/own the GitHub account and log in.
- Approve browser actions when an AI is driving Chrome.
- Hold the `ODDS_API_KEY` secret.
Everything else (edits, uploads, running the workflow, verifying) can be done by an AI
assistant with the Chrome tools, or by Josh via drag-drop.

**What only Brigitte can do:** enter the tips on footytips. The app *advises*; nothing
in this repo has, or should get, write access to her footytips account. If that ever
changes, golden rule: dry-run it and show Josh the output before it touches the real
comp.
