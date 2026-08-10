# Front-end — `nrl-tipping-guide.html`

The entire app is this one file: HTML structure + CSS + all model/UI JavaScript, no
external dependencies. It's designed to work opened as a local file and as a hosted
page, on desktop and iPhone. This doc maps its structure so you can find things fast.
For the tip math see `MODEL.md`.

---

## How it loads data

Near the top:
```html
<script src="nrl_data.js"></script>     <!-- window.NRL_DATA -->
<script src="nrl_learned.js"></script>  <!-- window.NRL_LEARNED -->
<script src="nrl_players.js"></script>  <!-- window.NRL_PLAYERS -->
```
Then in the main script:
- `SRC` = `NRL_DATA` if valid, else a baked-in `SEED` (so the page never renders blank).
- `LEARNED` = `NRL_LEARNED` if valid, else `null`.
- `learnedActive` = `LEARNED && lowConfidence !== true` (gates Elo/learned params).
- `PLAYERS` = `NRL_PLAYERS || {}`; `HAVE_PLAYERS` = it has > 50 entries.

If a data file is missing/broken the app degrades: seed data + a visible "showing
sample data" banner; no learned params; flat injury fallback.

---

## Local state & caching

- User edits (logged results, tweaked stats) are stored in `localStorage` under a key
  scoped to season+round+updated **plus a content signature**:
  `nrl_v3_<season>_<round>_<updated>_<sig>`. The `<sig>` (`dataSig()`) is a cheap hash of
  the teams/fixtures, so when the feed is regenerated under the *same* `updated` date (the
  job runs every 4 hours) any real data change produces a fresh key and the new official data
  takes over — without it, an earlier same-day snapshot would shadow the fresh data (this
  caused stale form dots). Old `nrl_v3_` keys are pruned on save.
- Accuracy history: key `nrl_acc_v3`. Comp-format setting: `nrl_compformat_v1`.
- **Do not** introduce `sessionStorage` or external storage; `localStorage` only.

### Staying fresh (rebuilt 2026-08-04 — the app now auto-updates while open)
The data files load via `<script src>` for instant paint and offline use.
`refreshFromNetwork()` re-pulls all five data files with a `?v=<ts>` cache-buster and
rehydrates (`hydrateData()` recomputes `SRC`/`LEARNED`/`PLAYERS`/`LINEUPS`/`TIPLOG`/`KEY`).
It now fires from FOUR triggers, not just boot:

1. **Boot** (as before).
2. **Foreground return** — `visibilitychange` → visible, and `pageshow` with
   `e.persisted` (bfcache), throttled to ≥60s since the last check. This is what fixes
   "I have to quit and re-open the home-screen app".
3. **Periodic** — every 5 minutes while the page is visible.
4. **Manual** — the `#freshBtn` refresh chip in the top nav (icon-only ≤640px, hidden
   entirely on `file://`), plus a custom pull-to-refresh on touch devices (`#ptr`
   indicator; passive listeners only; never attaches on `file://`).

Landmines baked into the implementation — keep them:
- `contentStamp()` (KEY + gamesLearned + tiplog length + lineups round) is compared
  before/after hydration; **nothing re-renders when the data didn't change**, so open
  `<details>` folds survive polling. Don't "simplify" this to always render.
- Each injected `<script>` tag is **removed in its onload/onerror handler** — without
  that, 5-minute polling leaks five tags per cycle forever.
- The `file://` short-circuit stays the first line of `refreshFromNetwork()`.
- `overscroll-behavior-y:none` on body is intentional (iOS PWA); the pull-to-refresh
  is custom for exactly that reason.

`sw.js` — a **network-first** service worker, registered only over http(s) — additionally
keeps the *shell* current and provides the offline cache (CACHE `nrl-tips-v6`; it
normalises the `?v=` query out of cache keys so polling can't bloat the cache). Both
are no-ops on `file://`. Bump `CACHE` to force-invalidate every cached copy.

### Live scores (2026-08-08 — the page polls ESPN while a game is on)

Full-time scores come from the pipeline's results memory, but IN-PLAY scores can't:
the cron is 4-hourly and best-effort. So the open page polls **ESPN's public NRL
scoreboard** (`site.api.espn.com/…/rugby-league/3/scoreboard?dates=YYYYMMDD`) — the
only NRL score source that sends `Access-Control-Allow-Origin: *` (nrl.com's own
JSON does not, so a static page cannot read it). Search `pollLive` in the file.

- `LIVE` (in-page map, never persisted) → `liveScore(p)` (state `in`) and
  `liveFinal(p)` (state `post`) — both oriented to the prediction's home side.
- Polled every 45s (`LIVE_MS`) while the page is visible AND `livePollList()` is
  non-empty (a fixture 10 min before kick-off → ~3h20 after, with no pipeline
  result yet). Any other time it's a no-op — zero network for most of the week.
  Foreground return forces an immediate check (`pollLive(true)`).
- **Display-only overlay**: the card, lock hero, quick list and schedule rows read
  it; the results memory, tip log, grading and model never do. `fixtureResult()`
  is checked FIRST at every call site, so the pipeline's official result always
  beats a lingering ESPN entry, and an ESPN `post` merely bridges the hours until
  the pipeline appends the real one.
- **`renderLiveBits()` — not `render()` — handles score ticks.** It replaces only
  the live cards (which are foldless like the FT card, so in-place replacement is
  safe) and redraws `lockHero` / `quicklist` / `weekAhead`. Calling `render()`
  here would collapse open folds every 45s — the exact bug `contentStamp()`
  exists to prevent. The quick list lives in `renderQuicklist(preds)` so this
  partial path and `render()` share one implementation.
- Guarded on `typeof fetch` (jsdom in `freeze_tips.mjs` has none) and wrapped in a
  swallow-everything catch: offline / 403 / redesigned payload = no live row.
- CSS: `.gwhen.live`, `.livedot` (pulse, disabled under `prefers-reduced-motion`),
  `.qline.live`, `.wkrow.live .k` — one hot colour, `#ff5d73`.

### Friends' comp tips (2026-08-09 — footytips, fetched by the open page)

Josh's ESPN footytips comp ("Family Feud") renders on the Tips screen: a
**Comp strip** of member chips (crest dot of the picked team + display name,
✓/✗ once the winner is known) on every LOCKED game's card, and a **mini comp
ladder** (`#compPanel`, under the Quick list / in the ≥1280px rail). Search
`pollComp` in the file. Key facts:

- The comp endpoint (`api.footytips.espn.com.au/competitions/{id}/…/ladders/{id}/rounds/{n}?view=tips`)
  is **public** — no cookie/token, `ACAO:*` — so the page fetches it directly
  (15-min poll while visible + boot + foreground). No pipeline step exists.
- **Pre-lock censorship is enforced HERE**: the API leaks picks before
  kick-off; `compLocked()` (our own feed's kickoff, or live/result evidence
  for a kickoff-less fixture) gates every strip. Never show pre-lock picks.
- `renderCompBits()` is surgical: it replaces only each card's `.compstrip`
  node (a locked pre-game card can have an open fold) + `renderCompPanel()`.
  Full renders embed the strip via `compStripHTML(p)` in all three card states.
- Config: `COMP_ID` / `COMP_LADDER` / `COMP_ME` constants (`COMP_ID=0`
  disables the feature; `COMP_ME` marks "(you)" because the anonymous API
  never sets `currentUser`). Display names only — never surnames.
- Strips are strictly locked-only (`compLocked()`): footytips seals a
  round's tips server-side until the round starts, so there is nothing to
  show earlier anyway (a short-lived "early picks" toggle was removed
  2026-08-10 — see GOTCHAS).

### Comp strategy mode (2026-08-10 — always on)

ALWAYS ON (Josh, 2026-08-10: "nobody else will see this page. it doesnt
need a toggle" — re-gate via `getStrat()` if that ever changes). Active: `fetchCompHistory()` pulls every completed round once and
caches per-member (team → [picked, seen]) affinity counts in localStorage
(`nrl_compstrat_hist_v1`, counts only, ~2KB); `predictPick()` predicts each
rival's pick (model's blended favourite, overridden by a ≥75%/n≥8 loyalty to
the other side — strongest loyalty wins when two collide; backtested 84%
overall, leaders 90-95%); every pre-kick-off card gets a **Predicted** strip
(grouped one chip per side, first names; the REAL picks strip replaces it at
lock); `computeStrategy()` marks ≤2 **🎯 split picks** when trailing (never
the Roosters game, threshold widens with the gap: 46%→42%) plus a gap/rounds
line in `#compPanel`; leading flips to cover mode (no splits). All updates go
through `renderStratBits()` — surgical `.stratnote`/`.compstrip.pred` node
swaps, fold-safe, never `render()`.

### Card ordering on Tips (2026-08-08 — what matters now is at the top)

Cards render in three status buckets — **On now** (live), **Up next** (kickoff
asc), **Played** (kickoff desc, most recent first) — sorted ONCE at the top of
`render()` on `fxList` BEFORE `predict`/`snapTips`/rank/upset, so every
index-paired array inherits the order with no remapping. Unparseable kickoffs
sink within their bucket in draw order; the draw index is the explicit
tie-break. Text dividers (`.gsec`, shares the `.wkday` recipe; "On now" carries
a `.livedot`) render only when ≥2 buckets are non-empty, and span the 2-up grid
at ≥1024px (`grid-column:1/-1`). The first Up-next card appends
`kickInfo(fx).rel` ("· in 3 hours") to its `.gwhen`. The quick list and `copyTips()` run in WEEK order (kickoff asc,
`weekOrder()`) since 2026-08-08 (later) — state-independent, so no tick can
re-sort them, and no order-freeze is needed.

**Re-sort timing:** `renderLiveBits()` never reorders (folds!). A poll that
changes a fixture's bucket sets `ORDER_DIRTY`; the reorder lands on foreground
return, or IMMEDIATELY if the change arrives within 15s of the last full render
(`LAST_FULL_RENDER` grace window — that's the boot/foreground poll answering,
i.e. the user just opened the app mid-game and nothing is mid-read).

---

## Key JavaScript functions (search these names in the file)

| Function | Role |
|----------|------|
| `avg`, `overallMargin`, `splitWeight`, `effRating`, `formNudge` | Heuristic team rating (see MODEL.md §1). |
| `eloStrength`, `eloGapToPoints`, `logistic` | Elo path + points↔probability. |
| `normName`, `playerImpact`, `injuryPenalty`, `namedSquad` | Position×rating injury weighting (uses `PLAYERS` + `LINEUPS`). The round's team list both cancels a named player's injury entry AND upgrades an unnamed doubt to a full-weight NOT NAMED absence (2026-07-30). `LINEUPS` is a `let` and re-read by `hydrateData()` (2026-08-04) so a refreshed team list takes effect without a full reload. |
| `resolveOdds`, `marketProb` | Odds `{open,close}` handling + de-vig to a home prob. |
| `predict(fx)` | Assembles margin → `modelP` → blends odds → returns the per-game prediction object. |
| `rationale`, `bandFor`, `whySummary`, `whyHTML` | The plain-English "why this tip" lead, the 1–2 sentence driver summary (2026-07-30), and the itemised ledger folded behind "Show the working" (lock line stays outside the fold). (`injurySentence` was deleted in 2026-07: the ledger replaced it, and it was the file's last unescaped interpolation of scraped player names.) |
| `modelFav(p)` / `tipSide(p)` | **Keep these apart.** `modelFav` = the side the numbers like (reporting only). `tipSide` = the side actually tipped, and it returns the Roosters in their own game. Anything that names a tip must call `tipSide`. |
| `render` | Master render: fills every section by element ID. |
| `pollLive`, `liveScore`, `liveFinal`, `renderLiveBits`, `renderQuicklist`, `weekOrder` | Live in-play scores (2026-08-08): ESPN poll → `LIVE` map → surgical redraw of the score surfaces only. `weekOrder` = the kickoff-asc order shared by the quick list + `copyTips` (2026-08-08 later). See "Live scores" above. |
| `copyTips`, `flash` | "Copy tips" button. |
| `resetState`, `loadState`, `saveState`, `resetAll` | Local state lifecycle. |

`predict()` returns (roughly): `{h, a, margin, modelP, mkt, pHome, blended, hInj, aInj,
wx, useElo, parts}`. The Roosters lock is applied at pick time, in **one** place —
`tipSide()` — which every tip-naming surface calls (quicklist, `cardHTML`, `copyTips`,
the ledger's for/against colouring). `predict()` itself stays honest: it returns the
model's own probability, so `lockHero`, the odds box and the ledger lead can still say
when the model disagrees with the lock.

---

## App structure (2026-07-30 rebuild; responsive tiers added 2026-08-04)

The page is a four-screen app: `#scr-tips`, `#scr-new`, `#scr-ladder`, `#scr-model` —
plain `.screen` wrappers toggled by a small standalone `<script>` at the end of the
body (`nrl_tab_v1` in localStorage remembers the tab; `a.chgbadge` clicks switch to
What's new before the `#chg-…` anchor scrolls; `a.gamelink` clicks switch to Tips
before the `#game-…` anchor scrolls; `#tabNewBadge` is fed by `renderChanges()`).
Hidden screens still receive their innerHTML — `render()` is unaware tabs exist.
Keep it that way: new surfaces go INSIDE a screen, and the render pipeline must
never depend on which screen is visible.

### Responsive tiers (2026-08-04 — phone and desktop get different UIs)

| Width | Behaviour |
|---|---|
| ≤ 640px | Phone UI, unchanged: single 600px column, fixed bottom tab bar. |
| 641–1023px | Same, with the pre-existing enrichment (`.moregrid`/`.statgrid` 2-col). iPad portrait keeps the bottom bar deliberately — don't lower the desktop breakpoint. |
| ≥ 1024px | Desktop: the SAME `.tabbar` element is restyled into a centred top pill row (the tab script needs no changes); `.wrap` widens to 1140px; game cards 2-up (`align-items:start` so an open fold doesn't stretch its neighbour); Model screen 2-column; What's new gets a feed+schedule grid. |
| ≥ 1280px | Tips screen adds a sticky right rail holding the Quick list. |

All desktop rules live in `@media(min-width:1024px)`/`(min-width:1280px)` blocks
placed BEFORE the `@media print` block, with no `!important` (print's
`.screen{display:block!important}` must keep winning). The `#scr-*.active` grid
displays override `.screen.active{display:block}` by ID specificity.

### Tip changes in the feed (2026-08-08)

`freeze_tips.mjs` records a **flip** whenever a run's pre-kick-off tip differs
from the frozen one (`NRL_TIPLOG.flips`, hydrated into `FLIPS`). `chgList()`
appends them as category `tip`, sev 3 — `CHG_ORDER` ranks `tip` first, the ★ row
and the card badge use the gold lock colour (`c-tip`/`b-tip`) — with text like
"Tip changed: now Raiders (55%) — was Knights (52%). Built on …" (the `why` is
the flip-time `whySummary()`, plain-texted). `contentStamp()` includes
`FLIPS.length` + last flip ts so a refresh carrying a new flip re-renders.

### What's new screen (redesigned 2026-08-04)

`#scr-new` now holds: a `#newMeta` status line ("Checked {time} · updates roughly
every 4 hours"), the Today feed panel (`#changeFeed`, badge/count semantics
unchanged — today-in-Sydney only, entries with no `ts` count as today), a collapsed
**Earlier** fold for the rest of the rolling 36h window (`chg-early-` id prefix;
overflow "show more" groups use `chg-more-` — three distinct anchor namespaces with
the cards' `#game-…`), and a **"This round's schedule"** panel (`#weekAhead`):
every fixture in kickoff order under day headers, crest dots, ground-local
time-only kickoff via the local `kt()` formatter (NEVER a locale tz abbreviation —
"GMT+10" truncated every row; the venue box still carries the fully-zoned time),
the tipped side as a pill (gold = SYD only), FT scores once played, and the bye
line. `renderNewScreen(preds,fxList)` is called from `render()` unconditionally.
Fixture group headers in the feed carry crest dots + a "view game →" link.
`renderChanges()` toggles `.long` on `#changeFeed` when >6 visible today-rows;
the desktop 2-column feed flow is scoped to `#changeFeed.long`.
Legacy `cat:"weather"` entries are filtered out in `chgList()` (transition window). `cardHTML()` builds the 2026 card: `gtop` (kick-off/venue),
`gmatch`/`gteam` (monogram crests carry the team code), `gprob`/`gbar.duo` (two
club-colour shares, `.alt` = shade-shift for same-colour matchups, `.lift` =
brightness floor for near-navy clubs), `gtippill`, then the `details.more` fold.
A fixture with a score in the results memory (`fixtureResult()`) renders the
FULL TIME state instead — score, winner pill, tip verdict — and the hero and
quick list follow suit. The verdict grades the PRE-KICK-OFF tip — never a recomputed one — in strict
precedence: the pipeline's `nrl_tiplog.js` (server-frozen, identical on every
device), then this browser's `nrl_snap_v1` snapshot, then the lock rule. See the
2026-08-02 entries in `GOTCHAS.md` before touching this. The change feed displays TODAY (Sydney) only; the data
file still carries the rolling 36h window.

## Element IDs the render targets

`render()` writes into these IDs — keep them intact if you restyle:

```
roundPill, metaline, dataBanners, games, quicklist, copied,
accYou, accModel, accLock, accNote, rkTax, learningSection, learningBody,
ladderNote, ladder, hga, formW, oddsW, compMode, howItWorks, foot,
changesSection, changeFeed, chgCount, tabNewBadge,
newMeta, weekAhead, ptr, compPanel
```

*(Removed 2026-08-08 later: `lockHero` — the pinned Roosters banner is gone, the
Roosters card sits in normal bucket order; `freshBtn`/`freshLabel` — the ↻ chip is
gone, pull-to-refresh + the auto-refresh triggers remain and `setFresh()` self-
no-ops on the missing element.)*

- `games` / `quicklist` — the per-game cards and the compact tip list. The quick
  list runs in WEEK order (kickoff asc via `weekOrder()`, TBC last), NOT the
  cards' bucket order — it reads as the round's fixture list, and no live tick
  can re-sort it.
- `hga`, `formW`, `oddsW` — Advanced-settings inputs (home-ground bonus, form weight,
  odds weight). When `learnedActive`, `hga`/`oddsW` default to the learned values via
  `applyLearnedFieldDefaults()`.
- `compMode` — comp-format selector (win / margin / confidence).
- `learningSection` / `learningBody` — the "what it's learned" panel (Elo ladder,
  params, backtest, low-confidence badge).
- `rkTax` — the "Roosters tax" figure.

---

## Styling / UX notes

- Visual style is a dark "Apple Sports"-inspired theme, optimised for iPhone (safe-area
  insets, PWA `<meta>` tags so it can be added to the home screen).
- No CDNs, no web fonts that require network — everything inline so offline works.
- The "why" line under each tip surfaces the injury adjustments, e.g.
  `SYD −4.3: Nathan Cleary out (Halfback)`. (Weather removed 2026-08-04.)
- When the model's margin side and the blended favourite differ, the ledger "Net:"
  line and the headline sentence pair each number with its own team — never quote
  one side's margin next to the other side's blended percentage.

---

## When you change the front-end
1. Preserve the element IDs above and the Roosters lock.
2. Keep it single-file and dependency-free.
3. After editing, remember `index.html` must be regenerated (run the workflow) for the
   change to reach the live site — see `DEPLOY_AND_OPS.md`.
4. If you add a new data field, update the fallback/`validData` checks so a missing
   field degrades gracefully.
