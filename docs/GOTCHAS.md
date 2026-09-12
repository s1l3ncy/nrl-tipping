# Gotchas — landmines already hit (read before deploying)

Real problems encountered on this project and how to avoid repeating them.

---

# 2026-09-12 — the Brigitte rebuild. Read this block first.

Nine entries from the night the app changed owner, lost its lock and gained an exact
finals solver. The four older sections marked **SUPERSEDED** further down were written
about the app as it was; this block is what is true now.

## The lock is gone and the objective is P(1st) — do not "restore" either

- **`LOCK_MODE = "off"`, and no team is ever force-tipped.** `tipSide()` is: comp split
  → (`LOCK_MODE==='tiebreak'` only) house preference on an exact coin toss →
  `modelFav()`. The `'tiebreak'` setting was verified to produce **byte-identical tips
  and the same P(1st) to six decimals** on the R28 data, which is the only reason it is
  allowed to exist. If it ever costs anything, delete it.
- **The utility is `w.first/SIM_N` — pure P(1st).** `top3`/`top4` are still counted for
  display and must never re-enter the utility. A safety term is not free: it buys a
  podium at the cost of the only outcome anyone cares about.
- **`EPS` must be derived from `SIM_N`, not fixed.** Under the old three-tier utility,
  utilities ran 0.02–0.05 and `EPS = 0.003` was sane. Under pure P(1st) they run
  0.15–0.35, where the Monte-Carlo standard error at 3,000 samples (~0.8pp) is **three
  times** EPS — the tie-breaks then fire on noise every run and churn the flip feed. It
  is now `max(0.003, 2·sqrt(0.25/SIM_N))` with `SIM_N = 8,000`. (20,000 was measured at
  ~820 ms on an 8-game round in jsdom — too much for a first paint. 8,000 is ~355 ms and
  still cuts the standard error ~40%.) Finals rounds do not sample at all.
- **`predict()` stays strategy-free.** Everything comp-aware lives behind `tipSide()`.

## `myResolvedOK` — the invisible regression that comes with deleting a lock

- Deleting `gradedTip()`'s last-resort "if the Roosters are in this game the tip is SYD"
  is correct (a game with no frozen tip and no snapshot must be honestly ungraded). But
  `simComp()`'s `myResolvedOK` read `g.known && g.short === winner`, so an **ungraded**
  resolved game evaluated to `false` and the +2 perfect-round bonus was modelled as
  **dead for the whole round**. It now skips unknowns and only breaks on a *known wrong*
  tip.
- Why this is the entry rather than a footnote: it is completely invisible when it
  happens. No error, no wrong-looking tip — just a systematically pessimistic plan. Any
  future change to what `gradedTip()` can return must re-check every consumer that
  treats "not known" as "not correct".

## `BEH_AFF_K` must be identical in `cloud_fetch.py` and the page

- The rival model is `P(tips home) = sigmoid(a + b·lp + loy·(affShare(home) −
  affShare(away)))`. `affShare()` shrinks a member's season affinity toward a coin flip
  by **`BEH_AFF_K` pseudo-games**. Python fits the coefficients against one definition of
  that covariate; the page evaluates them against its own. **Change one file only and the
  coefficients are being applied to a different variable than they were fitted on** —
  silently, with no error and nothing obviously wrong on screen. Both files carry the
  warning at the constant. Keep it there and keep the value in step.
- **The loyalty covariate is leave-one-out in Python and must stay that way.** A
  member's affinity share for team X is literally the mean of their own picks in X's
  games, so the pick being predicted sits inside its own covariate: fed in raw it is a
  perfect in-sample predictor and drove the market/form coefficient `b` to **exactly
  0.00** for all six members. With LOO + shrinkage, `b` is 0.31–1.60 and `loy` 2.16–5.09.
  Do not "simplify" the `_share()` closure.
- `beh` is still **fitted in-sample** on the market coefficient, so its reported `hit`
  (0.70–0.83) is mildly optimistic. The reference solver's sweep says the R28
  recommendation survives halving rival predictability.

## Per-member history arrays are ROUND-INDEXED — never zip dense lists

- `margins[]`, `scores[]` and `mpreds[]` originally shipped as dense lists with empty
  rounds filtered *out*, so members had different lengths (observed: 28/25/25/24/23/28
  for `mpreds`). **`finalsTieProbs()` zips them positionally** to get each round's margin
  difference — so her round 6 was being compared against a rival's round 8. It had not
  bitten only because `margins[]` happened to be complete for all six; the first missing
  round would have made the countback's standard deviation silently wrong, **and the
  countback is her entire edge**.
- All three arrays are now length `round`, index = round−1, `null` where absent — from
  `cloud_fetch.py` (`_by_round()`) and from the live poll (`byRound()`, which mirrors it
  exactly). The payload carries **`roundIndexed: true`**, and that flag is load-bearing:
  the two formats are indistinguishable by inspection when no round happens to be
  missing. `finalsTieProbs()` **refuses to zip without it** and falls back to the
  season-total mean with sd 10 — imprecise rather than quietly wrong.
- Every consumer must skip nulls explicitly: `marginHabit()` steps over trailing nulls to
  find the most recent entry but **stops the run at the first gap** ("in each of the last
  N rounds" has to be literally true); `herdRate()` and the MC herd fit share
  `gamesPlayedBy()`, which skips a member's null score rounds instead of charging them
  games they were never scored over.

## The aliveness filter is ONE-SIDED — the 100%-while-eliminated bug

- `finalsCtx()` used to drop any rival outside `me ± maxGain` **in both directions**.
  Dropping the provably beaten is safe. Dropping someone provably *ahead* is not: with
  the leader deleted from the model the DP sees no threats and returns **1**. Four points
  behind going into a one-game Grand Final, the panel read **"Chance of winning the comp:
  100%"**. The truth was 0%.
- The test is now `m.totalScore + maxGain >= me.totalScore` — only the provably beaten
  are dropped. An out-of-reach leader is **kept**, and the DP's own absorbing band
  returns 0 for that dimension, which is the honest answer. Verified against hand
  arithmetic at deficits 0/1/2/3/4.
- Related, and the reason the bug was survivable elsewhere: **`pctChance()` is the one
  formatter for any chance surface.** It prints `100%`/`0%` only for a value the solver
  proved exact, `>99.9%` / `<0.1%` at the edges, and 1 d.p. in both tails. Before it,
  99.77% rounded to "100%" — a certainty claim about a comp with three rounds left.
- And: **a split is armed only when the underdog is strictly worth more** (`vDog > vFav`).
  In a decided comp every line prices identically, and without this the panel printed
  `🎯 … +0.0 pts of win chance`, which is not advice. The **tie-break order is
  favourites → incumbent → LOCK_MODE**, not incumbent-first: the exact DP has no sampling
  noise, so incumbency buys nothing there and, leading by 30 with three rounds left, it
  armed three underdogs and swallowed the cover-mode line. Incumbency stays first in the
  Monte-Carlo path, where it exists to stop noise churning the flip feed.

## The cold-load transient: old tiplog tips flash for ~450 ms

- `compPlan()` returns a **provisional** plan immediately and solves on an idle callback.
  On a cold cache the provisional plan comes from the pipeline's frozen tiplog — which is
  normally correct, because the last workflow run computed it with this same code.
- **On the very first cold load after a deploy but before the first workflow run, it is
  not.** The committed tiplog still holds the *pre-rebuild* tips, so the page briefly
  showed `CRO-NQL→NQL  PEN-SYD→SYD` for ~450 ms before the solve corrected it. Measured,
  reproducible, self-correcting, and gone as soon as the pipeline runs once.
- It is harmless because `snapTips()` **refuses to snapshot a provisional plan** and the
  tiplog is unaffected. Do not "fix" it by making the first paint synchronous — that is a
  second of blocked paint on a phone, and Josh's rule is that the app just works with no
  narration. Do fix it by running the workflow promptly after a deploy (see below).
- **`PLAN_VER` (`'dp1'`) must be bumped whenever the solver's maths changes**, or a
  returning device reuses the previous model's cached plan out of `nrl_plan_v1`.
- `plan.provisional` is a state the old code did not have: anything that reads `plan.sim`
  must tolerate its absence for a few hundred milliseconds. The three current readers
  (`renderStratBits`, the `accComp` tile, the ledger split line) all null-guard it.

## Deploy ordering: `cloud_fetch.py` must run before `freeze_tips.mjs`

- The live `nrl_comp.js` has no `beh` until `cloud_fetch.py` runs with the new code. With
  the fallback rival model the tips are the **same**, but `pFirst` reads ~50% instead of
  ~46% and a split is priced at +0.3 rather than +2.0 — i.e. the *numbers on screen* are
  wrong-ish for one cycle even though the *decisions* are right.
- The workflow already orders it correctly (cloud_fetch → parse → learn → freeze). Verify
  it stays that way after any workflow edit. The freeze is safe either way because the
  page derives identity from `COMP_ME` rather than trusting the file's `me` flag — but
  don't lean on that.

## Finals cron slots, and the AEDT shift on Grand Final day

- Finals kickoffs are **earlier and doubled up** (R28: Sat 16:05 and 19:50, Sun 16:05),
  so the regular-season Saturday slot at 16:33 AEST fires *after* the first final has
  started — the difference between a tip frozen on live market prices and one frozen an
  hour stale. Four finals slots were added: Sat 15:35, Sat 19:07, Sun 15:35, Sun 18:45
  AEST (`35 5 * * 6`, `7 9 * * 6`, `35 5 * * 0`, `45 8 * * 0` in UTC).
- **Cron is UTC and Sydney is UTC+10 only until DST starts on Sun 4 Oct 2026 — which is
  Grand Final day.** Every Sunday line lands an hour later locally that day, and the
  "18:45" slot becomes 19:45, i.e. *after* a 19:30 kick-off. A fifth line (`45 7 * * 0`,
  17:45 AEST / 18:45 AEDT) covers it. Any future Sunday slot needs the same arithmetic —
  and if a schedule change crosses midnight, the day-of-week field has to move too.

## "Higher seed hosts" is WRONG for the preliminary finals

- The brief said "higher-ranked team is home in weeks 1–3". That is an approximation. The
  real NRL system, and what the code implements, is: **semi-finals hosted by the
  qualifying-final LOSERS, preliminary finals hosted by the qualifying-final WINNERS,
  Grand Final neutral.** The two differ whenever a seed-1 side loses its qualifying final
  and comes back through a semi.
- The audit walked all 256 week-1..3 outcome paths against an independently-built
  bracket: **0 matchup mismatches, 0 hosting differences.** It costs nothing this season
  (`homeAdv` is 0), but the code path is right and must stay right — a wrong host is a
  wrong probability in every downstream round.
- Related invariant, worth re-running if anyone touches the DP: **the absorbing band is
  exact, not an approximation.** Re-running the whole solve with the band widened by
  eight points in every dimension gives bit-identical values to 17 significant figures.

---

## Deploy / hosting

- **The live site is `index.html`, a *copy* of `nrl-tipping-guide.html`.** Editing the
  guide does nothing until the workflow runs `cp … index.html`. Symptom: "I changed the
  HTML but the site looks the same." Fix: run the workflow (or edit `index.html` too).
- **Raw/CDN caching hides fresh commits.** `raw.githubusercontent.com` and the Pages CDN
  serve stale copies for a while. Add `?v=<n>` to raw URLs when verifying, and hard-
  refresh the site. A "the file didn't change" panic is usually just cache.
- **Public repo is required** for free Actions + Pages. Don't make it private.
- **Schedules pause after 60 days of repo inactivity — and the bot's own commits DON'T
  count.** Pushes made with `GITHUB_TOKEN` do not reset the timer, so a repo that updates
  itself six times a day still goes quiet after two months. `keepalive.yml` now re-enables
  the workflow fortnightly via the API. GitHub emails the owner before disabling.
- **Scheduled runs are best-effort: routinely hours late, sometimes dropped entirely.**
  Measured on this repo: the 06:00-Sydney slot ran **3h44m late**; the noon slot **never
  fired**. Never schedule on minute `:00` (most congested), and never rely on one or two
  slots a day — run often instead (a full run is ~25s and free on a public repo).
  Corollary: **"the site didn't update" is not evidence the workflow is broken.** Check
  `last_run.json` first — it changes every run, so if its timestamp is fresh the job ran
  and the problem is in the data, not the schedule.
- **A green run can publish nothing.** `git commit … || echo "nothing changed"` means
  success ≠ published. That's why the heartbeat exists.
- **Editing files via the GitHub web editor / paste can corrupt large files.** Past
  incidents: a workflow YAML got *doubled* (paste appended instead of replacing →
  "'name' is already defined" / invalid workflow), and a base64 blob picked up a stray
  Cyrillic character that broke decoding. Prefer **drag-drop upload of the whole file**
  over in-browser paste for anything non-trivial, and verify with a raw fetch after.

## The sandbox may or may not have network — CHECK, don't assume
- This used to say flatly "the sandbox has no network". **On 2026-07-29 a full live run of
  `cloud_fetch.py` (nrl.com + zerotackle.com) succeeded from the local sandbox**, so the
  blanket claim is wrong and cost at least one session's worth of "I can't test that".
  Try one fetch first. If it fails with 403/tunnel errors you're in a sandbox without
  egress: test scraper **parsing** against saved or synthetic HTML and leave the live
  fetch to GitHub. The pure scripts (parse/learn/validate) run fine either way.
- When you do test the pipeline locally, run it in a scratch directory (copy the `.py`
  files and the dumps into `/tmp`), never in the project folder: `parse_nrl.py` appends to
  `nrl_learned.js`, which is **append-only, unrecoverable match history**.

## Odds are GEO-BLOCKED — a green run from Australia proves nothing (2026-07-30)
- **nrl.com withholds bookmaker prices from non-Australian IPs.** The 2026-07-29 odds
  scrape was verified end-to-end from an Australian machine — 8/8 fixtures priced — and
  published **nothing** from GitHub's US runners: run #28 committed a perfect
  `draw_meta.json` and no `odds_dump.txt`, same code, same endpoint, same minute. If an
  odds source works locally but `fixturesWithOdds` is 0 in `last_run.json`, suspect the
  egress IP before the code.
- **The Odds API is the primary source for exactly this reason** (geo-independent; needs
  the `ODDS_API_KEY` repo secret). nrl.com remains a fallback because it costs nothing
  and is correct when it answers. `last_run.json`'s `oddsApiState`
  (`no-key`/`bad-key`/`quota-exhausted`/`ok`) says which path a run took and why.
- **Never log, echo, or commit the key.** The repo is public. `cloud_fetch.py` redacts it
  from its own error output; keep it that way.
- **The free quota (500/month) fails silently when exhausted** — prices freeze rather
  than the run failing (best-effort by design). Watch `oddsApiRemaining` in
  `last_run.json`; if it hits 0 mid-month, thin the schedule.

## Weather was REMOVED end-to-end (2026-08-04) — don't reanimate it
- Josh: it wasn't affecting anything. Deleted from the scraper (`fetch_weather`,
  `CITY_COORDS`, `weather_dump.txt`), the parser (`parse_weather`/`apply_weather`/
  `--weather`, the change feed's weather category and rain-band logic), the model
  (`weatherEffect()` and the margin shrink), and the whole UI. The two 2026-07-30
  weather gotchas that used to live here (game-day matching; fetch-timeout line
  reuse) are history — do not re-add the feature to "fix" them.
- **Transition details that matter:** `fixture.weather` ships as an always-null key
  for one deploy cycle (CDN-cached old `index.html` copies still read it), then can
  be dropped; `chgList()` filters legacy `cat:"weather"` entries until the 36h
  window ages them out; the workflow deletes `weather_dump.txt` from the repo
  (idempotent `rm -f` before commit) — a leftover dump plus a leftover `--weather`
  flag would silently reanimate the feature.

## The player-ratings scrape (`cloud_fetch.py: extract_ratings`)
- **⚠ This section previously said the opposite, and that advice caused a real outage.**
  It claimed the ratings table has no player links and that names must be read from cells
  **positionally**. Both are wrong. The links are at `/players/<slug>/` — *not*
  `/rugby-league/players/…`, which is why an early version looked in the wrong place and
  concluded they didn't exist. Positional reading is what produced the **first-name-only
  keys** (`"nathan"`, `"harry"`, `"payne"`) that disabled every injury lookup for weeks:
  the `/overall/` page splits a player's name across **two cells**, so "the cell after the
  rank" is just the given name.
- **Scrape the nine PER-POSITION pages, not `/overall/`.** `/nrl-player-ratings/halfback/`
  etc. are real `<table>`s (`rank | Player | Team | Win % | Rating | move`) and the
  position is implied by the URL, which removes a whole class of column-order error.
  Take the name from the `/players/<slug>/` **anchor**, never a cell index.
- **The name is rendered TWICE inside the anchor**, unseparated — `Isaiah IongiIsaiah
  Iongi`, or abbreviated+full `K. Leuluai-GoingKalani Leuluai-Going`. `name_from_anchor()`
  uses the href slug as the canonical form to pick the right half. Same trick works on the
  team-lists pages.
- **A one-word key must never be emitted, and volume alone is not a valid publish gate.**
  `len(players) >= 100` passed happily on a file of pure garbage. The guard now also
  requires **≥80% of keys to contain a space** — a key that isn't a full name can never
  match the front-end, so it *is* a failed parse. Each page has a season table then a
  monthly one; the season table comes first and `setdefault` keeps it.
- **Name matching must line up across two feeds.** Injury names (injuries page) and
  rating names (ratings page) both come from Zero Tackle, so `norm_name()` (Python) and
  `normName()` (JS) must stay identical (lowercase, strip accents, keep apostrophes/
  hyphens). If you change one, change the other, or lookups silently fall through to
  "fringe player".
- **Only rated players are in the map** (roughly the top few hundred). Fringe/reserve
  players legitimately won't be found and are treated as low-impact by design — that's
  not a bug. But if *everyone* is scoring the 0.6pt fringe fallback, the map is broken —
  check `last_run.json`'s `playersRatedFullName` against `playersRated`.

## The injuries page and team lists
- **Club labels on the injuries page are bare `<a>` links, not headings.** Heading-based
  tracking found zero clubs, so `extract_injuries()` returned `{}` every run and the
  committed dump was silently reused forever. Attribute each table to the **nearest
  preceding team link** instead (`club_before()`). The team href can be either
  `/nrl/teams/<slug>/` or `/rugby-league/teams/<slug>/`.
- **Team lists live at ROOT level, not under `/nrl/team-lists/`.** The section index links
  out to `/round-21-team-lists-2026-236116/`. Fetch the index, take the highest round.
- **The squads are `<table>`s. There is not a single `<ul>`/`<li>` in the article.** A
  markdown/reader view of the page renders the rows as `- ` bullets, and a first version
  of `extract_teamlists()` was written against that illusion. It found no `<ul>` under any
  heading, so seven of eight games returned nothing — and the last heading, having no next
  heading to stop it, scanned off the end of the article into the **footer mega-menu**,
  whose `/players/oldest-youngest/`-style links look like player links. Result: "Off
  Contract 2026" was published as a Wests Tigers player. **Trust the DOM, not the rendered
  text.**
- **`<tr>` is left unclosed on every player row**, so `html.parser` nests the rows inside
  one another and `tr.find_all("td")` returns every descendant row's cells. Walk
  `.descendants` for a flat document-order token stream instead of parsing rows.
- **Identify a squad by what it CONTAINS, not by where it sits.** ≥13 player links *and*
  ≥13 bare jersey numbers. The number requirement is what makes a nav menu impossible to
  mistake for a team list — menus have links but never numbers. Then attach each squad to
  its *nearest preceding* heading. Scanning forward from a heading is the pattern that
  caused the footer bug.
- **There are no "Ins:"/"Outs:" labels** on the round article — it's squads only. The home
  table puts the jersey number *before* the name, the away table *after*; decide home/away
  from that orientation, not from document order (it also survives a half-published game).
- **Never cut the squad at "jersey number ≤ 17".** The number is not a selection signal —
  Parramatta named #22 at centre in Round 21 while #11 and #14 were on the bench. Cut at
  the `RESERVES` separator row instead. Reserves 20–22 are emergencies who may not travel,
  so counting them would wrongly cancel a genuine injury flag.
- **Team lists drop ~4pm Tuesday AEST.** Any cron that stops at noon will never see them
  on the day they're released. There's a dedicated Tuesday 16:23 slot for this.
- **A thin team-list parse on Mon/Tue morning is normal, not a failure** — the article for
  the upcoming round simply doesn't exist yet. `nrl_lineups.js` is left as-is, and
  `namedSquad()` ignores any lineup whose round ≠ the round being tipped.

## Data / model correctness
- **Injuries are applied to the model margin *before* the odds blend** on
  purpose — so when odds already price them in, the blend discounts them (no double-
  counting). Don't move them after the blend or add a second discount.
- **"Out this week" depends on the return round vs the round being tipped.** A player
  "back Round N" with N ≤ current round is *available* (0 penalty). Off-by-one here
  silently mutes or over-applies injuries.
- **Home/away designation matters and can look "wrong".** The app trusts the source's
  designated home team (e.g. a neutral/heritage venue). A past "Eels vs Tigers looks
  swapped" report turned out correct per the official listing. Verify against NRL.com
  before "fixing".
- **Best-effort fields are legitimately `null`.** odds/news/weather missing for a game is
  normal; the UI just omits them. Don't treat null as an error.

## Learning loop
- **`lowConfidence` intentionally ignores the learned model** under ~30 games. If tips
  look "too heuristic," check `nrl_learned.js.lowConfidence` — it's the guardrail, not a
  failure.
- **Never hand-edit `nrl_learned.js`.** It's the append-only match memory; corruption or
  a bad edit makes the generators abort (by design) to protect history.

## Friends' comp tips (2026-08-09) — footytips API
- **The comp endpoint is public (no auth, open CORS) — but a round's tips are
  SEALED server-side until the round starts.** Verified: requesting an
  unstarted round's who-tipped-what (API and logged-in UI both) gets clamped
  back to the last started round. An earlier claim that the API "leaks
  pre-lock picks mid-round" was WRONG — it came from mis-dating a Monday
  fetch of a finished round as a live Saturday capture. Whether an
  in-progress round exposes its not-yet-played games has never actually been
  observed. Either way `compLocked()` (kickoff passed per our own feed, or
  live/result evidence) is the display gate and is correct in every case; an
  "early picks" toggle built on the bad claim was added and removed the same
  night (2026-08-10).
- **Display names only.** The API carries members' full surnames; nothing in
  this app may render or store them.
- **`currentUser` is always false on anonymous calls** — "(you)" comes from
  the `COMP_ME` display-name constant, not the API. Since 2026-09-12 `COMP_ME` is the
  *only* source of identity: `compFromFile()` re-derives `me` by name and falls back to
  the file's flag only on a miss, and a name miss warns loudly. `pollComp()` dropped
  `!!u.currentUser||` from its test — a stray session cookie would otherwise mark a
  different member as "me" on each family member's phone, which is exactly the
  browser/freeze divergence class this app is built to avoid. Lockstep partner:
  `FOOTYTIPS_ME` in `cloud_fetch.py`.
- **Comp IDs live in the public repo.** Anyone reading the site source can
  fetch the comp's data (first names + picks + scores). Josh accepted this;
  if the comp ever objects, set `COMP_ID=0` and the feature vanishes.
- **Scoring, verified from `ladder.customScoringOptions` (2026-09-12)**: 1 point per
  correct tip; `allCorrectBonus {applyTo: Season, modifier: 2}` — +2 for a perfect
  round, **in finals rounds too**, so a one-game Grand Final round pays 3;
  `defaultScoreMethod: Zero` (no tip = 0); `rankByMargin: true` — a points tie goes to
  the **LOWER** cumulative margin error. The round's designated margin game is its
  **FIRST** game, checked against every member's published error in R24–R28. Don't
  re-derive any of this from the UI; read the API.

## Finals are rounds 28–31 — sources NAME them differently, the pipeline NUMBERS them (2026-09-07)

- **The season didn't end at Round 27 — the scraper's regexes did.** Zero Tackle's
  match-centre slugs switch from `…-round-27-2026-mc…` to
  `…-round-finals-week-1-2026-mc…` (then `-round-finals-week-2-`,
  `-round-preliminary-finals-`, `-round-grand-final-`), nrl.com's `roundTitle`
  becomes "Finals Week 1", team-list articles become `finals-week-1-team-lists-…` /
  `preliminary-finals-team-lists-…` / `grand-final-team-lists-…`, and the injury
  page's return column says "Finals". A digits-only regex reads all of that as
  "no round" and the app quietly sits on the last home-and-away round with
  `fixturesWithKickoff: 0`, `oddsApiState: not-attempted` in `last_run.json`. **All
  round naming goes through `parse_nrl.round_from_text()`** — never add another
  `round\s+(\d+)` regex to a source parser; extend that function instead (and its
  JS mirror `finalsReturnRound()` for injury text).
- **One numeric round everywhere; `roundName` is display-only.** Dumps say
  `<h2>Round 28</h2>` / `# Round 28 …` on purpose — `existing_draw()`,
  `existing_odds_round()`, `RESULT_ROUND_RE` and the draw-meta round check all read
  a number. Don't "improve" a dump header to "Finals Week 1".
- **A bare "week N" must NOT resolve to a finals round.** Zero Tackle names the
  Pacific Championships (October) and the pre-season challenge (February) articles
  `…-week-1-team-lists-…`; `latest_teamlists_url()` keeps the HIGHEST round, so a
  "week-1" → 28 reading would outrank `round-1-team-lists-2027` for as long as those
  articles sit on the index. `_FINALS_WEEK_RE` requires the word "finals", and
  `NON_PREMIERSHIP_RE` skips Origin / Pacific / pre-season / NRLW / All Stars slugs.
  Verified against every 2022–2026 premiership slug: none is skipped.
- **Club-count publish gates must shrink with the finals.** Zero Tackle's injuries
  page and team-list article only carry the clubs still alive (8 → 4 → 4 → 2). The
  regular-season gates ("≥6 clubs") would keep the *committed* file forever from
  week 2 on — a green run that silently freezes the injury table at the week-1
  snapshot. Both gates key on `FINALS_GAMES[rnd]` now; keep any new club-counted
  feed on the same rule.
- **"back Finals" changes meaning on finals day.** In-season it's long-term OUT
  (not before September). Once `SRC.finals` is true it means "expected back for the
  finals, week unspecified" → a half-weight DOUBT that the team list settles both
  ways; a *suspension* "back Finals" is a served ban → available. Dated forms
  ("back Finals Week 2", "back Grand Final") are ordinary dated returns. Reading
  the bare form as OUT would have costed the Roosters Crichton + Radley in the
  elimination final. Don't collapse these branches back into the long-term regex.
- **No byes in the finals — and the validator enforces it.** `compute_bye()` returns
  `[]` for round ≥ 28 and `validate_data.py` FAILS a finals payload with bye teams
  (or 0 / >4 fixtures) while skipping the "every team fixtured or on bye" rule.
  Idle teams are eliminated, not resting — nothing may print a nine-team bye line.
- **Between finals weeks the site shows the played week, and that's correct.**
  With no unplayed game on the fixtures page the run keeps the committed draw;
  nrl.com lists "TBA v TBA" which doesn't resolve. Don't "fix" this by inventing
  fixtures — the next pairings appear on Zero Tackle within a day of the last game.
- **`REGULAR_ROUNDS` (27) is a per-season constant** in `parse_nrl.py`,
  `validate_data.py` (`FINALS_START = 28`) and the HTML. Check it against the new
  draw every March.

## A tip's % is the TIPPED side's chance, never max(pHome,1-pHome) (2026-08-14)

- Any surface that prints a percentage next to the tip name must use the
  **tipped side's** blended prob (`tip===p.h ? pHome : 1-pHome`), NOT
  `Math.max(pHome,1-pHome)`. They're equal for straight favourites but diverge
  on a comp split (the tip is the underdog) and on a Roosters lock the model
  dislikes — where max() prints the OPPONENT's chance beside your tip
  ("Eels · 63%" when the Eels' own chance is 38%). The quick list had this bug
  until 2026-08-14. The frozen tiplog `prob` is already tipped-side-relative —
  match it. `Math.max()` is still correct for CONFIDENCE RANKING (how certain a
  game is), just never as the number shown next to the tip.

## The freeze must LOAD the prior tiplog — it is a simulator INPUT (2026-08-21)

- **`freeze_tips.mjs` inlines `nrl_tiplog.js` (the prior committed copy) into the
  jsdom page like every other data file. Never re-strip it** "to keep the freeze
  independent of its own output" — that was the original 2026-08-08 rationale, and
  it silently broke the moment the simulator started reading the tiplog:
  `myResolvedOK` (is my perfect round still alive?) goes through `gradedTip()` →
  `tiplogFind()`, and the incumbency tie-break reads `tiplogFind()` directly. A
  tiplog-less jsdom run models the +2 as dead from a round's first result onward
  and has no incumbency at all — so from the first Thursday-night result to the
  round's end, every freeze priced splits with different inputs from every real
  browser, froze a different tip, and announced its own artefact as a "Tip
  changed" flip (R25 SOU–NZW: freeze said NZW, every browser said SOU).
- **The independence worry is handled elsewhere**: the merge step reads the
  committed `nrl_tiplog.js` from DISK (`readTiplog()`), not from the page, and
  frozen entries never change post-kickoff. Loading the prior tiplog is exactly
  what a browser sees pre-run — that's the determinism invariant, not a violation
  of it. Incumbency then makes frozen splits a fixed point across runs instead of
  a browser-only behaviour.
- **Symptom to recognise**: What's new announces a flip that the Tips page
  doesn't show (or vice versa) while `nrl_data.js`/`nrl_comp.js` are identical.
  Before blaming cache, diff the sim's tiplog-dependent inputs: emulate the
  freeze in the page console with `TIPLOG=[]; SNAPS={}; COMP_PLAN=null` and
  recompute `compPlan()` — if the splits change, it's this class of bug.

## (SUPERSEDED 2026-09-12, in part) The comp simulator — perfect-round bonus & the top-4 objective (2026-08-15)

> **SUPERSEDED 2026-09-12.** The objective is now **pure P(1st)** — the top-4 and top-3
> terms are gone, so "don't drop top 4 back out" no longer applies. There is no lock, so
> "Josh's unlocked Roosters pick is `g.lock`" is history (and Josh is a *rival* now). In
> the finals `simComp()` is not what runs at all — `finalsPlan()` solves the bracket
> exactly. **What still stands, and matters more than ever:** the `bonusLive` gate, the
> "a perfect round covers the whole round including games already played" rule, and the
> `bwins` baseline. The finals solver reproduces all three exactly.

- **The +2 perfect-round bonus is modelled for the current round ONLY while it
  is in progress** (`bonusLive = cur.length>0`). A finished round's +2 is
  already inside `totalScore` from the API — awarding it again double-counts.
  Don't drop the `bonusLive` gate.
- **A perfect round is over the WHOLE round, including games already played.**
  `myResolvedOK` / `rivResolvedOK[]` precompute whether each tipper's perfect
  is still alive given resolved current-round games; one wrong resolved pick
  kills it. Draws (no winner) are neutral (don't break it). If you only
  checked the unresolved games you'd hand out phantom bonuses to someone who
  already dropped a game this round.
- **Josh's unlocked Roosters pick is `g.lock`, NOT the favourite.** He always
  tips the Roosters. The sim scored an unlocked Roosters game as a favourite
  tip until 2026-08-15 — wrong for scoring and doubly wrong for perfect rounds
  (a lost Roosters game breaks his perfect round). Locked Roosters games use
  the frozen lock tip.
- **The objective is `P(top4)+P(top3)+P(1st)`** — top 4 is Josh's floor goal
  and the least-noisy term (~2% vs top-3's ~0.5%). Don't drop top 4 back out.
- **The display baseline is "tip favourites ALL season" (`bwins`), a separate
  in-loop track — NOT the empty set (`wins[0]`).** The empty set still splits
  FUTURE rounds, so it reads ~tied with the chosen set (this round's single
  split is ~neutral) and made the panel look broken. `bwins` never splits, so
  it's the true play-safe number (~0.3% top 4 vs the strategy's ~1.5%). If you
  ever show a "straight" comparison, use `bwins`, not `wins[0]`.
- **A single round's split is ~EV-neutral for finishing position** (40k-sim
  verified). The value is the SUSTAINED policy, carried by the incumbency +
  policy-consistency tie-breaks below. Don't "fix" the machine to only arm
  splits that beat straight *this round* — that collapses to never-split and
  drops the odds to the play-safe floor.

## The comp simulator (2026-08-13) — determinism and time-consistency

- **The sim's seed comes from (season, round) ONLY — never the plan stamp.**
  A stamp-derived seed redraws the tape whenever standings tick, near-tied
  split sets then trade places between 4-hourly runs, and every trade is
  announced as a tip flip. Per-game KEYED draw streams (`draw('g|'+key,i)`)
  keep a game's simulated outcomes stable all round even as fixtures resolve
  out of the list. Don't "simplify" back to one sequential rng.
- **Future-me must play the machine's own policy** (≤2 dogs/round in pf≤0.62
  games while chasing). Modelling future-me as a straight-favourites tipper
  drove P(top 3) to zero and made every current-round split look worthless —
  which then argues against ever splitting (time-inconsistency). Same trap
  in reverse: the EPS tie-break toward the top-2 policy-consistent
  candidates exists because a single split's marginal value is genuinely
  below MC resolution against the ~14 future splits the sim assumes.
- **Incumbency is a feature, not inertia**: within EPS, splits already
  frozen in the tiplog stay armed. Removing this reintroduces flip-feed
  churn from pure MC noise.
- **The chances line is honest and small** (~0.1–1%). Don't "fix" it to look
  motivating; the audit's numbers were the same shape.
- **`compMarginOf()` reads the RAW `window.NRL_COMP`** — `compFromFile()`
  strips `totalMargin`, and the browser-poll members never carry it. The
  countback (lower margin wins ties) rides only in the file copy.
- **The adherence tally is per-device** (localStorage counts, `nrl_adh_v1`,
  labelled "since R{first}") — picks are only visible post-lock, so entered/
  matched can only ever be measured for locked games. Don't move raw picks
  or surnames into storage (privacy rule above).
- **The margin advice is deliberately BELOW the expected margin** (×0.85,
  logistic-inverted from the blended prob): countback is a lower-is-better
  cumulative error, margins are right-skewed, and the median beats the mean
  for that loss. Don't "correct" it up to the model margin. It assumes
  footytips puts the margin on the round's FIRST game.

## (SUPERSEDED 2026-09-12, in part) The comp-WIN objective (2026-08-10 audit rebuild)

> **SUPERSEDED 2026-09-12.** "Roosters lock first" is gone from `tipSide()`; the need
> bands are only a candidate filter (θ floored at 0.65) and the Monte-Carlo fallback;
> and P(win) is no longer "honestly ~0.1–1%" — Brigitte sits at ~45% in Finals Week 1,
> because she is one point off the lead with the countback in her favour. **Everything
> else in this entry is still live and still load-bearing:** the `predict()`/`tipSide()`
> seam, the determinism rule (everything the tip depends on ships in a data file), the
> anti-tilt rule, matched-split exclusion, oddsW 0.75 + `oddsWeightLearned`, and the
> `.mkt` logging.
- **`tipSide()` is now a DECISION POLICY, `predict()` stays an honest
  estimator — never blur that line.** Don't shade `pHome` to justify a split,
  and don't move strategy out of `tipSide()`: the freeze, grading, every
  surface and the flips feed all assume that single seam.
- **Determinism rule: everything the tip depends on ships in data files.**
  Rival profiles + standings live in `nrl_comp.js` (pipeline-computed). Never
  reintroduce client-fetched inputs to `tipSide()` — the 2026-08-10 first cut
  had profiles in localStorage and the freeze would have frozen DIFFERENT
  tips than the browser showed.
- **The split cap and θ come from the (gap, rounds-left) bands ONLY** — a
  failed split must not change aggression except through the gap itself
  (anti-tilt, audit consensus). Matched splits (ahead-cluster not on the
  favourite) are excluded — EV burn, zero rank movement.
- **oddsW 0.5 was never learned** — it was a default mislabelled in prose.
  Now 0.75 prior + `oddsWeightLearned` flag; the front-end ignores the
  learned value unless the flag is true. `tiplog .mkt` is the accumulating
  odds history that will make it fittable — don't strip that field.
- **P(win) is honestly ~0.1-1%.** The policy is ~10× better than straight
  favourites, not a miracle. UI shows need/splits, never promises.

## (SUPERSEDED 2026-08-13, and again 2026-09-12) Comp strategy mode (2026-08-10)

> **SUPERSEDED 2026-09-12.** "The 🎯 note never touches the Roosters game" is exactly
> backwards now — in R28 the Roosters game was the single most valuable decision on the
> board (−6.5 pts of win chance to tip them). The ≤2-splits cap is gone too: the exact
> solver arms whatever set maximises P(1st), which is usually 0 or 1 splits and is
> priced, not capped. `predictPick()` survives only as the **fallback** rival model when
> `nrl_comp.js` ships no fitted `beh`. **Keep the Brigitte/Claire loyalty example below
> for a different reason than it was written**: it is now a record of *the user's own*
> tipping history (she tipped SYD 24/24 in 2026), which is why the app must tip *for*
> her rather than *as* her — her affinities are deliberately not an input to the tip.
- **Strategy is ALWAYS ON at Josh's direction** ("nobody else will see this
  page") — every surface still checks `getStrat()`, so re-gating is a
  one-line change if a family member ever finds the URL.
- **The 🎯 note never touches the Roosters game and never suggests more than
  2 splits a round.** Splits are variance plays, not EV plays — scattergun
  contrarianism is how Susie loo got to last place. Don't raise the cap.
- **`predictPick`'s loyalty tie-break is load-bearing**: a ≥75% underdog
  loyalty flips the prediction only if it beats the favourite-side loyalty
  (Brigitte tips Panthers 83% but Roosters 100% — R3 head-to-head confirmed
  she takes the Roosters). Validated live on R24: 8/8 predictions confirmed
  by Josh (incl. the tie-break game).
- **History cache stores affinity COUNTS, never raw rounds or surnames**, and
  `fetchCompHistory` fetches sequentially, only rounds it lacks.

## Tip flips in the feed (2026-08-08) — and the mid-game freeze guard
- **A ko-less fresh entry must NEVER overwrite an existing tiplog entry.**
  nrl.com blanks a fixture's kickoff WHILE the game runs, so `freeze_tips`
  sees it as "no kick-off ⇒ still upcoming" and would re-freeze a tip
  mid-game — run #84 actually did this to SOU–PAR before the guard existed
  (same side both times, no harm done). A stale pre-game tip is always
  legitimate grading input; a mid-game overwrite never is. No flip is recorded
  for a guarded entry either — it would be a phantom "tip changed".
- **Flips are pipeline-only.** The front-end renders `NRL_TIPLOG.flips`
  verbatim; it never computes its own flips (a browser comparing an old
  in-memory tip against a refreshed one would duplicate the pipeline's record
  or invent flips from partial data).
- **The feed shows only the LATEST flip per game (2026-08-21)** — `chgList()`
  dedupes on the unordered pair, newest `ts` wins; the full history stays in
  `nrl_tiplog.js`. Don't "restore" the older rows: two flips for one game in
  the window read as contradictory headlines (seen live on R25 SOU–NZW, where
  the divergence artefact and its correction coexisted — and the OLDER one
  sorted on top because same-sev/same-cat rows had no time tie-break; both
  group sorts now end `chgTs(b)-chgTs(a)`).
- **`contentStamp()` must include the flips** (count + last ts) or a refresh
  that only delivered a flip won't re-render and the feed stays stale.

## Grading tips: never grade a recomputed tip (2026-08-02)
- **The model's opinion of a finished game is contaminated by that game.** After full
  time, `learn_model` refits the Elo WITH the result, and the market price disappears —
  so `tipSide()` recomputed post-game can flip to the winner and "grade" itself ✓ for a
  tip that was never shown (BRI v NEW R22: pre-game blend said Broncos, post-game
  recompute said Knights, Knights won, card claimed "got it"). Any ✓/✗ must come from
  the **pre-kick-off snapshot** (`nrl_snap_v1` in localStorage, written by `snapTips()`
  on every render before kick-off) — key `nrl_snap_v2` since 2026-09-12. There is no
  third fallback any more: the lock rule used to be one ("the Roosters tip needs no
  snapshot — it's a constant"), and it is gone. **No tiplog entry and no snapshot → say
  "final — no pre-game tip on record", never guess.** See the `myResolvedOK` entry at
  the top of this file for the trap that hides inside that deletion.
- **Freeze server-side, and never by reimplementing the model.** `freeze_tips.mjs`
  exists so the frozen tip is the same on every device — and it deliberately runs
  the REAL page in jsdom rather than mirroring the math in Python/Node, because a
  second implementation silently drifts (see the smoke-test WARN that's been firing
  for exactly that reason). If you change the front-end model, the freeze follows
  automatically; don't "optimise" it into a reimplementation.
- **"Season accuracy" numbers are three different things — label which.** The 64% is
  the walk-forward *backtest* (what the model would have tipped across the whole results
  memory); 14-5 is the *team's* W-L; "your tips" is only what was frozen before
  kick-off. Presenting any of them as one of the others reads as a bug to the user —
  because it is one.

## (SUPERSEDED 2026-09-12) The Roosters lock and the change feed (2026-07-29)

> **SUPERSEDED 2026-09-12 — the lock no longer exists.** Kept because three of its five
> bullets are about other things and are still true, and because the *shape* of the
> first bug (a rule that four surfaces only annotated instead of applying) is the reason
> `tipSide()` is still the single seam. Read it as: **the DECISION is applied in exactly
> one place, `tipSide()`, and every surface that names a tip must call it.** The team
> list, change-feed sort-order, "never emit a change the model can't feel" and
> line-move-attribution bullets are untouched by the lock's removal. "`predict()` must
> stay lock-free" generalises to **`predict()` must stay strategy-free**.
- **The lock is applied in exactly ONE place: `tipSide()`.** Any surface that names a tip
  must call it. Four of them once recomputed `pHome>=0.5?h:a` and only *annotated* the
  Roosters game, so `copyTips()` pasted `Cowboys v Roosters → Cowboys (locked)` whenever
  the model disagreed — and the whole "Roosters tax" measured a rule that wasn't applied.
  The bug is **latent on the heuristic engine** whenever it happens to like the Roosters;
  test with `lowConfidence:false` (the Elo path) before believing a lock change works.
- **The team list cuts both ways on doubts (2026-07-30).** `namedSquad()` clears an
  injury-table entry for a player who IS named — and upgrades an undated doubt to a
  full-weight absence (badged NOT NAMED) for a player who ISN'T, once this round's list
  exists. Don't re-soften that: a doubtful player left at half weight after Tuesday is
  how Tom Dearden read as a mere "doubt" during a game he wasn't playing in. Pre-release
  (or a stale lineups file) `namedSquad()` returns null and doubts stay doubts.
- **`predict()` must stay lock-free.** The ledger's loyalty-pick line and the
  walk-forward tax depend on the model's own, unlocked opinion. (The pinned
  `lockHero` banner was removed 2026-08-08 — the Roosters card sits in normal
  bucket order; don't reintroduce a pinned hero without Josh asking.)
- **The change feed's sort order IS the truncation policy.** `merge_changes()` sorts
  `(sev, ts)` desc before `kept[:CHANGES_MAX]`. Put `ts` first and severity becomes a
  same-second tie-break: 60 trivia entries then evict a spine player's "out of the 17"
  inside its own window. Display order is the front-end's job, not this list's.
- **Never emit a change entry for a difference the model can't feel.** (The worked
  example here used to be weather's 20-point rain bands — weather is gone, but the
  principle stands for any future feed: key the entry id on the band/threshold the
  model actually responds to, never the raw string, or trivia floods the window.)
- **A line-move entry may only name a "firming" side when exactly one price
  shortened (2026-08-04).** `build_changes()` used to attribute direction whenever
  the home price differed — so both-prices-lengthen (a vig change, nobody's money)
  got pinned on a team. The front-end's `oddsHTML()` had this rule first; the feed
  now mirrors it (`team:null, dir:neutral` otherwise).

## Live scores (2026-08-08) — why ESPN, and what not to "fix"
- **nrl.com's JSON cannot be read from a browser.** `/draw/data` has live scores
  and a clock, but sends no `Access-Control-Allow-Origin` header — tested. Don't
  swap the front-end's live-score source back to nrl.com "because it's official";
  the fetch will silently fail on the live site. ESPN's
  `site.api.espn.com/…/rugby-league/3/scoreboard` sends `ACAO: *` and is the only
  reachable source. (Its Akamai edge 403s a *spoofed* browser user-agent from a
  datacenter IP — a sandbox test that fakes a UA can look broken while real
  browsers work fine. Test with a plain client UA, or from an actual browser.)
- **The live overlay must stay display-only.** `LIVE` feeds cards/hero/quicklist/
  schedule and NOTHING else. Grading, the results memory, the tip log and the
  model never read it — an ESPN score grading a tip into the record would
  reintroduce the 2026-08-02 hindsight class of bug via a third-party feed.
  `fixtureResult()` is checked before `liveFinal()` at every call site: the
  pipeline's result always wins once it lands.
- **Score ticks must never call `render()`.** A full render rebuilds `#games` and
  collapses every open fold — 45-second polling would make folds unusable. Only
  `renderLiveBits()` (live cards are foldless, replaced in place) plus the
  fold-free surfaces. Corollary: don't add a `<details>` fold to the live card.
- **The live tip pill shows the FROZEN tip** (`gradedTip`: tiplog → snapshot; the
  third step, the lock, was removed 2026-09-12), falling back to `tipSide()` only when
  no frozen tip exists. Same rule now applies to `copyTips()`, which used to re-derive
  a kicked-off game's tip with `tipSide()` and so contradicted the card and the tiplog
  the moment a game started (2026-09-12 audit). A mid-game
  `tipSide()` recompute is contaminated (odds vanish at kick-off) — same rule as
  full-time grading.
- **`pollLive` must stay guarded on `typeof fetch`.** `freeze_tips.mjs` boots the
  page in jsdom (no `fetch`); an unguarded call would throw on every workflow run.
  The 45s interval is killed by freeze's `window.close()` like the 5-minute one.
- **nrl.com's draw meta can DROP a fixture's kickoff while the game is in play**
  (R23 MEL v MAN published `kickoff:""` mid-game on the feature's first day) — so
  the live window can't be kickoff-only. `livePollList()` also polls a
  kickoff-less, result-less fixture on any game day (a same-round kickoff within
  **±36h — was ±12h until 2026-08-13**, when PEN–SYD was the day's ONLY game, every
  other kickoff was 21h+ away, and the live score vanished mid-match) and lets
  ESPN's state decide. `pollLive()` must also add TODAY's date to the ESPN query
  when a polled fixture is kickoff-less — the blanked game contributes no date of
  its own, and a range built from the round's other kickoffs skips it. Don't
  "simplify" any of this back to pure kickoff-window logic, and don't narrow the
  window without checking the solo-Thursday-game case.
- **The status-bucket sort lives in `render()` and ONLY there.** It must run on
  `fxList` before `predict`/`snapTips`/rank/upset (index-paired arrays), and
  `renderLiveBits()` must never reorder/insert/remove cards or `.gsec` dividers.
  A mid-poll bucket change sets `ORDER_DIRTY`; the reorder waits for foreground
  return — EXCEPT within 15s of the last full render (`LAST_FULL_RENDER`),
  where it renders immediately. Don't remove that grace window: without it a
  fresh open mid-game boots before the first ESPN response and the live game
  sits under "Up next" until the user backgrounds the app. And don't widen it:
  past ~15s the user may be mid-read with folds open.
- **The quick list + copyTips run in WEEK order (`weekOrder()`), not the cards'
  bucket order** (2026-08-08 later, Josh's call: "list them in order of the
  week"). Kickoff order is state-independent, so live ticks can't re-sort it —
  which is also why the old `CARD_ORDER` freeze could be deleted. Don't "unify"
  the two surfaces onto one order; they answer different questions.
- **A lingering `post` entry is load-bearing, not litter.** It renders the FT card
  during the hours before the pipeline appends the official result. Don't "clean
  up" `LIVE` when the poll window closes.

## Front-end
- **No CDNs, no `sessionStorage`/external storage** — must work offline as a local file;
  `localStorage` only.
- **`touch-action:manipulation` lives in the universal `*` rule on purpose (2026-08-13).**
  It's the iOS double-tap-zoom fix. A selector list misses tappable surfaces and the
  zoom comes back; `user-scalable=no`/`maximum-scale=1` in the viewport meta is NOT an
  acceptable substitute — it kills pinch zoom (accessibility).
- **Preserve the render element IDs** and the `predict()`/`modelFav()`/`tipSide()` seam
  (see `FRONTEND.md`). *(This used to say "and the Roosters lock" — removed
  2026-09-12. `rkTax` is out of the ID list; `accComp` is in.)*
- **The service worker is network-first on purpose.** `sw.js` tries the network first and
  only falls back to cache when offline, so it can't get "stuck" serving a stale shell —
  the classic cache-first SW trap that this was built to avoid. To nuke all caches, bump
  `CACHE` (`nrl-tips-vN`). SWs run only over http(s); `file://` use is unaffected. Don't
  switch it to cache-first "for speed" without a version-bump story, or staleness returns.

## iOS 62px dead strip (2026-08-18, WebKit bug 301994) — NEVER re-add `viewport-fit=cover`

- **The symptom is invisible in this app** — that's the landmine. With
  `viewport-fit=cover` in the viewport meta, iOS 26.5.2/26.6/27-beta sizes a standalone
  home-screen web view **62px shorter than the screen and top-anchors it**: a dead,
  unpaintable, iOS-default-black band sits at the bottom, ignoring `theme-color` and
  manifest colours. Our dark navy theme camouflaged it perfectly; the tab bar the app
  believed was flush with the screen edge was actually 62px above it. No DOM element
  can paint the band (a `100lvh` `z-index:-1` painter clips at the viewport edge —
  proven by probe on-device). Diagnosed and fixed in the Fit booking tool project on
  18 Aug 2026 (its `docs/IOS-VIEWPORT.md` + `DECISIONS.md` D-48 have the full
  measurement story); this app got the same fix the same day.
- **The fix is removing the attribute** — without cover the same short view seats
  BELOW the status bar and ends flush at the physical bottom (normal app geometry).
  **It takes effect per INSTALL**: after any deploy that touches the viewport meta,
  delete and re-add the home-screen icon or nothing changes on the phone.
- **Without cover, `env(safe-area-inset-*)` report 0 — always.** Never write `env()`
  inline again; use the `:root` vars `--sat`/`--sab`/`--sal`/`--sar`. Two JS
  backstops ("safe-area backstops" script at the end of the guide) restore
  `--sat`/`--sab` by measured shortfall (`screen.height - innerHeight`: ≤8px
  full-bleed → 62/34; 40–200px letterboxed → 0/34; else nothing), iOS+standalone
  gated, env-wins, self-undoing, re-run on resize/rotate, held during pinch zoom.
  **Letterboxed top is 0 on purpose** — the status bar is above the view; restoring
  62 there double-pads the header. If Apple fixes 301994 the backstops silently hand
  back to `env()`; no redeploy needed.
- **`test_ios_viewport.py` (repo root) is the regression net** — Playwright, shims
  `navigator.standalone`, proxies `screen.height`; includes a static check that the
  meta never regains `viewport-fit=cover`. Run it after ANY change near the viewport
  meta, the `--sa*` vars, `.topnav`/`.tabbar` padding or the backstop script. Every
  piece of the backstop is individually mutation-tested — keep it that way.
- Trigger detection is **geometry-only, never UA version** — standalone iOS UAs
  freeze/lie about the OS version (26.6 reports "OS 18_7").

## 2026-08-04 batch — new landmines (audit + rebuild)

- **`logisticScale` is statistically unidentifiable — NEVER re-add it to the grid
  search.** In `predict_phome` the scale cancels exactly for the Elo term, so the
  walk-forward loss only sees `homeAdv/scale`; the old grid used it as a lever to
  inflate the underweighted home edge and always drove it to the grid minimum (5),
  which made every injury penalty ~40% more potent at inference than designed. It is
  pinned at 7 in `learn_model.py` and still published in `params` (the front-end and
  the freeze read it).
- **Opening odds must be carried forward in FULL rebuild mode.** `apply_odds()` used
  to set `open = close = fresh` every run, and the workflow always runs full rebuilds
  — so `open` was destroyed every 4 hours, `resolveOdds().moved` was permanently
  false, and the "Line moved / Bookies (open)" UI could never fire. Full mode now
  inherits the previous published `open` for the same round + fixture pair
  (orientation-corrected); it seeds `open = fresh` only on first sighting.
- **(SUPERSEDED 2026-09-12) The loyalty tax must come from `backtest.lockTax`**
  (walk-forward, computed server-side from pre-game Elos) — never recompute it in the
  browser. The old front-end `modelFavoursHome()` graded past Roosters games with the
  CURRENT Elo, which already contains each game's own result — the exact hindsight
  pattern the 2026-08-02 entry above bans. That function is deleted; if `lockTax` was
  absent the UI showed nothing.
  > **`lockTax` itself is gone as of 2026-09-12** (with `LOCK_TEAM` and
  > `lock_tax_metrics()` in `learn_model.py`, and `#rkTax` in the page) — there is no
  > forced pick left to tax. `validate_learned.py` never required the key, so the
  > publish gate is unchanged. **The principle survives and still binds every future
  > stat: never grade a past game in the browser from current Elo.**
- **Injury names must be plausible names.** A Panthers stats table (`P | W | L`
  cells) was scraped as player "P", reason "W", return "L" — a live phantom entry
  worth real model points, and the NOT-NAMED rule would have upgraded it to full
  weight on Tuesday. `extract_injuries()` now rejects rows whose cells are all ≤2
  chars and requires a plausible name (≥2 words / ≥4 letters / a `/players/` link);
  `looks_like_player` (Python) and `looksLikePlayer` (JS) both reject 1–2 letter
  names — keep the two copies identical, same as `norm_name`/`normName`.
- **Results carry a `season` field now; every reader must stay season-aware.**
  Dedup is on (season, round, home, away); missing `season` defaults to 2026. Without
  this, a 2027 game repeating a 2026 round+pairing is silently dropped, the Elo
  replay's chronology scrambles at the boundary, and in March 2027 the front-end
  would show last year's score as "Full time" for an unplayed fixture.
- **Grading keys are unordered team pairs.** `freeze_tips.mjs` and `myRecord()` key
  on `[home,away].sort()` (stored orientation kept for display) so a home/away
  orientation flip between runs can't double-grade one game.
- **Kick-off rows must never print locale tz abbreviations.** The What's-new schedule
  originally used `Intl` zone names — en-US ICU renders "GMT+10", which truncated
  every row on the phone. The schedule uses the local `kt()` time-only formatter
  (ground-local); the card's venue box remains the place for the fully-zoned time.
- **`refreshFromNetwork()` must remove its `<script>` tags and no-op on an unchanged
  `contentStamp()`.** With 5-minute polling, forgetting either means unbounded DOM
  growth or a re-render every 5 minutes that collapses whatever fold the user had
  open. Both behaviours are load-bearing, not polish.
- **The repo's workflow and the local `.github/workflows/` copy can diverge — always
  edit from the LIVE copy.** The local copy was one revision behind and lacked the
  "Freeze pre-kick-off tips" step; uploading it as-is would have silently killed the
  tip log. Fetch the live file (raw URL) before editing, or use the staged copy in
  `update docs for upload/github-workflows/`.
