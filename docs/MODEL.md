# The Model — how a tip is calculated

> **Read §5 first if you are here about the tip itself.** Since 2026-09-12 the model
> produces a *probability*, and a separate solver turns probabilities into *tips*.
> Everything between §1 and §4 is the probability. §5 is the decision.

## THE OBJECTIVE IS P(BRIGITTE FINISHES 1st) — AND NO TEAM IS LOCKED (2026-09-12)

The app belongs to **Brigitte** now (Josh's wife; footytips display name `Brigitte`),
and it has exactly one objective:

```
U = P(Brigitte finishes 1st in the footytips comp)
```

Nothing else. No top-3 term, no top-4 term, no loyalty pick, no accuracy target. In
code: `util = w.first/SIM_N`. `top3`/`top4` are still *counted* because the panel reads
better with context, but they never enter the utility. Josh ("Special unit", 10 points
back at the handover) is modelled as a rival like any other.

**The Roosters lock is gone** — see §5, which used to be the section documenting it.
`LOCK_MODE = "off"`. Its only other setting, `"tiebreak"`, prefers the Roosters when and
only when the objective genuinely cannot separate the two options (exact equality of
P(1st) in the finals solver; `|pHome−0.5| < 0.005` in the fallback). Verified on the R28
data: flipping it to `"tiebreak"` returns **byte-identical tips** and the same P(1st) to
six decimals. It is free, and it must stay free.

Why this is not a matter of taste: at Finals Week 1 2026, with Brigitte 2nd on 131 and
three games left in the round, tipping the Roosters in the Sunday qualifying final was
worth **−6.5 points of comp-win chance** — a bigger swing than any other decision on the
board, and one the old app was structurally incapable of making.

**In the finals (rounds 28–31) the split policy is not simulated at all — it is solved
exactly.** `finalsPlan()` enumerates the whole remaining bracket and does backward
induction over it: no PRNG, no sampling error, no EPS. `simComp()` below survives as the
regular-season path and as the fallback if the bracket cannot be resolved. Full detail
in §5; the plain-English version is in `docs/STRATEGY.md`.


## (superseded 2026-09-12) THE SPLITS ARE NOW PRICED BY SIMULATION (2026-08-13, extended 2026-08-15)

> **SUPERSEDED in part.** The objective described below (`U = P(top 4) + P(top 3) +
> P(1st)`) was replaced by pure P(1st) on 2026-09-12, and "never the Roosters game" is
> gone with the lock. `simComp()` itself is still the regular-season engine and still
> works as described; in the finals it is the fallback. `SIM_N` is 8,000 now, not 3,000,
> and `EPS = max(0.003, 2·sqrt(0.25/SIM_N))` — under a pure-P(1st) utility the old fixed
> 0.003 was about a third of the Monte-Carlo standard error, so the tie-breaks fired on
> noise every run.


The split-selection layer of the 2026-08-10 policy below was replaced by an
in-page Monte-Carlo season simulator, `simComp()`. **Objective (2026-08-15):
U = P(top 4) + P(top 3) + P(1st)** — Josh's goal is top 4 "at least", ideally
the podium; equal-weighting the tiers makes 1st worth 3, top 3 worth 2, top 4
worth 1. The simulator prices the **+2 perfect-round bonus for every round
including the current one** (while it's still live — a finished round's bonus
is already banked), so a current-round split is charged for the perfect round
it forfeits. The panel compares the strategy against **tipping favourites all
season** (the honest play-safe floor), not a same-round straight tip — a
single round's split is ~EV-neutral; the edge comes from the sustained policy. Every
candidate split set for the current round is scored over 3,000 simulated
rest-of-seasons: real games for the current round (blended probs, rivals'
actual-then-predicted picks), generic games for future rounds (per-rival herd
rates fitted to season accuracy, shared outcomes for herd correlation, +2
perfect-round bonus, margin-countback tie-breaks), and future-me playing this
same machine policy. Deterministic by construction: seeded PRNG keyed on
(season, round) with per-game draw streams — browser and jsdom freeze derive
identical tips. Selection breaks near-ties (EPS=0.003) toward frozen
incumbent splits, then the top-2 (1−pf)·foes candidates (policy consistency),
then fewer splits. The need bands below survive only as the θ candidate
filter (floored at 0.65) and as the fallback if the simulator throws. The
audit's hard guards all stand: never the Roosters game, matched-split
exclusion, need<0.5 → no splits, anti-tilt inputs. The comp panel surfaces
the simulator's honest P(1st)/P(top 3), the margin-game median advice, and
the adherence tally. Full detail in `docs/CHANGELOG.md` 2026-08-13 (night).


## (superseded in part 2026-09-12) THE OBJECTIVE CHANGED (2026-08-10): win the comp, not maximise accuracy

> **SUPERSEDED in part.** Step 1 below ("Roosters lock first, always") no longer exists.
> The need bands in step 3 are now only a *candidate filter* (θ floored at 0.65) and the
> fallback path; in the finals the split set comes from the exact solver in §5. Step 2's
> "deficit to the MAX of the rivals at-or-above Josh" is now countback-aware and measured
> against Brigitte (`cbBeats()` — a rival level on points with a *lower* cumulative
> margin error is ahead of her). Everything else — the `predict()`/`tipSide()` seam,
> oddsW 0.75, `oddsWeightLearned`, the per-tip `.mkt` logging, the anti-tilt rule —
> stands unchanged.

A three-specialist audit (data scientist, professional bettor, behavioural
psychologist — full findings in `docs/CHANGELOG.md`) rebuilt the DECISION layer.
`predict()` stays an honest probability estimator; `tipSide()` is now a
comp-optimal decision policy:

1. **Roosters lock first, always** (unchanged, non-negotiable).
2. **State**: d = deficit to the MAX of the rivals at-or-above Josh (a 4-way
   cluster, not one leader); need = d / rounds-left; T = games left (schedule
   table `COMP_GAMES_PER_ROUND`, finals rounds shrink). Standings come from
   `nrl_comp.js` (pipeline) refreshed live by the browser poll.
3. **Split rule**: tip the underdog only when (a) the favourite's blended prob
   ≤ θ(need), (b) near-unanimity of the ahead-cluster sits on the favourite
   (actual picks once visible, else the behavioural predictor — a matched
   split moves no ranks), (c) the game hasn't kicked off, (d) the round's
   split cap isn't spent. Bands: need<0.5 → 0 splits; <1 → 1 @ θ=.55; <2 →
   2 @ .58; <3 → 4 @ .62; else nuclear (.75, or 1.0 when d>0.6·T).
   Candidates rank by (1−pf)·foes — cheapest variance, most rank leverage,
   least damage to the +2 perfect-round bonus.
4. **Leading → cover mode**: straight favourites, no splits.
5. **Anti-tilt**: the schedule is a function of (standings, games left) ONLY.
6. **oddsW**: now defaults 0.75 (market-heavy). The old 0.5 was an UNFITTED
   default mislabelled as learned; `learn_model` emits `oddsWeightLearned`
   and `freeze_tips` logs per-tip market probs (`tiplog .mkt`) as the corpus
   that will eventually let oddsW be fitted for real.
Monte-Carlo validation (audit): ~10× P(win) vs pure favourite-tipping at the
current gap — but the honest absolute number is ~0.1–1%. The machine is the
best play, not a promise.


This is the heart of the project: exactly how the app turns data into a predicted
winner and a confidence for each game. All of this runs **in the browser** inside
`nrl-tipping-guide.html`; the learning loop (`learn_model.py`) mirrors the same math
server-side so its backtest numbers mean what the app will actually show.

Everything works in **points of margin** (predicted home margin), which is then
squashed into a win probability. Injuries, home-ground edge and the Elo/
form ratings all contribute in the same points space so they compose cleanly.

> **Weather was removed entirely on 2026-08-04.** It never picked a side, only shrank
> confidence, and in practice it wasn't affecting tips. There is no weather term
> anywhere in the model now; `fixture.weather` ships as an always-null key for one
> deploy cycle (CDN-cached old pages still read it) and then the key can be dropped.

---

## 1. The two rating engines

The app has two ways to rate teams and uses whichever is trustworthy:

### (a) Heuristic rating — always available
Per team, per venue side (`home` or `away`):

```
overallMargin(t) = (PF - PA) / max(1, P)          // season avg points margin
split            = (splitPF - splitPA) / splitP    // that team's home OR away split
splitWeight(n)   = min(0.5, n / (n + 6))           // trust the split more as its sample grows, capped at 0.5
effRating(t,side)= w*split + (1-w)*overallMargin   // shrink split toward overall
                   + formNudge(t)                   // recent-form nudge
formNudge(t)     = clamp(±2, (last5 - 2.5) * formW) // formW default 0.4; last5 = wins in last 5
```

So a team's effective rating is its season margin, pulled toward its home/away split
(more so when that split has more games), plus a small bump/penalty for hot/cold form.

> **Data source (added 2026-07-28):** `last5` (wins in the last 5) and the home/away
> split records are derived by `parse_nrl.py` from the append-only results memory — the
> scraped ladder doesn't carry a form column or split tables. Early in the season they're
> partial (few logged games) and sharpen over time; `splitWeight` keeps a thin split
> sample from dominating the overall margin.

### (b) Elo rating — used only once the learning loop is confident
`learn_model.py` replays an Elo rating for every team from the full result history and
stores it in `nrl_learned.js` (`elo: {short: rating}`). The front-end converts an Elo
gap into an equivalent points margin so it flows through the same pipeline:

```
ELO_PROB_BASE = 400
eloGapToPoints(diff, scale) = diff * scale * ln(10) / 400
```

**Which engine is used** is decided by `learnedActive = LEARNED && lowConfidence !== true`.
Under ~30 logged games the learning loop sets `lowConfidence = true`, the front-end
ignores the learned Elo/params, and it uses the heuristic ratings + hand-tuned dials.
Once enough history accrues, it switches to Elo.

---

## 2. Building the match margin

Inside `predict(fx)`:

```
if (useElo)   margin = eloGapToPoints(eloHome - eloAway, scale)
                       - homeInjury + awayInjury + hga
else          margin = (effRating(home,'home') - homeInjury)
                       - (effRating(away,'away') - awayInjury) + hga
```

- `hga` = home-ground advantage in points. Default 2; when the learning loop is
  active it's the learned `homeAdv` (observed mean home winning margin). Adjustable
  in Advanced settings.
- `homeInjury` / `awayInjury` = the injury penalties from §3.

Then the margin is squashed:

```
modelP = logistic(margin) = 1 / (1 + e^(-margin / scale))    // scale = logisticScale, PINNED at 7 (see §4)
```

The margin identity the "Show the working" ledger relies on is now simply:
`ratingGap + formGap + hga − hInjPts + aInjPts === margin` (no weather term).

Finally, if bookmaker odds exist for the game, the model blends with the market:

```
market = de-vig(closingOdds)              // remove the bookmaker's margin, get a fair home prob
pHome  = (1 - oddsWeight) * modelP + oddsWeight * market      // oddsWeight default 0.5
```

The favourite (higher `pHome`) is the **model's** favourite — `modelFav(p)`. It is not
necessarily the tip: `tipSide(p)` asks the comp question on top of it (§5). Keep the two
apart; every reporting surface uses `modelFav`, every tip-naming surface uses `tipSide`.

> **When the model's margin side and the blended favourite differ** (the bookies flip
> the tip across 50%), every surface must pair each number with its own team — the
> ledger's "Net:" line and the card's headline sentence do this explicitly
> (2026-08-04 fix; previously "Net: Knights by 0.1 → 54%" quoted the *Raiders'*
> blended chance next to the Knights' margin).

---

## 3. Injuries — position × rating weighted (the important part)

**Data:** the injury feed only gives *Player / Reason / Expected-Return* — no position.
So position and quality come from a **separate live source**: Zero Tackle's overall
player-ratings page, scraped by `cloud_fetch.py` into `nrl_players.js`:

```
window.NRL_PLAYERS = { "nathan cleary": {pos:"Halfback", pct:84.1}, ... }
```

**Who counts as "out this week":** each injury entry carries an expected return like
`— back Round 25`. A player counts only if their return round is **after** the round
being tipped (or is long-term/unknown, e.g. TBC / Finals / Next Season). Someone
"back Round 19" when you're tipping Round 22 is available → 0 penalty.

**Confirmed vs unconfirmed (added 2026-07-28):** an absence with a dated return, a
long-term flag (Finals / Next Season / Indefinite / Season), or a suspension counts at
**full** weight. A player merely *listed* injured with no timeframe (a bare knock)
is only a doubt and counts at **half** weight (`UNCONFIRMED_WEIGHT = 0.5`), so an
early-week gametime decision doesn't swing a tip like a confirmed long-term injury does.
The card's "why" line shows such a player as *in doubt* rather than *out*.

**The team list settles doubts (added 2026-07-30):** the named squads in
`nrl_lineups.js` cut both ways. A player *named* in this round's 17 cancels his own
injury-table entry entirely (a season-long "TBC" can't keep a fit player half-out). A
*doubtful* player — no timeframe — who is **not** in his club's published squad has had
his gametime decision made: he counts as a confirmed absence at full weight, badged
**NOT NAMED**. Before the round's list is published (`namedSquad()` returns null),
doubts stay doubts at half weight.

**Per-player cost** (`playerImpact`), from their position and rating:

```
base = 3.6  if spine   (Fullback / Halfback / Five-eighth / Hooker)
     = 2.1  if edge    (Centre / Winger / Second-row)
     = 1.2  otherwise  (Prop / Lock / front row)
q    = clamp(0.55, 1.4, pct / 70)          // rating scales it: a star > a squad player
pts  = min(5, base * q)                     // single-player cap
```
A player **not** in the ratings map is treated as fringe (≈0.6 pts). Names are matched
by a normalisation that lowercases, strips accents, and keeps apostrophes/hyphens —
both the injury feed and the ratings page are Zero Tackle, so they use the same
spelling and line up.

**Combining a team's injuries:** sort the out-players by cost, then apply steep
diminishing returns and a team cap:

```
factors = [1, 0.65, 0.4, 0.25, 0.12, then 0.08...]
teamPenalty = min(6.5, Σ pts_i * factors_i)
```

So Nathan Cleary (spine, 84) out ≈ **−4.3**; a bench prop out ≈ **−0.9**; two stars out
stacks with diminishing returns up to the cap. This penalty is applied to the model
margin **before** the odds blend, so if the market already priced the injury in, the
blend naturally discounts it (no double-counting).

> If `nrl_players.js` is missing/empty, `injuryPenalty` falls back to a flat per-out
> player cost (still with diminishing returns + cap) so injuries still matter somewhat.

---

## 4. The learning loop (`learn_model.py`)

- **Memory:** `nrl_learned.js.results` is an append-only log of finished games
  `{season, round, home, away, hs, as}`. `parse_nrl.py` grows it (deduped on
  season+round+home+away; entries without a `season` field are treated as 2026 —
  added 2026-08-04 so a 2027 game repeating a 2026 round+pairing isn't silently
  dropped, the Elo replay stays chronological across the boundary, and the front-end
  can't display last year's score as this year's "Full time"). `learn_model.py`
  never deletes it.
- **Elo replay:** every team starts at 1500; games are replayed chronologically
  (season, then round) with a home-ground bump (`eloHGA`) and a margin-of-victory
  multiplier on the K-factor (`eloK`), FiveThirtyEight-style. Since 2026-08-04 the
  MOV multiplier uses the **winner-relative** Elo gap — an upset win is amplified,
  an expected win dampened. (It previously used `abs(gap)`, which dampened every
  big-gap game regardless of who won — the opposite of the intent.)
- **Fitting:** `homeAdv` = observed mean home winning margin. `eloK` and `eloHGA` are
  chosen by a small deterministic grid search that minimises **walk-forward log-loss**
  (each game predicted from ratings *before* it — no leakage). `oddsWeight` is
  grid-searched to minimise Brier only if an odds-history file is supplied, else
  defaults to 0.5.
- **`logisticScale` is PINNED at 7 and no longer fitted (2026-08-04).** In this
  parameterisation the scale cancels exactly for the Elo term, so the walk-forward
  loss can't identify it — the old grid search used it purely as a lever on
  `homeAdv/scale` and always drove it to the grid minimum (5), which then made every
  injury penalty and the HGA ~40% more potent at inference than designed. It cannot
  be learned from win/loss outcomes; never re-add it to the grid (see `GOTCHAS.md`).
- **Backtest:** after fitting, it computes Brier, log-loss and hit-rate over the memory
  and appends one `{date, games, brier}` history snapshot.
  > **Removed 2026-09-12: `backtest.lockTax`.** It measured "how many tips has the
  > forced Roosters pick cost", walk-forward from each Roosters game's pre-game Elos.
  > With no forced pick there is no tax, so `LOCK_TEAM`, `lock_tax_metrics()` and the
  > `backtest["lockTax"]` assignment were all deleted from `learn_model.py`.
  > `validate_learned.py` never required the key, so the publish gate is unchanged.
  > The *principle* that produced it is still live and still important: **never
  > recompute a historical grade in the browser from current Elo** — the current Elo
  > already contains each game's own result. See GOTCHAS 2026-08-02.
- **Guardrail:** under `LOW_CONFIDENCE_THRESHOLD = 30` games it holds conservative
  defaults instead of grid-search results and sets `lowConfidence = true`; the
  front-end then ignores the learned params entirely (see §1).

---

## 5. No team is locked — the exact finals solver

*(2026-09-12. This section used to be "The Roosters lock (the one inviolable rule)" and
described a forced `SYD` tip plus a running "Roosters tax". Both are gone end-to-end.
The old text is preserved in `docs/CHANGELOG.md` 2026-07-29 and 2026-08-04 if you need
the archaeology.)*

### 5.0 The seam

```
predict(fx)   →  an honest probability. Never knows about the comp. Never shaded.
modelFav(p)   →  the side that probability likes. REPORTING ONLY.
tipSide(p)    →  the side actually tipped. THE DECISION.
```

`tipSide()` is one place, and every surface that names a tip calls it (quicklist,
`cardHTML`, `copyTips`, the ledger's for/against colouring, `freeze_tips.mjs`). Its whole
body is:

1. Is this game in `compPlan().splits`? → tip the underdog named there.
2. Is the game an exact coin toss (`|pHome−0.5| < 0.005`) **and** `LOCK_MODE ===
   'tiebreak'`? → `lockPref()` may prefer the house club. Default `LOCK_MODE = "off"`,
   so in the shipping configuration this branch never fires.
3. Otherwise `modelFav(p)`.

Do not move strategy out of `tipSide()` and do not let it leak into `predict()`. The
freeze, the grading, the flip feed and every card assume that single seam.

### 5.1 Why a split is ever correct

Brigitte cannot pass a rival by making the rival's picks. Points only change hands in
games where their tips **differ**. A split — tipping the underdog — buys a chance of
gaining a point on a specific rival, at the cost of expected points. It is worth it only
when the price is small (a near coin-flip) and the payoff is real (the rival is very
likely on the other side).

There is a second reason it works in 2026, and it is the reason the answer is as
aggressive as it is: **footytips breaks a points tie on the lower cumulative margin
error** (`rankByMargin`), and Brigitte holds that countback against everyone. She does
not need to *pass* the leader; she needs to *draw level* and stay there. §5.5.

### 5.2 `finalsPlan()` — full enumeration + backward induction

From Finals Week 1 there is no season left to sample: nine games, four rounds, one
bracket. So the finals rounds are not simulated — they are **solved**.

**The bracket** is derived from the ladder (`teams[]` ships in ladder order, so the seeds
are its first eight rows) and is the real NRL system, not a generic knockout:

```
week 1 (r28)  QF1 = 1v4      QF2 = 2v3      EF1 = 5v8      EF2 = 6v7
week 2 (r29)  SF1 = QF1 loser (HOSTS) v EF1 winner
              SF2 = QF2 loser (HOSTS) v EF2 winner
week 3 (r30)  PF1 = QF1 winner (HOSTS) v SF2 winner
              PF2 = QF2 winner (HOSTS) v SF1 winner
week 4 (r31)  GF  = PF1 winner v PF2 winner, NEUTRAL venue
```

**"Higher seed hosts" is wrong for the preliminary finals** and the code does not do it:
the *qualifying-final winners* host, which differs whenever a seed-1 side loses its QF
and comes back through a semi. The audit walked all 256 week-1..3 outcome paths against
an independently-built bracket: 0 matchup mismatches, 0 hosting differences.

Which specific matchup a future round produces is the whole point — a 1v4 qualifying
final and a 6v7 elimination final are different problems, and *which* one the rivals are
likely to misread is where the value is. Generic future games would erase that.

Games already played are read out of the results memory (`finalsResultWinner()`), never
simulated; a missing result means the bracket is unknowable and `finalsCtx()` returns
null → `finalsPlan()` returns false → the Monte-Carlo path takes over.

**Game probabilities.** The current round uses `predict()` — Elo + injuries + the market
blend, i.e. exactly the number printed on the card, so the panel and the card can never
disagree. Future rounds have no odds and no team lists, so they run on Elo + the learned
home edge only (`finalsEloP()`), with **no home edge at all in the Grand Final**.

**The state** is `(bracket path, three rival score deltas)`. `path` is a bitmask of which
side won each decided slot; the deltas are `rival.totalScore − me.totalScore`, clamped
into an **absorbing band** of ±(points still available + 1). The clamp is *exact, not an
approximation*: once a rival is further ahead than everything still on offer, nothing
later can change the answer. The audit re-ran the entire solve with the band widened by
eight points in every dimension and got **bit-identical values to 17 significant
figures** — that is the proof, and it is worth re-running if anyone touches the band.

Everything memoises into flat `Float64Array`/`Uint8Array` tables keyed by integer (one
table per future round, ~7 MB for a four-round bracket, thrown away with the plan). Cost:
**~330 ms** for a Finals Week 1 bracket — 114k memo states, ~18M inner iterations — and
1–50 ms for the later, smaller rounds. It runs **once per `planStamp`**, not per render.

Optimisation history, so nobody re-treads it: 1108 ms → 590 ms (pooled scratch buffers,
integer memo keys) → 366 ms (flat typed-array memo, successor read inlined into the hot
loop) → ~330 ms (hoisted index arithmetic, split the loop-invariant branch), every step
verified value-identical to six decimals. A Float32 memo bought another 13% and was
**rejected**: the DP sums thousands of terms and the tie-break compares at 1e-12. The
only honest lever left is probability-floor pruning, which would make it approximate.

### 5.3 The rival model — `beh`, and `BEH_AFF_K` lockstep

Each rival's pick probability comes from a **per-member logistic fitted in
`cloud_fetch.py`** and shipped in `nrl_comp.js`:

```
P(member tips HOME) = sigmoid( a + b·lp + loy·(affShare(home) − affShare(away)) )
```

- `lp` — the game's Elo logit (`_elo_logit()` mirrors the page's
  `eloGapToPoints()`/`logistic()` exactly, so both sides see the same covariate).
- `affShare(team)` — that member's season share of picks in that team's games,
  **shrunk toward a coin flip by `BEH_AFF_K` pseudo-games** so a two-appearance team
  can't scream.
- Fitted by plain Newton with an L2 ridge (`BEH_RIDGE = 0.25`) on a 3×3 system, in pure
  Python — the workflow runner has only `requests` + `beautifulsoup4`, no numpy. Members
  with fewer than `BEH_MIN_PICKS = 20` picks ship no fit.
- Shipped as `beh: {a, b, loy, n, hit}`. 2026 values: `b` 0.31–1.60, `loy` 2.16–5.09,
  in-sample `hit` 0.70–0.83, `n` 198–204.

> **`BEH_AFF_K` MUST be identical in `cloud_fetch.py` and `nrl-tipping-guide.html`.**
> The fit and the evaluation must see one and the same covariate. Change it in one file
> only and the coefficients are being applied to a different variable than they were
> fitted on — silently, with no error and no obviously wrong output. Both files carry
> the warning at the constant; keep it there.

> **Why leave-one-out matters.** A member's affinity share for team X is *literally the
> mean of their own picks in X's games*, so the pick being predicted is inside its own
> covariate. Fed in raw it is a perfect in-sample predictor and drove the market/form
> coefficient `b` to **exactly 0.00** for all six members. Each training row therefore
> uses the share with *that* pick removed, then shrunk. Measured: `b` went from 0.45 to
> 1.1+ once this was fixed. Do not "simplify" the `_share()` closure.

If no fit shipped (an old `nrl_comp.js`, or too few picks), the page falls back to
`predictPick()` (the 2026-08-10 loyalty predictor) applied at that member's `herdRate()`.
Same tips in the R28 test, but `pFirst` reads ~3.5 points higher and splits are priced at
+0.3 instead of +2.0 — see the deploy-ordering note in GOTCHAS.

### 5.4 `STRAT_AWARE` — rivals play strategically too, sometimes

Everyone in a tight finals comp is capable of splitting deliberately. `finalsStratVector()`
models that: **with probability `STRAT_AWARE` (0.25) a rival plays a comp-aware line for
the WHOLE round** —

- level with or ahead of the leader → cover with favourites;
- behind by `d` → take the underdog in the `ceil(d/2)` most winnable games, skipping any
  underdog below 15% (a hopeless split is worse than useless).

Two properties are load-bearing:

- **The mode is latent and per-round, not per-game.** That is what correlates a rival's
  picks *within* a round, and correlation is what makes one observed pick informative
  about their others.
- **It never overrides a pick that is already visible.** Once a game kicks off footytips
  reveals what everyone actually tipped; `fixedPicks` pins those, for both the
  behavioural and the strategic component.

`STRAT_AWARE = 0.25` is a **construction, not an observation** — R24–R27 were
regular-season rounds with the comp not yet tight, so there is nothing to fit it on. The
reference solver's sensitivity sweep says the R28 recommendation survives 0.00, 0.25 and
0.50 (the effect is non-monotonic: a *moderate* amount of strategic play is worst for her,
because it puts Thorners and Jake on the Dolphins beside her, while a lot of it makes them
bleed points on splits that don't land). It is a single page constant, easy to retune.

### 5.5 The countback — `finalsTieProbs()`

footytips' `rankByMargin` gives a points tie to the **lower cumulative margin error**
(`totalMargin` = Σ over rounds of |predicted margin − actual margin of that round's
designated margin game, which is the round's FIRST game`|`). Brigitte's 476 against
Claire's 492, Jake's 492 and Thorners' 515 is her entire edge, so a tie is **not** a loss
here and must never be priced as 0.5.

It is modelled as a race on accumulated error. With `D_r` = (their error − her error) in
round `r`, she keeps the tie iff `currentLead + Σ D_r > 0` over the margin games still to
come:

```
mean per round  = lead / rounds        (from the season totals — 28 rounds of evidence)
sd              = sd of the per-round differences, floored at 5, default 10
P(tie kept)     = Φ( (lead + mgLeft·mean) / (sd·√mgLeft) )
```

Two rules the code enforces and you must not relax:

- **Only zip the per-round histories when `COMP.roundIndexed` is true.** On an old dense
  file, index *i* is her *i*-th recorded round and his *i*-th, which are different
  calendar rounds the moment either has a gap. Refusing to zip falls back to the
  season-total mean with sd 10 — imprecise, but not silently wrong.
- **Both sides of every pair must be numbers.** Nulls are gaps, not zeroes.

Known simplification: tie-break outcomes are treated as **independent across rivals**. A
bad margin guess by her hurts against everyone at once, so this slightly overstates
P(1st) in tied states. Same simplification as the Python reference. An exact dead heat
(identical cumulative margin) is treated as probability zero; footytips would actually
show a shared rank.

### 5.6 The bonus, and who gets modelled

- **`allCorrectBonus` +2 applies in finals rounds too.** A one-game Grand Final round
  pays 1 + 2 = **3**. The audit's hand-computed GF at deficits 0–4 is what proves the
  page pays it: 2 behind is only survivable *because* a correct one-game round pays 3.
- **Alive-aware.** A wrong tip in a game already played this round kills that tipper's
  bonus for the round (`myBonus` / `rivBonus[]`). An *unknown* tip is treated as broken.
- **`FINALS_MAX_RIVALS = 3`.** The DP is exact in three rival deltas; a fourth costs
  ~25× the state space and will not run in a browser. Rivals are taken
  highest-score-first among the mathematically alive, so truncating can only
  **overstate** P(1st) — and the Python reference enumerated exactly how much, over all
  256 remaining result paths, for the one truncated 2026 rival (Josh, who needs a literal
  9-from-9 with every bonus): **0.61%**. Every P(1st) the app prints is therefore high by
  at most that. In a tighter comp with four genuinely live rivals this is the constant to
  worry about first.
- **The aliveness filter is ONE-SIDED, deliberately.** Only the provably beaten
  (`m.totalScore + maxGain < me.totalScore`) are dropped. See GOTCHAS "the one-sided
  aliveness filter" — dropping an out-of-reach *leader* made the DP see no threats and
  return **1**, printing "Chance of winning the comp: 100%" while she was mathematically
  eliminated.

### 5.7 Reading the answer off, and arming a split

`playRound()` returns the value of every admissible tip vector for the round. Then:

- **Tie-breaks, in order: favourites → the incumbent frozen tip → `LOCK_MODE`.** Exact
  equality only (`EQ = 1e-12`), so this can never cost win probability. Favourites lead
  because the exact DP has no sampling noise — a tie is a *real* tie, reproducible run to
  run — so incumbency buys nothing here and does harm in a decided comp, where every line
  prices identically and "the incumbent" is whatever the tiplog last held. (Leading by 30
  with three rounds left, incumbent-first armed three underdogs as splits "worth +0.0
  points" and swallowed the cover-mode sentence.) Incumbency stays *first* in the
  Monte-Carlo path, where it exists to stop noise churning the flip feed.
- **A split is armed only when the underdog is strictly worth more** (`vDog > vFav + EQ`).
  Each game's price is computed honestly: the best achievable P(1st) with that game pinned
  to the favourite, versus pinned to the underdog. That difference is the number the panel
  prints ("+2.0 pts of win chance"), and it is in **win probability**, not expected tips.
- The "tipping favourites the rest of the way" baseline pins her *locked* games to what
  she actually entered — it is an honest "tip chalk from here", not a rewrite of history.

### 5.8 The boot path — provisional plan, idle solve

A ~330 ms synchronous solve on first paint is ~1 s of blocked paint on a phone, and Josh's
rule is that the app just works with no narration. So `compPlan()` is a **front door that
always returns synchronously**:

1. the in-memory plan, if it is for this stamp and not provisional; else
2. `planCacheRead()` — the last solved plan for **this exact stamp** out of
   `localStorage` (`nrl_plan_v1`). This is an *answer*, not a guess, because
   `planStamp()` is `PLAN_VER | COMP_STAMP | round | lockedMask | results |
   dataSig(SRC) | gamesLearned | TIPLOG.length` — the plan is a pure function of it; else
3. `planFromTiplog()` — the pipeline's frozen tips read back as a split set, i.e. what
   the last workflow run computed **with this same code**, marked `provisional`; else
4. straight favourites.

The real solve is queued by `schedulePlanSolve()` on `requestIdleCallback` (timeout 400 ms,
`setTimeout(0)` fallback) and re-renders only if `splitSig()` changed. Measured in
headless Chromium: **0.7 ms to correct tips** cold, solve landing 446 ms later with no
change; **0.2 ms and no solve at all** on a return visit.

Three guards, all load-bearing:

- **`PLAN_VER` (`'dp1'`) must be bumped whenever the solver's maths changes**, or a
  returning device reuses the previous model's cached plan.
- **`snapTips()` refuses to snapshot a provisional plan.** The local snapshot is the
  "what this browser actually showed pre-kickoff" grading backup; a tip that stood for one
  frame is not that.
- **A *later* re-solve re-renders surgically** (`renderCompBits()` + `renderStratBits()` +
  `ORDER_DIRTY`), never `render()`, which would snap open `<details>` shut. Only the first
  solve of the session does a full render. Same rule `pollComp()` follows.

**The freeze must never defer.** `freeze_tips.mjs` publishes to every device; a
provisional answer there is the wrong tip everywhere. It sets `window.NRL_SYNC_PLAN`
before the page's scripts (forcing the sync path in the page's own boot render too) and
calls `compPlanSync()` before reading tips. `reference/crosscheck.mjs` does the same.

### 5.9 Verifying a change to any of this

1. `node reference/crosscheck.mjs` — boots the real page in jsdom and compares P(1st) for
   every R28 tip vector against `reference_finals_solver.py`. `COMPFILE=…` points it at a
   `nrl_comp.js` with fitted `beh` (the shipping configuration).
2. `node freeze_tips.mjs` **twice** — the second run must report `0 new/changed`.
3. `node smoke_test.mjs` (59/59) and `python3 test_ios_viewport.py` (20 green).
4. Compare a real headless Chromium render against the jsdom freeze: `pFirst` must match
   to the last bit.

Expect the page and the Python reference to differ by up to ~3.2 points *uniformly* — the
reference fits one global no-intercept logistic over R24–R27 (strongly market-following,
therefore accurate rivals), the page fits per-member over the whole season (more
loyalty-driven, therefore slightly less accurate rivals, therefore a uniformly higher
P(1st) for her). What must **not** differ: the best line, and the ordering of
Roosters-containing lines below non-Roosters ones.

---

## 6. Glossary

*(Numbered 2026-09-12. Several code comments and docs used to point at "docs/MODEL.md
§6" when there was no §6 — §5 was the lock and the glossary was unnumbered. The dangling
references in `nrl-tipping-guide.html` were cleaned up in the same batch; this heading
exists so any that survive in old notes resolve to something.)*

- **Margin** — predicted/actual home points minus away points. The model's native unit.
- **Elo** — a self-correcting rating; teams gain/lose points based on results vs
  expectations. Base 400 is the standard probability scale.
- **HGA / homeAdv** — home-ground advantage, in points, added to the home side.
- **Logistic / scale** — the S-curve turning a points margin into a 0–1 win
  probability; `scale` sets how steep it is (pinned at 7 points — unlearnable, see §4).
- **Brier score** — mean squared error of probability forecasts (0 = perfect, lower is
  better). The app's main calibration metric.
- **Log-loss** — another proper scoring rule for probabilities; punishes confident
  wrong calls harder. Used for the parameter grid search.
- **Hit-rate** — plain "did the tip win" percentage (draws excluded).
- **Walk-forward** — evaluating each game using only information available *before* it,
  so the backtest doesn't cheat by peeking at the outcome it's predicting.
- **De-vig** — removing the bookmaker's built-in margin from odds to recover a fair
  implied probability.
- **CLV (closing-line value)** — whether the model beat the market's opening vs closing
  price; the honest way to judge a tip against the book.
- **Spine** — fullback, halfback, five-eighth, hooker; the positions that most drive a
  team, hence weighted heaviest when injured.
- **lowConfidence** — the learning-loop guardrail flag; while true, learned params are
  ignored in favour of the hand-tuned heuristic.
