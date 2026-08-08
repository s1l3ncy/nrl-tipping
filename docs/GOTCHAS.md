# Gotchas — landmines already hit (read before deploying)

Real problems encountered on this project and how to avoid repeating them.

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
- **`contentStamp()` must include the flips** (count + last ts) or a refresh
  that only delivered a flip won't re-render and the feed stays stale.

## Grading tips: never grade a recomputed tip (2026-08-02)
- **The model's opinion of a finished game is contaminated by that game.** After full
  time, `learn_model` refits the Elo WITH the result, and the market price disappears —
  so `tipSide()` recomputed post-game can flip to the winner and "grade" itself ✓ for a
  tip that was never shown (BRI v NEW R22: pre-game blend said Broncos, post-game
  recompute said Knights, Knights won, card claimed "got it"). Any ✓/✗ must come from
  the **pre-kick-off snapshot** (`nrl_snap_v1` in localStorage, written by `snapTips()`
  on every render before kick-off) or from the lock rule (the Roosters tip needs no
  snapshot — it's a constant). No snapshot, no lock → say "no pre-game tip on record",
  never guess.
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

## The Roosters lock and the change feed (2026-07-29)
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
- **The live tip pill shows the FROZEN tip** (`gradedTip`: tiplog → snapshot →
  lock), falling back to `tipSide()` only when no frozen tip exists. A mid-game
  `tipSide()` recompute is contaminated (odds vanish at kick-off) — same rule as
  full-time grading.
- **`pollLive` must stay guarded on `typeof fetch`.** `freeze_tips.mjs` boots the
  page in jsdom (no `fetch`); an unguarded call would throw on every workflow run.
  The 45s interval is killed by freeze's `window.close()` like the 5-minute one.
- **nrl.com's draw meta can DROP a fixture's kickoff while the game is in play**
  (R23 MEL v MAN published `kickoff:""` mid-game on the feature's first day) — so
  the live window can't be kickoff-only. `livePollList()` also polls a
  kickoff-less, result-less fixture on any game day (a same-round kickoff within
  ±12h) and lets ESPN's state decide. Don't "simplify" that back to pure
  kickoff-window logic.
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
- **Preserve the render element IDs and the Roosters lock** (see `FRONTEND.md`).
- **The service worker is network-first on purpose.** `sw.js` tries the network first and
  only falls back to cache when offline, so it can't get "stuck" serving a stale shell —
  the classic cache-first SW trap that this was built to avoid. To nuke all caches, bump
  `CACHE` (`nrl-tips-vN`). SWs run only over http(s); `file://` use is unaffected. Don't
  switch it to cache-first "for speed" without a version-bump story, or staleness returns.

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
- **The loyalty tax must come from `backtest.lockTax` (walk-forward, computed
  server-side from pre-game Elos) — never recompute it in the browser.** The old
  front-end `modelFavoursHome()` graded past Roosters games with the CURRENT Elo,
  which already contains each game's own result — the exact hindsight pattern the
  2026-08-02 entry above bans. That function is deleted; if `lockTax` is absent the
  UI shows nothing.
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
