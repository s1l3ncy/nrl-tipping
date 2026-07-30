# The Model — how a tip is calculated

This is the heart of the project: exactly how the app turns data into a predicted
winner and a confidence for each game. All of this runs **in the browser** inside
`nrl-tipping-guide.html`; the learning loop (`learn_model.py`) mirrors the same math
server-side so its backtest numbers mean what the app will actually show.

Everything works in **points of margin** (predicted home margin), which is then
squashed into a win probability. Injuries, weather, home-ground edge and the Elo/
form ratings all contribute in the same points space so they compose cleanly.

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

Then **weather** shrinks the margin (see §4), and the margin is squashed:

```
modelP = logistic(margin) = 1 / (1 + e^(-margin / scale))    // scale = learned logisticScale, default 7
```

Finally, if bookmaker odds exist for the game, the model blends with the market:

```
market = de-vig(closingOdds)              // remove the bookmaker's margin, get a fair home prob
pHome  = (1 - oddsWeight) * modelP + oddsWeight * market      // oddsWeight default 0.5
```

The favourite (higher `pHome`) is the model's tip — **except** the Roosters game (§6).

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

## 4. Weather — shrinks confidence, never picks a side

With no per-team wet-weather data, weather does **not** favour either team. It only
reduces certainty as rain rises (wet games are more random). Since 2026-07-30 the
fixture's weather string is the forecast for the game's **own local day** (matched from
its kick-off date) — not the old "wettest of the next ~6 days", which routinely shrank a
Thursday game by Saturday's rain. From that string it reads the rain %:

```
shrink = clamp(0, 0.22, 0.30 * (rain% - 0.20) / 0.80)     // nil below 20% rain, up to -22%
margin = margin * (1 - shrink)                             // pulls toward a coin-toss; sign preserved
```

Because the sign is preserved, weather can lower confidence but can't flip a tip on
its own. Applied before the odds blend, same as injuries.

---

## 5. The learning loop (`learn_model.py`)

- **Memory:** `nrl_learned.js.results` is an append-only log of finished games
  `{round, home, away, hs, as}`. `parse_nrl.py` grows it (deduped); `learn_model.py`
  never deletes it.
- **Elo replay:** every team starts at 1500; games are replayed chronologically with a
  home-ground bump (`eloHGA`) and a margin-of-victory multiplier on the K-factor
  (`eloK`), FiveThirtyEight-style (bigger blowouts move ratings more, dampened when the
  result was expected).
- **Fitting:** `homeAdv` = observed mean home winning margin. `eloK`, `eloHGA`,
  `logisticScale` are chosen by a small deterministic grid search that minimises
  **walk-forward log-loss** (each game predicted from ratings *before* it — no leakage).
  `oddsWeight` is grid-searched to minimise Brier only if an odds-history file is
  supplied, else defaults to 0.5.
- **Backtest:** after fitting, it computes Brier, log-loss and hit-rate over the memory
  and appends one `{date, games, brier}` history snapshot so accuracy-over-time is
  tracked honestly.
- **Guardrail:** under `LOW_CONFIDENCE_THRESHOLD = 30` games it holds conservative
  defaults instead of grid-search results and sets `lowConfidence = true`; the
  front-end then ignores the learned params entirely (see §1).

---

## 6. The Roosters lock (the one inviolable rule)

In the Roosters' own fixture the tip is **forced to `SYD`**, no matter what the model
computes. The model still runs for that game — the app uses it to tell you honestly
whether the model agrees with the loyalty pick or not, and tracks a running
**"Roosters tax"**: how many tips the forced pick has cost versus what the model would
have chosen. Never remove or "correct" this lock; it's the point of the app.

**Where it lives:** one helper, `tipSide(p)` in `nrl-tipping-guide.html`. It returns the
Roosters whenever either side is `LOCK`, and `modelFav(p)` otherwise. Every surface that
names a tip calls it — quicklist, the card's tipline and ★/🔒 badges, **Copy tips**, and
the ledger's for/against colouring. (Until 2026-07-29 each of those recomputed
`pHome>=0.5?h:a` independently and only *annotated* the Roosters game, so the lock was
cosmetic: with the model disagreeing, "Copy tips" pasted the Roosters' **opponent**
labelled `(locked)`, and the tax measured a rule that wasn't being applied.)

`predict()` deliberately does **not** apply the lock — it returns the model's own
probability, which is what lets `lockHero` say "⚠ Risky this week — the model favours X",
the ledger print the loyalty-pick line, and the tax be computed at all. If you add a new
surface: call `tipSide()` for the pick, `modelFav()` only to report what the model thinks.

---

## Glossary

- **Margin** — predicted/actual home points minus away points. The model's native unit.
- **Elo** — a self-correcting rating; teams gain/lose points based on results vs
  expectations. Base 400 is the standard probability scale.
- **HGA / homeAdv** — home-ground advantage, in points, added to the home side.
- **Logistic / scale** — the S-curve turning a points margin into a 0–1 win
  probability; `scale` sets how steep it is (default 7 points).
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
