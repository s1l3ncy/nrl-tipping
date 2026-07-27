# Pro Tipper Panel — Model Review & Accuracy Roadmap

Four experts audited the model (season points-margin blended with home/away splits, a
last-5 form nudge, a home-ground edge, and an optional bookmaker-odds blend):

- **The Sharp** — professional bettor, market/edge lens
- **The Quant** — sports modeller, statistics/validation lens
- **The Analyst** — ex-club performance analyst, rugby-league lens
- **The Strategist** — tipping-comp winner, "win the comp" lens

## Headline consensus

1. **The model can't currently tell whether it's any good.** It logs win/loss of the *tip*
   but throws away the *probability* behind it. Without that you can't measure calibration,
   and you can't tell skill from luck. Every panelist landed here first.
2. **Its key numbers are asserted, not fitted.** The 7-point logistic scale, the 2-point home
   edge, and the flat 50/50 model-vs-market blend were all hand-set and never validated against
   real outcomes.
3. **It ignores the things that decide the close games.** Injuries/team-news and weather are
   shown on the card but don't move the prediction at all, and there's no strength-of-schedule,
   no rest/travel, no late-mail reaction.
4. **A real bug:** the docs/SPEC promise an Elo replay when a full results log is supplied, but
   the current shipped front-end doesn't implement it — ratings are always the flat season
   average. Either wire Elo in or drop the promise.

## Roadmap — ranked by accuracy-per-effort

### Tier 1 — do these first (high impact, low effort, uses data we already have)
- **Log the model's probability, not just the tip.** Store predicted `pHome` per game, then
  score the season with **Brier score** and **log-loss** and draw a **calibration curve**. This
  is the single most valuable change — it turns "I went 6/8" into "am I actually calibrated?"
- **Fit the logistic scale to real margins.** Replace the hardcoded `/7` with a scale fit by
  logistic regression on logged margin→result data. Same for the home-ground edge.
- **Capture opening *and* closing odds (timestamped), not one snapshot.** Enables **closing-line
  value (CLV)** — the honest yardstick for whether the model beats the market. Track model prob
  vs closing-market prob each week.
- **Make the odds-blend weight earned, not fixed.** Tie `oddsW` to the model's rolling Brier
  score vs the market's, instead of a static 0.5.

### Tier 2 — meaningful accuracy gains (medium effort, mostly existing data)
- **Fix the double-count.** The 50/50 "overall margin + home/away-split margin" blend re-uses
  games already inside the overall average. Replace with an **opponent-adjusted margin**
  (strength-of-schedule) — beating good teams should count more than beating the Dragons.
- **Add shrinkage / regression to the mean** for small samples and early season (weight ≈
  P/(P+k) toward league average) so a 7-game home split isn't trusted like a 15-game one.
- **Exponential recency weighting** on match margins instead of a flat season average plus a
  clamped last-5 nudge.
- **Actually use the injury feed.** Turn the `news` string into a margin penalty, weighted by
  position — a halfback/hooker/fullback (the "spine") out matters far more than a bench forward.
  Regex-tag the late mail for "ruled out"/spine names.

### Tier 3 — footy factors worth encoding (scrapable, incremental)
- **Short turnarounds:** derive days-rest from kickoff deltas; penalise <5-day breaks.
- **Travel:** use the `city` field to flag interstate / trans-Tasman trips (Warriors, Townsville,
  Perth) as an away penalty distinct from the generic home edge.
- **Dead rubbers / motivation:** late-season, dampen ratings for teams already locked into or out
  of the eight (derive from ladder position + rounds left).
- **Weather styling:** in the wet, widen uncertainty / favour low-error kicking teams rather than
  just shifting the favourite.

### Tier 4 — needs new data or manual upkeep (lower priority)
- Venue-specific "fortress" records (needs venue-level history, not just home/away).
- Head-to-head / hoodoo effects (needs a historical results log).
- Representative/Origin fatigue, coaching-change bounce (need player-rep lists / manual flags).

## Winning the comp (not just raw accuracy)
- **Optimise for the comp's actual scoring.** Add a setting for win-only vs margin vs
  confidence/streak comps — a confidence comp rewards *ranking* the 8 tips by probability, not
  just picking them. Surface the predicted **margin** (already computed) for margin comps.
- **Quantify the Roosters tax.** Add a season stat: expected tips lost by being forced onto the
  Roosters when the model preferred the opponent. Right now the loyalty rule looks cheap
  (Roosters are 13-5) but the tool can't say *which rounds it actually bled ground*.
- **Upset-of-the-week flag** on the closest-to-50% game — the best spot to fade the crowd when
  you're chasing a rival.
- **Rival tracker:** log a rival or two's tips; beating one specific person matters more than raw
  hit-rate, and divergent picks are where ladders are won.

## Honest "won't move the needle"
- Fine-tuning the logistic constant or home-edge by hand (do it with data or leave it).
- Chasing more decimal places on ratings while injuries/weather remain cosmetic.
- Expecting to consistently beat the closing line — realistically the model's job here is a
  well-*calibrated* tip and a sensible confidence order, not a betting edge.
