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

### Staying fresh on the home screen (added 2026-07-28)
The data files load via `<script src>` for instant paint and offline use, but on each
online launch `refreshFromNetwork()` re-pulls them with a `?v=<ts>` cache-buster and
re-renders (through `hydrateData()`, which recomputes `SRC`/`LEARNED`/`PLAYERS`/`KEY`).
`sw.js` — a **network-first** service worker, registered only over http(s) — additionally
keeps the *shell* current and provides the offline cache. Both are no-ops on `file://`.
Bump `CACHE` in `sw.js` to force-invalidate every cached copy.

---

## Key JavaScript functions (search these names in the file)

| Function | Role |
|----------|------|
| `avg`, `overallMargin`, `splitWeight`, `effRating`, `formNudge` | Heuristic team rating (see MODEL.md §1). |
| `eloStrength`, `eloGapToPoints`, `logistic` | Elo path + points↔probability. |
| `normName`, `playerImpact`, `injuryPenalty`, `namedSquad` | Position×rating injury weighting (uses `PLAYERS` + `LINEUPS`). The round's team list both cancels a named player's injury entry AND upgrades an unnamed doubt to a full-weight NOT NAMED absence (2026-07-30). |
| `weatherEffect` | Rain → margin-shrink factor. |
| `resolveOdds`, `marketProb` | Odds `{open,close}` handling + de-vig to a home prob. |
| `predict(fx)` | Assembles margin → `modelP` → blends odds → returns the per-game prediction object. |
| `rationale`, `bandFor`, `whyHTML` | The plain-English "why this tip" lead + the itemised ledger. (`injurySentence` was deleted in 2026-07: the ledger replaced it, and it was the file's last unescaped interpolation of scraped player names.) |
| `modelFav(p)` / `tipSide(p)` | **Keep these apart.** `modelFav` = the side the numbers like (reporting only). `tipSide` = the side actually tipped, and it returns the Roosters in their own game. Anything that names a tip must call `tipSide`. |
| `render` | Master render: fills every section by element ID. |
| `copyTips`, `flash` | "Copy tips" button. |
| `resetState`, `loadState`, `saveState`, `resetAll` | Local state lifecycle. |

`predict()` returns (roughly): `{h, a, margin, modelP, mkt, pHome, blended, hInj, aInj,
wx, useElo, parts}`. The Roosters lock is applied at pick time, in **one** place —
`tipSide()` — which every tip-naming surface calls (quicklist, `cardHTML`, `copyTips`,
the ledger's for/against colouring). `predict()` itself stays honest: it returns the
model's own probability, so `lockHero`, the odds box and the ledger lead can still say
when the model disagrees with the lock.

---

## Element IDs the render targets

`render()` writes into these IDs — keep them intact if you restyle:

```
roundPill, metaline, dataBanners, lockHero, games, quicklist, copied,
accModel, accLock, accNote, rkTax, learningSection, learningBody,
ladderNote, ladder, hga, formW, oddsW, compMode, howItWorks, foot
```

- `lockHero` — the Roosters lock banner (safe/risky verdict).
- `games` / `quicklist` — the per-game cards and the compact tip list.
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
- The "why" line under each tip surfaces the injury and weather adjustments, e.g.
  `SYD −4.3: Nathan Cleary out (Halfback) · wet — model less certain`.

---

## When you change the front-end
1. Preserve the element IDs above and the Roosters lock.
2. Keep it single-file and dependency-free.
3. After editing, remember `index.html` must be regenerated (run the workflow) for the
   change to reach the live site — see `DEPLOY_AND_OPS.md`.
4. If you add a new data field, update the fallback/`validData` checks so a missing
   field degrades gracefully.
