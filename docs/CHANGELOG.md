# Changelog & decision log

Dated record of the significant changes and *why* they were made, so a future reader
understands the reasoning, not just the diff. Newest first.

---

## 2026-08-15 — Perfect-round bonus in the current round; top-4 objective; honest "play safe" baseline

Josh asked whether the +2 perfect-round bonus (all games in a round tipped
right → +2, paid at round end) was in the simulator. It was — for FUTURE
rounds only. Three linked changes, all surfaced by his question.

**1. Current-round perfect bonus (`simComp`).** The sim now awards the +2 for
the current round too, for Josh and every rival — but ONLY while the round is
in progress (a finished round's +2 is already inside `totalScore`; adding it
again would double-count, so it's gated on `cur.length>0`). Crucially it's
*alive-aware*: a wrong pick on a game ALREADY PLAYED this round kills the
perfect round, so `myResolvedOK` / `rivResolvedOK[]` are precomputed from
resolved current-round games (draws treated as neutral). A current-round
split now correctly forfeits Josh's +2 unless its underdog wins — the real
cost of splitting, finally priced.

**2. Roosters-underdog pick fix (same function).** For an UNLOCKED Roosters
game the sim was scoring Josh as tipping the favourite; he always tips the
Roosters (`g.lock`), often the underdog. Fixed — matters doubly now that a
lost Roosters game breaks his perfect round. (Locked Roosters games already
used the frozen lock tip.)

**3. Objective now includes top 4, and the baseline is honest.** The utility
was `P(1st)+P(top 3)`, omitting top 4 — Josh's actual stated goal ("top 4 at
least"). Now `P(top 4)+P(top 3)+P(1st)` (equal weight → 1st worth 3, top 3
worth 2, top 4 worth 1; ambition rewarded, floor valued). Top 4 (~1.5%) also
resolves at 3k sims where top 3 (~0.4%) barely does. And the panel's
comparison baseline changed from "empty set THIS round" (which still splits
future rounds, so it read ~tied — misleading) to **tipping favourites ALL
season** (`bwins`, a separate in-loop track). The honest read at ship:
following the machine gives top 4 ~1.5% vs ~0.3% tipping chalk all year —
the split strategy roughly 5×'s the floor goal, which the old same-round
baseline completely hid.

**Key finding recorded:** any SINGLE round's split is ~EV-neutral for finishing
position (verified at 40k sims: split vs straight this round were identical on
1st/top3/top4) — the value is entirely in the SUSTAINED policy. The
incumbency + policy-consistency tie-breaks (2026-08-13) are what commit the
machine to that policy despite each round looking individually neutral; they
stay. The panel now says so plainly ("the season-long chase is what earns the
gap; any one round barely moves it") rather than implying this round's split
beats straight.

Display-only + strategy-layer; `predict()` untouched. Freeze re-ran with 0 tip
changes (the Eels split is retained). Determinism verified. `sw.js` CACHE v19.

---

## 2026-08-14 (later) — Quick list showed the favourite's % on a split, not the tip's

Josh spotted "Eels · 63%" on the quick list when the Eels are a comp SPLIT —
63% is the *Cowboys'* chance; the Eels' own is 38%. `renderQuicklist()` paired
`tipSide(p).name` (the tipped side — the underdog on a split) with
`Math.max(pHome,1-pHome)` (the *favourite's* confidence). Identical for
straight favourites (tip == favourite), wrong for splits and for a Roosters
lock the model dislikes. Now prints the **tipped side's** blended win chance
(`tip===p.h ? pHome : 1-pHome`), matching the frozen tiplog `prob` and the
card. Verified on the live round: Eels 38%, Rabbitohs split honest, straight
favourites unchanged, Roosters lock shows its true 48%. Display-only — the
freeze re-ran with 0 tip changes. `sw.js` CACHE v18. The card, copy-tips and
week-ahead schedule were audited and were already correct (the card names the
favourite explicitly and shows the tip pill separately).

---

## 2026-08-14 — Pre-game odds slots in the schedule

Josh asked whether the tip tracks odds moves: it does, but only as often as
the workflow runs, and the 4-hourly grid's last look before some kickoffs
was ~3h stale. Four weekly cron slots added (AEST: Thu 18:43, Fri 19:07,
Sat 16:33, Sun 13:07 — off-hour minutes per the scheduling notes) so the
frozen tip carries a market price from ~1h before the round's typical
kickoffs. ~+17 odds-API calls/month on top of ~240 (free tier 500 — watch
`oddsApiRemaining`). In AEDT they fire an hour later local and still land
pre-game. Workflow file only; edited from the live copy per GOTCHAS.

---

## 2026-08-13 (night) — Monte-Carlo season simulator drives the splits; chances panel; margin adviser; adherence loop

Josh: "Ultimately I want to put my chances of coming 1st or at least top 3
up." Objective chosen (explicitly): **balanced — winning is worth ~2× a
podium**, so the machine maximises U = P(top 3) + P(1st).

**The simulator (`simComp()`, in-page).** The 2026-08-10 need-band split
selection is replaced by a priced one: every candidate split set for the
current round is scored by simulating the rest of the season 3,000 times —
current round with real games (blended probs; rivals' actual picks once
visible, else `predictPick()`), future rounds as generic games where each
rival herds the favourite at a rate fitted to their season accuracy
(`h=(acc+p̄f−1)/(2p̄f−1)`), everyone shares each simulated outcome (herding
correlation), +2 perfect-round bonus, and points ties resolved by the real
margin countback. Future-me plays the SAME machine policy (up to 2 dogs a
round in pf≤0.62 games while chasing, cover when ahead) — modelling
future-me as a straight-favourites tipper zeroed P(top 3) and made every
current split look worthless. Key engineering:
- **Deterministic**: mulberry32 PRNG, seed from (season, round); per-game
  KEYED draws so the tape is stable all round even as fixtures resolve out.
  Browser and jsdom freeze derive byte-identical tips (verified: freeze run
  recorded exactly the 2 intended flips).
- **Common random numbers**: rival totals simulated once per iteration;
  candidate sets are ranked against the same tape (paired comparison).
- **Tie-breaks within EPS=0.003 of best U**: (1) incumbency — splits already
  frozen in the tiplog stay, so MC noise can't churn the flip feed; (2)
  policy consistency — the top-2 candidates by (1−pf)·foes, matching the
  simulated future schedule (fixes the time-inconsistency where each round's
  marginal split looks individually worthless); (3) fewer splits.
- Band selection survives as the fallback if the sim throws; the audit's
  guards stay (never the Roosters, matched-split exclusion, need<0.5 → no
  splits, anti-tilt inputs only).
At ship (R24, 14 behind, 8 rounds left): 2 splits armed — SOU (40%), PAR
(38%) — honest chances line "1st <0.1% · top 3 0.5%".

**Chances panel**: the comp-panel strategy line now leads with P(1st) /
P(top 3) and what straight tips would sit at.

**Margin adviser + countback**: footytips ranks equal scores by cumulative
margin, LOWER first (it's why Brigitte 416 ranks above Claire 426 at 112
each; Josh and Thorners are tied 447). The panel now shows each member's
countback (±N) and, pre-lock, a recommended margin for the round's first
game (the margin game): 0.85× the logistic-inverted blended margin — the
median play, since margins are right-skewed and blow-out entries poison the
countback.

**Adherence loop** ("You vs the machine"): once games lock, footytips shows
what was actually entered — the panel compares Josh's real picks against the
frozen machine tips: entered n/N, matched, and the running cost of
deviations and missed entries (his audited historical leaks: ~4 pts to
unentered tips, 61 coin-flip dog picks). Counts only, accumulated per-device
in localStorage (`nrl_adh_v1`), labelled "since R{first}".

Files: `nrl-tipping-guide.html`, `sw.js` CACHE v17. No pipeline changes; the
freeze picks the new policy up automatically (by design — it runs the page).

---

## 2026-08-13 (later) — Live-poll survives a blanked solo-game kickoff; comp picks de-bubbled

Mid-match (PEN–SYD, the day's only game), Josh reported the live score gone
and the game card sunk to the bottom. Root cause was NOT the earlier batch:
the 20:45 workflow run republished data after nrl.com blanked the fixture's
kickoff mid-game (the documented landmine) — and `livePollList()`'s "game
day" test for kickoff-less fixtures required another same-round kickoff
within ±12h. Tomorrow's games were 21h away, so the test failed, ESPN was
never polled, `LIVE` stayed empty, and the card rendered as a kickoff-less
pre-game card (which sorts to the bottom of Up next, showing the Predicted
strip instead of a score).

**Fixes** (`nrl-tipping-guide.html`, `sw.js` CACHE v16):
- The game-day window for kickoff-less fixtures is now **±36h** — spans a
  solo-game evening whose neighbours are tomorrow night, still quiet between
  rounds.
- `pollLive()` adds **today's UTC date** to the ESPN query when polling a
  kickoff-less fixture — its blanked kickoff contributes no date, so a range
  built from the round's other kickoffs (all tomorrow+) skipped the very
  game that was live.
- **Comp picks are now plain text, not pills** (v2 of the morning's grouped
  chips — Josh: "I don't like the bubble sort of situation"): crest dot +
  bold team code + first names per side, faint · separator, ✓/✗ per side at
  FT. Same for the Predicted strip (`.cgrp`/`.cdot` replace `.cpick`).

Verified in jsdom against the live blanked-kickoff data: poll list includes
PEN–SYD, a simulated ESPN entry renders the live card top-of-list with score
and clock, comp strip carries zero pill elements; freeze harness 8/8 tips,
0 changed (the mid-game guard held for PEN–SYD).

**Recommendation recorded, not implemented** (needs Josh's nod): have
`parse_nrl.py` carry the previous run's kickoff/venue forward when the fresh
draw blanks them for a same-round fixture pair (like the odds `open`
carry-forward) — that would stop mid-game runs shipping kickoff-less
fixtures at all.

---

## 2026-08-13 — Grouped comp chips + double-tap zoom killed

Josh, two-part UI brief: the comp strip ("what people tipped") "doesnt look
clean" on the card, and double-tapping the tip / menu buttons on his phone
triggered iOS double-tap zoom, forcing a manual zoom-out.

**Comp strip grouped by side** (Josh chose this over polished per-person chips
or names-under-the-bar): `compStripHTML()` now renders **one chip per picked
team** — crest dot + team code (bold) + the first names on that side — instead
of one pill per member. Six members collapse to at most two chips; a ✓/✗
renders once per side when the winner is known (same `fin.winner` logic as
before, just applied per team). The home side's chip renders first, the away
side's second, matching the card's layout; any stray pick for a team not in
the fixture (shouldn't happen, but the API is external) renders after those.
`predStripHTML()` — which already grouped by side — adopts the same chip
anatomy (`.cpick.side`: bold code, `.sep` dot, bigger crest) so the Predicted
and Comp strips read as one system, dashed vs solid. Names remain first names
only (`name.split(' ')[0].slice(0,10)`), same as the predicted strip — the
display-names-only privacy rule in GOTCHAS is unaffected.

**Double-tap zoom**: `*{touch-action:manipulation}` added to the universal
reset. `manipulation` keeps panning and pinch-zoom but drops the double-tap-
to-zoom gesture, so a fast second tap on a tab, pill, fold or button no longer
zooms the page. Applied universally on purpose — a selector list would
reintroduce the zoom on any tappable surface it missed. Pinch zoom still
works, so accessibility is preserved (the viewport meta was NOT given
`user-scalable=no`/`maximum-scale=1` for exactly that reason).

**Verification**: the real `freeze_tips.mjs` harness run against the edited
page froze 7/7 upcoming tips with 0 changed — the model and every tip are
untouched. Grouped strips (pre-lock predicted, simulated locked, simulated
full-time with per-side ✓/✗) verified in jsdom against the live round's data.

Files: `nrl-tipping-guide.html`, `sw.js` (CACHE v15). No pipeline, model,
schema or workflow changes.

---

## 2026-08-10 (night) — THE OBJECTIVE CHANGED: comp-win policy hardwired into tipSide()

Josh: "I want the model to be built purely to win the tipping comp (asides
from always betting roosters)… Not a suggestion but hard wired." A
three-specialist audit (data scientist / professional gambler / behavioural
psychologist, run as independent agents) preceded the build. Consensus
findings that shaped it:

- **The target is a 4-way cluster** (Brigitte 112, Claire 112, Jake 111,
  Thorners 111 — beat the MAX), not one leader; ~41 games left, not 60.
- **oddsW=0.5 was an unfitted default** mislabelled as learned
  (`marketBrier:null` proves it). All three: weight the market heavily →
  0.75 prior, `oddsWeightLearned` flag, and `freeze_tips` now logs per-tip
  de-vigged market probs (`tiplog .mkt`) so it can be fitted for real later.
- **Splits are variance purchases**: only ever in the pf≤0.60 band, only
  when the ahead-cluster herds the favourite (matched split = EV burn),
  ranked (1−pf)·foes, capped per round by need bands, anti-tilt (schedule
  from standings only). MC: ~10× P(win) vs straight favourites at gap 14;
  honest absolute ~0.1–1% — recorded, not oversold.
- **Behavioural upgrades**: anti-loyalty flip in the rival predictor (the
  family-wide Eels/Titans/Dragons aversions; +3-5pp → ~87%), loyalty
  tie-break kept, rivals static-and-converging (weekly refit suffices).
- **Josh's own leaks the machine now removes**: ~4 pts lost to unentered
  tips (enter every game — the app tips everything), 61 coin-flip dog picks
  at 50.8%, zero perfect rounds in 23 (the +2 bonus channel).

**Build:** `cloud_fetch.py` ships `nrl_comp.js` (standings + picks + season
affinity profiles, ~23 extra public-API GETs/run, best-effort);
`tipSide()` = lock → `compPlan()` split table → blended favourite; blue 🎯
split pill + "comp split — model favours X" honesty line; panel shows
d/rounds-left/need/armed splits; predicted strips unchanged; advisory
"Comp play" notes deleted (superseded by the hardwired tip). Freeze inlines
`nrl_comp.js` → frozen tips byte-identical to browser tips (verified);
flips feed announces policy tip changes automatically. R24 at ship: SOU
(42%) and STI (49%) splits armed, everything else straight, SYD locked.

---

## 2026-08-10 (later) — Comp strategy mode: rival prediction + split picks

Josh: "you should be able to somewhat predict what they will tip… build in
that strategy layer into who I should tip to try and win the competition",
plus predicted picks visible on every card pre-lock.

**Rival model:** full comp history (rounds 1-23, ~1,015 picks) profiles each
member: accuracy, family-herd rate (71-82%), team loyalties (Claire: Sea
Eagles 20/20; Jake: Panthers 20/20; Brigitte: Roosters 20/20, Titans 1/20).
Deployable predictor = model's blended favourite unless a ≥75% (n≥8) loyalty
to the other side outranks the favourite-side loyalty. Backtest (train 1-18,
test 19-23): **84% of individual picks correct**; Brigitte 95%, Claire 90%,
Josh himself least predictable (76%). Live validation: predicted Brigitte's
whole R24 slate before the round; Josh confirmed 8/8 including the
Panthers-v-Roosters loyalty collision.

**In the app (always on — Josh: "nobody else will see this page"):** "Predicted" strip on every
pre-kick-off card (chips grouped by side with first names; real picks replace
it at lock); ≤2 gap-aware **🎯 split picks** per round when trailing (14
behind, 8 rounds left at ship time → threshold 42-46%; never the Roosters
game; cover mode when leading); strategy line in the comp panel. History is
fetched once and cached as affinity counts (~2KB localStorage).

`sw.js` CACHE v13.

---

## 2026-08-09 — Friends' footytips comp on the Tips screen

Josh: "I'd love my website to be able to show what my friends have tipped."
Investigated ESPN footytips (his comp "Family Feud", 6 members). Findings that
shaped the design: the web app is an API-backed SPA; the comp data endpoint
(`api.footytips.espn.com.au/competitions/{id}/…/rounds/{n}?view=tips`) turned
out to be **fully public** (no cookie, no token, `ACAO:*` — the initial 401s
elsewhere were AWS API Gateway's misleading unknown-route message), returning
events, every member's per-game pick, and the comp ladder. So the planned
cookie-secret pipeline scraper was scrapped for something much better: the
open page fetches the comp directly, live-scores-style. No credentials, no
expiry, no pipeline step, nothing to maintain.

**UI:** a "Comp" strip of member chips (picked team's crest dot + display
name, ✓/✗ once the game has a winner) on every locked game's card in all
three states, and a mini comp ladder under the Quick list (rank, movement,
round · total, "(you)" via `COMP_ME`). 15-min poll while visible + boot +
foreground; surgical `.compstrip`-only updates so folds survive.

**Two deliberate guardrails:** (1) the API leaks picks BEFORE kick-off (the
official UI hides them) — `compLocked()` censors pre-lock picks in this app,
in both directions of fairness; (2) the API carries full surnames — the app
renders display names only. Privacy note recorded in GOTCHAS: the comp IDs in
the public repo make the comp's first names/picks fetchable by anyone;
accepted by Josh, reversible via `COMP_ID=0`.

`sw.js` CACHE v10.

**2026-08-10 follow-up — early-picks toggle added, then REMOVED same night.**
Josh asked to see others' picks pre-lock; a per-device toggle shipped (v11)
on the belief the API exposed unstarted games' picks mid-round. Josh then
caught the flaw: that "evidence" was a Monday fetch of a finished round,
mis-remembered as a live mid-round capture. Retested properly: a round's
tips are sealed server-side until the round starts (API and logged-in UI
both clamp an unstarted round back to the last started one), so the toggle
could never show anything the locked-only view wouldn't. Removed at Josh's
direction; `compLocked()` remains the sole display gate. `sw.js` v11→v12.

---

## 2026-08-08 (evening) — Hero retired, tip-change feed, week-order quick list, ↻ chip removed

Josh's brief, four parts: the Roosters banner shouldn't pin the top ("the very top
card should always be the live game (or the next closest game). the roosters can
just go in its usual order"); the What's-new tab must announce **tip changes and
why** ("thats the most important updates of course"); the ↻ refresh chip can go
("i just pull down to refresh"); and the quick list should run "in order of the
week", not most-recent-first.

**1. The pinned `lockHero` is gone** (Josh chose full removal over folding the
verdict into the card). The Roosters card sits in normal bucket order and still
carries the gold 🔒 pill and its live/FT states; the safe/risky read lives on in
the ledger and the Model tab's walk-forward `lockTax`. The ≥1280px grid lost its
"hero" row; `renderLock()` deleted; `predict()` stays lock-free for the surfaces
that remain.

**2. Tip changes surface in What's new — with the why.** `freeze_tips.mjs` now
freezes each pre-kick-off tip WITH the tipped side's blended win % and a
plain-texted `whySummary()`; when a run's tip differs from the frozen one it
records a **flip** (`NRL_TIPLOG.flips`, ≤20 / 48h). The feed renders flips as
sev-3 `tip` entries ranked above every other category, gold ★, e.g. "Tip
changed: now Raiders (55%) — was Knights (52%). Built on Knights missing Dylan
Brown and 4 more…". Card badges go gold (`b-tip`) when a flip is the headline
change. `contentStamp()` includes flips so a refresh carrying one re-renders.
**Found and fixed while testing:** nrl.com blanks a fixture's kickoff while the
game runs, which made `freeze_tips` re-freeze an IN-PLAY game's tip (run #84 did
this to SOU–PAR, harmlessly — same side). A ko-less fresh entry now never
overwrites an existing frozen entry, and records no flip.

**3. Quick list + copyTips in week order** — kickoff asc (`weekOrder()`), TBC
last. State-independent, so live ticks can't re-sort it; the `CARD_ORDER` freeze
became dead code and was deleted. Cards keep their status buckets.

**4. The ↻ chip (`#freshBtn`) is gone.** Pull-to-refresh, boot/foreground/5-min
auto-refresh, and the live-score poll are all unchanged; `setFresh()` stays and
self-no-ops.

Also verified this session (Josh asked): **the learning loop is live and
adjusting** — tonight's two finished games appended within hours (167→169),
Elo moved winner-ward (MEL +20.4 / MAN −19.0; DOL +7.1 / BRI −4.6), and the
grid refit shifted `eloHGA` 80→60 / `homeAdv` 0.38→0.56 with the backtest
re-run over all 169 games.

---

## 2026-08-08 (later) — The top of the Tips screen is always "what matters now"

Josh's brief: "the closest upcoming game should always be at the top. Or if the
game is live it should be at the top so I don't have to scroll down", with a
designer pass first and a coder implementing the brief.

**Ordering (one comparator, one place):** three status buckets — On now (live,
kickoff asc), Up next (kickoff asc, soonest first), Played (kickoff DESC, most
recent nearest the boundary) — so the whole list reads as distance-from-now in
both directions. Unparseable kickoffs sink within their bucket; draw index
tie-breaks (decorated stable sort). Sorted once at the top of `render()` before
predict/snapTips/rank/upset so all index-paired meta inherits it. lockHero stays
pinned above everything in all states.

**Presentation:** conditional text dividers ("On now" with the pulsing livedot /
"Up next" / "Played", `.gsec` sharing the `.wkday` recipe) appear only when the
round spans ≥2 buckets — an all-upcoming Tuesday looks exactly like before.
Dividers span the desktop 2-up grid. The top upcoming card appends the existing
`kickInfo().rel` ("· in 3 hours"). Quick list + `copyTips()` rows follow the
same order via `CARD_ORDER` (frozen per full render). Rejected as clutter:
highlight rings, countdown timers, auto-scroll, per-card relative times.

**Re-sort timing (the subtle part):** live-score ticks still never reorder the
DOM (open folds). A bucket change (pre→in, in→post) sets `ORDER_DIRTY`, consumed
by a full render on foreground return — or immediately when the change lands
within 15s of the last full render, which is the boot poll answering: without
that grace window (found in real-data testing), opening the app mid-game showed
the live card stuck under "Up next" until the next background/return.

Verified: 25-scenario jsdom suite (ordering, dividers, rel suffix, fold
survival across score ticks, quicklist stability, ORDER_DIRTY set/clear),
a deferred-reorder test (late bucket change → no jump → foreground reorder),
real-data boot during the live SOU–PAR game (On now first, immediately), and
`freeze_tips.mjs` clean.

---

## 2026-08-08 — Live in-play scores on every score surface

Josh's brief: "when a game goes live I want it to display the live scores on the
card… a 'live score', not updating periodically" — i.e. opening the app mid-game
should show the current score the way it already shows a final score.

**The design constraint is the architecture.** The pipeline can't do this: GitHub
Actions cron is best-effort and 4-hourly; "live" has to be the OPEN PAGE polling a
score source directly. That requires a source that (a) has NRL scores and (b) sends
CORS headers a static page can use. Tested from the sandbox and from Josh's own
Chrome on the live site's origin:

- **nrl.com's own JSON** (`/draw/data` — same payload `cloud_fetch.py` reads) has
  live scores, `matchState` and a game clock, but **no
  `Access-Control-Allow-Origin` header** — a browser can't read it cross-origin.
- **ESPN's public scoreboard** (`site.api.espn.com/apis/site/v2/sports/rugby-league/3/scoreboard?dates=YYYYMMDD`)
  sends `Access-Control-Allow-Origin: *`, carries state (`pre`/`in`/`post`), a
  display clock and both scores, and its `displayName`s are exactly this project's
  team names. Verified working (HTTP 200, CORS passed) from the live site in a real
  browser during Storm v Sea Eagles, Round 23. **ESPN is therefore the score
  source** — the only reachable one, not merely a convenient one.

**How it works (all in `nrl-tipping-guide.html`; nothing else changed except a
`sw.js` cache bump to v7):**

- A `LIVE` map (in-page only, no localStorage) holds one entry per game:
  home/away shorts, scores, `state`, clock. `pollLive()` fetches ESPN every 45s
  while the page is visible AND a fixture is inside its live window (10 min before
  kick-off → ~3h20 after, and not already in the results memory); the rest of the
  season it's a no-op that never touches the network. Foreground return forces an
  immediate check, so opening the app mid-game shows the current score at once.
- **Display-only overlay.** `liveScore()`/`liveFinal()` feed the card, the lock
  hero, the quick list and the round-schedule rows. The results memory, the frozen
  tip log, grading (`gradedTip`/`myRecord`) and the model are untouched — an ESPN
  score can never grade a tip into the record; only the pipeline's result does that.
- **The live card mirrors the FT card** (big score, no fold): a pulsing LIVE
  badge + game clock, leader bolded, the FROZEN pre-kick-off tip in the pill
  (never a mid-game recompute — GOTCHAS 2026-08-02), and "✓ tip in front / ✗ tip
  behind / scores level".
- **An ESPN `post` bridges the FT gap**: full time shows the real final-score card
  immediately, hours before the pipeline appends the official result — which then
  wins (`fixtureResult` is checked first at every call site).
- **Score changes re-render surgically.** `renderLiveBits()` replaces only the
  live cards (foldless by design) and redraws hero/quicklist/schedule; it never
  calls `render()`, so open folds on other cards survive every score tick. The
  quick list was extracted from `render()` into `renderQuicklist()` for this.
- **Degrades to exactly the old behaviour**: offline, `file://`, jsdom
  (`freeze_tips` — guarded on `typeof fetch`), an exhausted API or a redesigned
  payload all just mean no live row, like a null odds field.

Verified: jsdom integration test (live + post + fold-survival across a score
change), `node --check` on both inline scripts, `freeze_tips.mjs` runs clean
against the new page, and the real ESPN endpoint from Josh's Chrome on the
production origin.

**Post-deploy hardening (same day):** run #81 published the in-play MEL v MAN
fixture with `kickoff:""` — nrl.com's draw meta drops a fixture's kick-off while
the game is running, which would have blinded the kickoff-based live window for
the exact game that's live. `livePollList()` now also polls kickoff-less,
result-less fixtures on game days (any same-round kickoff within ±12h) and lets
ESPN's own state decide.

---

## 2026-08-04 — Desktop UI, self-refreshing app, What's new redesign, weather removed, and a specialist audit's nine fixes

Josh's brief: a real desktop UI ("it should have a different ui for a laptop compared
to a phone"), an app that stays fresh without force-quitting ("it should just remain
open and auto update whenever I am in it"), a better What's new screen ("a lot of
spare space"), weather gone ("it isn't effecting anything"), and an independent
sports-and-gambling-specialist audit of the whole system. Built by a four-agent
chain: UI design → specialist audit → implementation → independent end-user testing
(iPhone + desktop viewports), with all tester defects fixed and re-verified.

**1. Desktop UI (≥1024px) — the phone UI is untouched at ≤640px.** The same
`.tabbar` element restyles into a centred top pill row (tab script unchanged);
`.wrap` widens to 1140px; game cards go 2-up (`align-items:start` so an open fold
doesn't stretch its neighbour); the Model screen goes 2-column; ≥1280px adds a
sticky Quick-list rail on Tips. All new CSS sits in `min-width` media blocks BEFORE
the print block, no `!important`. 641–1023px (iPad portrait) deliberately keeps the
bottom bar.

**2. The app now keeps itself fresh while open.** `refreshFromNetwork()` fires on
boot, on foreground return (`visibilitychange`/`pageshow`, ≥60s throttle), every 5
minutes while visible, from a ↻ chip in the nav (`#freshBtn`, icon-only on phones,
hidden on `file://`), and from a custom pull-to-refresh (`#ptr`, passive listeners —
`overscroll-behavior-y:none` stays). A `contentStamp()` compare means an unchanged
poll re-renders NOTHING (open folds survive); injected script tags are removed
(polling would otherwise leak five per cycle); `LINEUPS` became a `let` so
`hydrateData()` actually picks up a refreshed team list — a pre-existing bug.
`sw.js` CACHE v6.

**3. What's new redesigned.** Status line ("Checked {time} · updates roughly every
4 hours"), Today feed (semantics unchanged: today-in-Sydney, badge counts today
only), a collapsed "Earlier" fold for the rest of the 36h window (previously
dropped), crest dots + "view game →" links per fixture group (`#game-…` anchors on
cards), and a "This round's schedule" panel — every fixture in kickoff order with
ground-local times (a local `kt()` formatter; locale tz abbreviations like "GMT+10"
truncated every row — see GOTCHAS), the tipped side (gold = SYD only), FT scores,
and the bye line. A quiet day now reads as a complete screen, not dead space.

**4. Weather removed end-to-end.** Model term, card pills, venue-box chips, change
feed category, `parse_weather`/`apply_weather`/`--weather`, `fetch_weather` +
`CITY_COORDS` + `weather_dump.txt` (workflow deletes the committed dump,
idempotently). `fixture.weather` ships as an always-null key for one deploy cycle.
The ledger identity is now `ratingGap + formGap + hga − hInjPts + aInjPts === margin`.

**5. Specialist audit — nine bugs fixed** (judgement calls NOT applied; listed
below for Josh):
- A1 opening odds were destroyed every run (full-rebuild `apply_odds` set
  `open = close`); full mode now carries the first-seen open forward, so the "line
  moved" UI can actually fire and CLV data accumulates.
- A2 `logisticScale` was unidentifiable in the fit (cancels for the Elo term) and
  the grid drove it to 5, making injuries/HGA ~40% too potent — pinned at 7, out of
  the grid.
- A3 the Elo MOV multiplier used `abs(gap)`, dampening upsets instead of amplifying
  them — now winner-relative (FiveThirtyEight-style, as the docstring always claimed).
- A4 the "Roosters tax" was graded with hindsight (current Elo contains each graded
  game's own result) — now computed walk-forward in `learn_model.py`
  (`backtest.lockTax`); the front-end shows nothing if the field is absent.
- A5 the injuries scrape published phantom player "P" from a Panthers stats table —
  name-plausibility guards in `extract_injuries` + both `looks_like_player` copies.
- A6 results had no `season` field (three latent 2027-boundary corruptions:
  dropped games, scrambled Elo chronology, last year's score shown as "Full time") —
  season stamped on new entries, all readers season-aware, missing → 2026.
- A7 the change feed named a "firming" side when both prices lengthened — direction
  only when exactly one price shortened.
- A8 dead calibration code (`brierScore`/`calibrationVerdict`) deleted and the
  UI copy that promised it corrected.
- A9 grading keys are unordered team pairs (an orientation flip between runs could
  double-grade a game).
Also fixed from testing: the ledger "Net:" line / headline pairing the pre-blend
margin side with the post-blend probability when the bookies flip the tip (each
number now sits with its own team).

**Audit recommendations recorded for Josh (NOT implemented — approve to proceed):**
C1 fit home advantage as a logit intercept (home teams win 57.3% but homeAdv=0.41pts
≈ 52% baseline; biggest pure-accuracy lever). C2 persist a closing-odds history
(unlocks oddsWeight fitting, marketBrier, CLV). C3 meanwhile consider oddsW ≈ 0.65–0.7
for priced games. C4 regularise the grid fit (eloK and eloHGA both sat on grid
boundaries). C5 make stale odds visible when the API quota exhausts. C6 store the
frozen probability in `nrl_tiplog.js` (enables honest tips-as-shown Brier +
calibration). C7 candidate variables, ranked: travel/short turnarounds, season-boundary
Elo carryover with shrinkage, bye-week effect, the spread market, Origin drain.
The audit also verified sound: Elo core, de-vig parity across all three
implementations, injury arithmetic parity (Python = JS exactly), the lock's
centralisation in `tipSide()`, freeze/grading precedence, and that the results
memory reconciles exactly with the scraped ladder for all 17 teams.

Tested: independent end-user agent at 390/375/1023/1024/1280/1440px over http and
file://, all tabs, every fold, ledger arithmetic re-summed by hand, refresh
lifecycle (change → re-render; no change → no re-render), weather grep of the full
DOM, lock surfaces, localStorage persistence, print emulation; pipeline re-run
(learn → validate PASS) and `freeze_tips.mjs` against the new page (8 tips frozen,
SYD locked). Verdict: ship; three minor defects found, fixed, independently
re-confirmed.

---

## 2026-08-02 (pm) — Tips are frozen by the PIPELINE now: same record on every device

Josh, after the localStorage freeze shipped: "I want it to work on all devices and do
it automatically… not rely on the device to store it." Right call — per-device
snapshots meant your record lived on whichever phone happened to be open pre-game.

- **New `freeze_tips.mjs`** runs in the workflow after `learn_model.py`. It does NOT
  reimplement the model (a second implementation is exactly the drift risk
  `GOTCHAS.md` warns about) — it loads the real `nrl-tipping-guide.html` with the
  run's fresh data into **jsdom** and asks the page's own `predict()`/`tipSide()`
  what it is telling users, then writes `nrl_tiplog.js`
  (`window.NRL_TIPLOG = {updated, tips:[{season,round,home,away,tip,ko,ts}]}`).
  An entry is rewritten on every run until its kick-off (last pre-kick-off run wins,
  worst case ~4h before kick-off on the current schedule) and never touched after.
  Pruned to 250 entries. Best-effort: a freeze failure keeps the committed log and
  never blocks a publish.
- **The front-end loads `nrl_tiplog.js` as a fifth data file** and grades in strict
  precedence: pipeline log (identical everywhere) → this browser's own pre-kick-off
  snapshot (covers a tip shown here between runs) → the lock rule. "Your tips"
  accumulates from the log automatically — no device needs to have been open.
- `sw.js` CACHE v5, log precached; `refreshFromNetwork()` + `hydrateData()` re-pull
  and re-read the log on each launch; workflow gains the freeze step (`npm install
  jsdom`, non-fatal).
- `nrl_tiplog.js` joins the never-hand-edit / never-upload generated-files list.

Tested: freeze run against live data froze the real CRO + PAR tips for today's two
games; a scenario with a deliberately wrong server tip AND a conflicting local
snapshot graded from the SERVER log (✗) as required; smoke 60/60; zero console errors.

---

## 2026-08-02 — The full-time card graded a hindsight tip; the stats wore the wrong labels

Josh, Sunday morning: the Broncos v Knights card claimed "✓ tipped Knights" when the
app's pre-game blend had said *Broncos* (who lost); and the Model tab's "64% correct
(season)" + "14-5 Roosters record" made no sense in his first week of tipping.

**1. Tips are now frozen at kick-off and graded only against the frozen pick
(`nrl-tipping-guide.html`).** The final card used to call `tipSide()` at render time —
after `learn_model` had folded the game's own result into the Elo and the market price
had vanished — so a tip that flipped post-game graded itself ✓ with hindsight. Now
`snapTips()` writes the displayed tip for every not-yet-started game into
`nrl_snap_v1` (localStorage) on each render, and full-time grading reads ONLY that
snapshot. The Roosters lock needs no snapshot (the rule is the tip). No snapshot and
no lock → the card says "final — no pre-game tip on record" — including, honestly,
for BRI v NEW itself, which predates the feature and whose real pre-game tip the app
has no record of.

**2. The Model tab now says what each number is.** "Your tips (graded)" — frozen picks
plus lock games, graded against the results memory; starts from when the app is
actually used, never back-filled. "Model backtest (whole season)" — the walk-forward
would-have-tipped rate over all 156 results (the old, mislabelled 64%). "Roosters
season W-L (the team)" — the club's record (the old 14-5). The loyalty tax is
reworded as backtest ("would have cost"). Full post-mortem in `GOTCHAS.md`.

Tested: scenario harness froze a deliberate wrong tip for a finished game — card
graded ✗ against the snapshot while the post-game recompute would have claimed ✓;
lock game ✓ by rule; unsnapshotted finals claim nothing; smoke 60/60; zero console
errors.

---

## 2026-07-31 — Finished games show the score; the feed is today-only; the bar tells two teams apart

Morning-after fixes from Josh (Roosters 82–12 over the Cowboys overnight — the lock's
finest hour). All in `nrl-tipping-guide.html`; no pipeline changes.

- **A played game is a result, not a tip.** New `fixtureResult(p)` reads the append-only
  results memory for the round being tipped; when a fixture has a score the card renders
  a FULL TIME state — big score, "<Winner> won" pill (gold + 🐓 when it's the Roosters),
  and "✓ tipped X — got it" / "✗ tipped X" — with the odds/injury detail dropped as
  stale. The lock hero flips to "Full time: Roosters beat …" with the score, and the
  quick list swaps the percentage for the result + ✓/✗. Draws wash.
- **What's new shows TODAY only** (Sydney). The card said "56 updates since yesterday
  2:55 am" — technically the 36h window doing its job, practically clutter. The data
  file still carries the rolling window (nothing is lost), but the feed, badge and
  header now cover entries first seen today: "7 updates today · since 3:11 am AEST".
  Accepted trade-off, per Josh: a late-night drop won't be on screen after midnight.
- **The probability bar is a two-colour split, not all red.** Each team's share is
  painted in its own club colour with a white seam at the split, a 50% tick, and
  colour-key dots beside the percentages. Same-colour matchups (Dragons v Dolphins —
  both red) shade-shift the away side darker; near-navy clubs (Bulldogs) get a
  brightness lift so their share can't sink into the background.
- **Crests are monogram roundels** — the club colour dot now carries the team code
  (white, shadowed) so you know who's who without relying on colour alone. Real club
  logos were considered and skipped deliberately: they're trademarked artwork and the
  app is on a public repo.

Tested: smoke 60/60, injury logic 9/9, `node --check` clean, headless render against
live data (final card 12–82 with ✓, 7 duo bars incl. clash + lift cases, feed 56→7).

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
