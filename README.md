# NRL Tipping Guide

A tool that works out who to tip each NRL round so that **Brigitte has the best
possible chance of finishing 1st** in the family footytips comp. Not the most
accurate tips — the tips most likely to *win the whole thing*, which occasionally
means backing an underdog everyone else has got wrong.

> **Changed 2026-09-12.** This app used to be Josh's, and its one fixed rule was that
> the Sydney Roosters were always tipped, whatever the numbers said. Josh handed it to
> Brigitte, who has no club loyalties — *"she really wants to win"* — so the rule is
> gone and the objective is now, exactly, the probability she finishes first. In the
> 2026 finals that one change was worth about **6.5 percentage points** of win chance
> in a single game. Anywhere below that still talks about a locked Roosters tip or a
> "Roosters tax" is describing the old version; `docs/MODEL.md` and `docs/STRATEGY.md`
> are current.

## What's new

- **Opening and closing odds (CLV).** The data feed now keeps track of the
  FIRST bookmaker odds seen for a game (the "open") as well as the LATEST
  ("close"), so you can see whether the market moved and whether the model
  would have beaten the opening line, the closing line, or neither — this
  is called closing-line-value (CLV), the honest way to judge a tip against
  the market rather than just "did I win".
- **The model's own confidence is now tracked, not just its tips.** Every
  predicted win chance is logged, and the app scores itself with a Brier
  score and a calibration view over the season — so it can tell you whether
  its percentages are actually trustworthy, not just whether it happened to
  pick the winner.
- **Tip for how YOUR comp actually scores.** A setting lets you match the
  model's advice to your competition's format — straight win/loss, margin
  (closest points-margin), or confidence/streak (ranking your 8 tips by how
  sure you are) — since the best pick can differ depending on how you're
  scored.
- *(removed 2026-09-12)* **The "Roosters tax", quantified.** A running season stat
  showed roughly how many tips the locked Roosters pick had cost you compared with
  what the model would have picked. With the lock gone there is no tax to measure;
  the stat tile now shows **your comp place and your chance of finishing 1st**.
- **Upset-of-the-week.** Each round, the game closest to a 50/50 toss-up is
  flagged — handy if you're chasing a rival and need to find the best spot
  to fade the crowd.
- **Draws now count fairly.** If a game ends in a draw, it no longer counts
  as a "correct" or "incorrect" tip for anyone — it's set aside as a push,
  so your accuracy record isn't unfairly bumped up or down by a tie.
- **No more accidental double-logging.** If you try to log the same game's
  result twice, the app now recognises it and won't double-count it in your
  records.
- **A heads-up when the data looks stale.** If the weekly data feed hasn't
  refreshed in about 8 days or more, you'll see a warning on screen so you
  know you might be looking at an old round. It's just a nudge — the app
  still works, but check whether a fresher update is available.
- **"Copy tips" button.** Want to quickly paste this round's tips into a
  text, group chat, or email? There's now a one-click "Copy tips" button
  that grabs a plain-text list of the round's picks for you.
- **Advanced settings, tucked away.** The knobs for fine-tuning the model
  (home-ground advantage bonus and recent-form weighting) have moved into a
  collapsed "Advanced settings" section, out of the way of everyday use.
  Open it only if you want to experiment with how the model weighs things.
- *(removed 2026-09-12)* **Model vs Roosters-lock accuracy tracker.** Compared the
  model's own pick against the locked Roosters pick over the same games. There is no
  lock any more, so there is nothing to compare it with.
- **Richer per-game detail.** Each game now shows extra context where it's
  available: the bookmakers' odds next to the model's own percentage (so
  you can see where the model agrees or disagrees with the market), each
  team's home/away form split (a team can be great at home and shaky on the
  road, or vice versa — now you can see that at a glance), the latest
  injury/team-news for each side, and a short weather note for the host
  city. Any of these can show as "not available yet" for a given week —
  that's normal, not a bug (see below).
- **The round picks itself.** You no longer need to select which round
  you're tipping — the app automatically shows the next unplayed round
  based on the latest data feed, so there's one less thing to manage each
  week.

### About the new odds / injuries / weather fields

These three pieces of extra detail are "best effort" — they come from
separate weekly fetches (bookmaker odds, NRL team-news, and a weather
forecast) that don't always happen or land in time, unlike the core ladder
and draw which refresh every week without fail. If one of them is missing
for a game, the app just leaves it out for that game rather than showing
a broken box — everything else keeps working normally.

Odds specifically are now captured twice: the first price seen for a game
(the "open") and the latest one (the "close"), so the app can show whether
the market moved and compare the model against both — that's the
closing-line-value (CLV) feature mentioned above. You don't need to do
anything differently to get this — the same daily/gameday refresh just
records both automatically now.

Team news, odds, and weather now also refresh daily (and more often on game
days), while the ladder and fixture list still only rebuild once a week.

## How to open it

1. Find the file **`nrl-tipping-guide.html`** in this folder.
2. Double-click it. It opens in your normal web browser (Chrome, Safari,
   Edge, etc.) — no install, no internet connection needed to use it.
3. That's it. You'll see this round's games, the tip for each, and — on the Tips
   screen — your chance of winning the comp, plus a 🎯 mark on any game where the
   tip is deliberately *not* the favourite because it improves that chance.

You can close and reopen the page any time — anything you type in (results,
edited team stats, edited fixtures) is remembered in your browser between
visits.

## What's on the screen

- **This round's tips** — every game in the current round (chosen for you
  automatically — there's no round selector to manage), with the tip and a
  win-likelihood bar. A game marked 🎯 is a **comp split**: the tip there is not
  the favourite, on purpose, because the numbers say it raises your chance of
  finishing first. The line under it tells you by how much, and who is on the
  other side.
- **The comp panel** — one number that matters: *"Chance of winning the comp: N%"*,
  next to how far behind (or ahead) you are and what you'd be on if you simply tipped
  the favourites the rest of the way. Plus the mini ladder with the margin countback,
  and the margin-game advice for the round's first game.
  *(This used to be a "safe / risky" banner about the Roosters pick — gone 2026-09-12.)*
- **Per-game detail** — where available: the market odds alongside the
  model's percentage, each team's home/away split record, injury/team-news
  notes, and a short weather line for the venue's city. Missing pieces
  just don't show, rather than the app guessing or erroring.
- **Weekly update — log a result** — once a game has been played, pick the
  two teams and enter the final score here, then save. This updates that
  team's win/loss record, points for/against, and recent form.
- **Power ratings & ladder** — a simple ladder driven by the same numbers
  the model uses, so you can see why it favours who it favours, plus each
  club's colour so it's easy to scan.

## How the model works (plain English)

Every team gets a single "power rating" for the season so far. It's their
average points margin per game — points scored minus points conceded,
divided by games played — blended with how they've gone specifically at
home or away. Early in the season, or off a small number of games, that
home/away split is trusted less and pulled back toward the team's overall
average (so a hot 3-game home streak doesn't get over-weighted); as more
games pile up, the split carries more weight.

That rating then gets a small nudge for **recent form** — how many of their
last five games they've won — and a penalty if their latest team-news
mentions a key player is out, weighted by how important that position is
(a halfback, hooker, or fullback missing matters more than a bench forward).

For any given match, the tool works out the gap between the two teams'
ratings, adds a small bonus for the home team (home-ground advantage), and
turns that gap into a percentage chance of winning. If bookmaker odds are
available, the model's own percentage is blended with the market's (using
the closing odds when both an opening and closing price have been seen).
Whichever team comes out ahead is the model's tip for that game.

Whichever team the numbers favour is the **model's** pick — but the model's pick is
not automatically the tip. Since 2026-09-12 the tip comes from a second step that asks
a different question: *given where everyone sits on the comp ladder and what the rivals
are likely to tip, which set of tips gives Brigitte the best chance of finishing 1st?*
Usually that is the favourite. Occasionally it is the underdog in a near-coin-flip game
that the leader is on the wrong side of — a **split** — because you cannot pass someone
by making the same picks they do. In the 2026 finals the app solves the remaining
bracket exactly rather than guessing. `docs/STRATEGY.md` explains it in plain English.

*(Until 2026-09-12 this section read "The **Roosters are always tipped** in their own
game, regardless of what the model says — that's a fixed rule, not a suggestion",
alongside a running "Roosters tax". Both are gone.)*

**A note on Elo:** earlier versions of this document said Elo was planned
future work, not yet wired up. That's now out of date — see "How it learns"
below for the real, current picture: the app does keep a full-season match
log and does replay an Elo rating from it each update.

## How it learns

On top of the hand-tunable formula above, the app now has a genuine
learning loop:

- **It remembers every result.** Every game you (or the weekly refresh)
  logs is kept in a full-season match log, not just this week's ladder
  snapshot.
- **It re-fits its own dials each update.** Home-ground advantage, how
  steeply a points-margin gap turns into a win percentage, and how much to
  trust bookmaker odds are no longer fixed numbers someone picked by hand —
  they're re-estimated from the match log every time the data refreshes.
- **It keeps an Elo rating for every team**, replayed from the full match
  history each update, alongside the formula above.
- **It backtests itself.** After each re-fit, the app checks how well its
  past predictions would have scored against what actually happened
  (a Brier score — lower is better-calibrated) and tracks that trend over
  time, so it can tell you honestly whether it's actually getting better,
  not just assume it is.
- **Guardrail: it doesn't trust itself too early.** With only a handful of
  games to learn from, a fresh fit can be noisy. Until roughly **30 games**
  of history have been backtested, the app treats its own learned numbers
  as low-confidence and leans on the steadier hand-tuned formula instead —
  it only switches over once it's earned enough evidence.
- **A "what it's learned" panel** shows this in plain sight — the current
  dials, the Elo ladder, the backtest numbers, and a low-confidence badge
  whenever the guardrail above is active — so you can see why the model
  believes what it believes, not just its latest tip.

## How the weekly auto-refresh works

Once a week, an automated job:

1. Fetches the latest ladder (including each team's home/away split) and
   next round's draw from the NRL's usual public sources (Zero Tackle and
   NRL.com) — this part always runs.
2. Best-effort, also fetches match odds, injury/team-news, and a weather
   note for each host city, if those sources are available that week.
3. Turns all of that into an updated `nrl_data.js` file sitting next to the
   HTML file in this folder.
4. Checks that file is valid (correct number of teams, valid fixtures, etc.)
   before it's allowed to go live. Missing odds/news/weather never blocks
   this — only a broken ladder or draw does.
5. The next time you open (or refresh) `nrl-tipping-guide.html`, it
   automatically loads whatever is in `nrl_data.js` and shows the round
   that's next up — you don't need to do anything. The header shows the
   date it was last updated and where the data came from.

If, for any reason, `nrl_data.js` is missing or broken, the page falls back
to the last known-good data baked into it, so it never shows a blank or
broken screen.

The exact steps the automated job runs each week are written out precisely
in `WEEKLY_UPDATE.md`, for anyone maintaining this app.

## How to log results each week

1. Wait until a round's games have been played.
2. Open `nrl-tipping-guide.html`.
3. In the **"Weekly update — log a result"** section, choose the home team,
   type in the final home score, type in the final away score, choose the
   away team, and click **Save result**.
4. Repeat for each game played that round.
5. The ladder, ratings, and next round's tips update automatically as you
   go — no need to reload the page.

Your logged results stay saved in that browser only. If the weekly
auto-refresh (above) later brings in fresh official data for the same round,
that official data takes over the next time the page loads.

## Files in this project (for reference)

| File                        | Purpose                                              |
|------------------------------|-------------------------------------------------------|
| `nrl-tipping-guide.html`     | The app itself — open this one.                       |
| `nrl_data.js`                | Weekly data feed the app loads automatically.         |
| `nrl_learned.js`              | The app's learned memory + fitted params/Elo — see "How it learns". |
| `parse_nrl.py`                | Turns raw fetched source pages into `nrl_data.js`.    |
| `learn_model.py`              | Re-fits params + Elo from the match log into `nrl_learned.js`. |
| `validate_data.py`            | Checks `nrl_data.js` is valid before it's used.       |
| `validate_learned.py`         | Checks `nrl_learned.js` is valid before it's used.    |
| `smoke_test.mjs`              | Automated check that the tipping math still works.    |
| `WEEKLY_UPDATE.md`            | Step-by-step runbook the weekly job follows.          |
| `SPEC.md`                      | The technical build spec for this project.            |
