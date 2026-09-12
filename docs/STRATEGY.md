# Comp strategy — how the app plays to win

*Written 2026-09-12, Finals Week 1. For Josh and Brigitte first, agents second.*

This is the one doc to read if you want to know **why the app tips what it tips** without
reading any code. `MODEL.md` §5 is the same thing in engineering terms; `CHANGELOG.md`
2026-09-12 is the dated record of the night it was built.

The short version: since 2026-09-12 the app has exactly one goal — **make Brigitte finish
1st**. Not tip accurately. Not finish top three. First. Every design decision below falls
out of that, including the uncomfortable ones.

---

## 1. The comp, and its rules (verified from the API, not from the UI)

**Comp:** "Family Feud" on ESPN footytips. `COMP_ID` 1372189, ladder 381260129, six
members. The endpoint is public — no cookie, no token, CORS open:

```
https://api.footytips.espn.com.au/competitions/1372189/sports/rugby-league/
  leagues/nrl/game-types/tipping/ladders/381260129/rounds/{N}?view=tips
```

Everything below was read out of `ladder.customScoringOptions` and cross-checked against
five rounds of published results. **Do not re-derive these from the website** — the UI
does not show them all, and one of them (which game carries the margin) is not documented
anywhere.

| Rule | Value | Why it matters |
|---|---|---|
| Points | **1 per correct tip** | |
| Perfect-round bonus | `allCorrectBonus {applyTo: Season, modifier: 2}` — **+2 for tipping every game in a round correctly** | It applies in the **finals** too. A one-game Grand Final round therefore pays **1 + 2 = 3**, which is the only reason being 2 points behind going into the GF is survivable. |
| No tip | `defaultScoreMethod: Zero` | Missing a game scores 0, it does not default to the favourite. |
| **Tie-break** | `rankByMargin: true` — a tie on total points goes to the **LOWER** cumulative margin error | **This is Brigitte's entire edge.** See §3. |
| Margin error | `totalMargin` = Σ over rounds of \|her predicted margin − the actual margin\| for that round's **designated margin game** | |
| The margin game | **the FIRST game of the round** | Verified for every member in every round R24–R28: `results[].round.margin` is exactly that, and the sign always agrees with the side they tipped. R28's was SOU–NEW. |
| Comp ends | `finishRound: 31` | Rounds 28 = Finals Week 1 (4 games), 29 = Semis (2), 30 = Prelims (2), 31 = Grand Final (1). |
| Pick visibility | Sealed server-side until a round starts, then revealed **game by game at each kick-off** | So rivals' picks become information *during* a round. §5 exploits this. |

---

## 2. Where everyone stood (12 Sep 2026, 08:35 AEST)

After Souths lost the Friday-night elimination final 10–20 to Newcastle:

| # | Member | Total | Margin error | R28 SOU–NEW | Perfect round still alive? |
|---|---|---|---|---|---|
| 1 | Claire with an i | 132 | 492 | SOU ✗ | no |
| 2 | **Brigitte** | **131** | **476** | SOU ✗ | no |
| 3 | Thorners69 | 130 | 515 | SOU ✗ | no |
| 4 | Jake | 128 | 492 | SOU ✗ | no |
| 5 | Special unit (Josh) | 121 | 506 | NEW ✓ | yes |
| 6 | Susie loo | 112 | 541 | NEW ✓ | yes |

Fourteen points of tipping remain for the leaders (8 games + 3 bonuses they can still
reach). Read this table twice, because two things in it decide everything:

- **The top four are inside four points**, and none of them can get this round's bonus.
- **Brigitte has the lowest margin error of the four.** She wins any tie.

Josh and Susie can still bank perfect rounds but are effectively out: Susie is
mathematically eliminated (112 + 16 = 128 < Brigitte's floor of 131), and Josh needs a
literal 9-from-9 with every bonus *and* Brigitte to collect ≤6 of her remaining 14 —
enumerated exactly over all 256 remaining result paths, **0.61%**.

Ladder / bracket for 2026: 1 PEN, 2 NZW, 3 DOL, 4 SYD, 5 CRO, 6 SOU, 7 NEW, 8 NQL.

---

## 3. How the solver reasons — in plain English

### You cannot pass someone by copying them

If Brigitte and Claire tip the same eight games, they finish the round the same distance
apart no matter what happens on the field. Points only change hands in games where their
tips **differ**. So "tip the most likely winner every week" is a fine way to maximise
your score and a bad way to win a comp you are behind in — it guarantees you stay behind.

A **split** — deliberately tipping the underdog — is how you create a chance of gaining.
It costs you expected points and buys you a chance of a swing. It is worth doing only
when the cost is small (a near coin-flip game) and the payoff is real (the person you
need to catch is very likely on the other side).

### She doesn't need to pass Claire. She needs to draw level.

This is the bit that makes the answer more aggressive than instinct suggests. Because
footytips breaks ties on the **lower** cumulative margin error, and Brigitte's is the
lowest in the cluster:

- P(she wins a final-score tie against **Claire**) = **95.8%**
- against **Thorners** = **~100%** (39 points of cushion)
- against **Jake** = **76.2%** (same 16-point cushion, but Jake's margin guesses are wild,
  so the spread is huge)

So the problem is not "score more than Claire". It is "collect **one** swing against
Claire, then cover". That is a much easier problem, and it is why one well-chosen split
is worth taking and a second one usually is not.

### Which split, then

Two things multiply: how likely the underdog is to win, and how likely the rival is to be
on the favourite. In Finals Week 1:

| Game | Underdog's chance | Claire on the favourite | Product |
|---|---|---|---|
| NZW v DOL | **42.5%** | ~81% | **0.34** |
| CRO v NQL | 33.9% | ~88% | 0.30 (but costs far more) |
| PEN v SYD | 29.4% | ~99% | 0.29 (costs the most) |

The Dolphins are the best differentiation-per-point-given-up on the board. Taking them
costs about **0.15 of an expected point** and buys a **~34%** chance of gaining a full
point on the leader. The other two games are 66%/71% favourites — you give up far too much
for far too little, and two splits in one round is how people fall *further* behind.

### And the biggest decision of the round was not the clever one

Swing in P(1st) from flipping a single tip, others held at their best:

| Game | Swing |
|---|---|
| **PEN v SYD** | **6.5 pts** |
| CRO v NQL | 5.4 pts |
| NZW v DOL | 3.0 pts |

Tipping the Roosters on Sunday was worth **−6.5 percentage points of comp-win chance** —
more than twice the value of the split, and in the opposite direction. That single number
is why the old app's one inviolable rule had to go.

### Why "cover" is a real strategy too

When she is *ahead*, the right play is the opposite: straight favourites, every game,
and make the chasers take the risks. The panel calls this **cover mode** and it is not
laziness — it is the mirror image of the same logic. If you're in front, every game where
you tip the same as your chaser is a game they cannot gain in.

---

## 4. The maths, for anyone who wants it

In the finals the app does not simulate — it **solves**. Nine games, four rounds, one
bracket: small enough to enumerate exactly.

**The bracket** (the real NRL system, not a generic knockout):

```
week 1 (r28)  QF1 = 1v4   QF2 = 2v3   EF1 = 5v8   EF2 = 6v7
week 2 (r29)  SF1 = QF1 loser (hosts) v EF1 winner
              SF2 = QF2 loser (hosts) v EF2 winner
week 3 (r30)  PF1 = QF1 winner (hosts) v SF2 winner
              PF2 = QF2 winner (hosts) v SF1 winner
week 4 (r31)  GF  = PF1 winner v PF2 winner, neutral venue
```

Note the preliminary finals are hosted by the **qualifying-final winners** — *not* "the
higher seed", which is the approximation everyone reaches for and which differs whenever a
top-two side loses its qualifying final and returns through a semi.

**The recursion.** Let the state be `(bracket path, d₀, d₁, d₂)` where `dᵢ` is rival *i*'s
score minus Brigitte's. At the start of round *r*:

```
V(r, path, d) = max over her tip vectors t of
                  Σ over outcomes o  P(o) · Σ over rival gain triples g
                      P(g | o) · V(r+1, path⊕o, d + g − herGain(t,o))

V(after the last round, d) = Π over rivals of  [ dᵢ < 0 ] + [ dᵢ = 0 ] · P(she wins that countback)
```

with `herGain(t,o) = correct tips + 2 if all correct and her perfect round is still
alive`, and the same for each rival.

Four inputs feed it:

1. **Game probabilities.** The current round uses the app's own blended number — Elo +
   injuries + de-vigged market at `oddsW = 0.75` — so the panel and the card can never
   disagree. Future rounds have no odds, so they run on Elo + the learned home edge, with
   no edge at all in the Grand Final. R28's inputs were:

   | Game | Elo | Market | Blend | Expected margin |
   |---|---|---|---|---|
   | NZW v DOL | NZW 51.5% | NZW 59.5% | **NZW 57.5 / DOL 42.5** | NZW by 2.1 |
   | CRO v NQL | CRO 62.9% | CRO 67.1% | **CRO 66.1 / NQL 33.9** | CRO by 4.7 |
   | PEN v SYD | PEN 68.0% | PEN 71.4% | **PEN 70.6 / SYD 29.4** | PEN by 6.1 |

2. **What each rival will tip.** A per-member logistic fitted in the pipeline over the
   whole season: `P(tips home) = sigmoid(a + b·(Elo logit) + loy·(loyalty difference))`.
   The loyalty term is leave-one-out and shrunk, because a member's affinity for a team is
   literally the average of their own picks in that team's games — fed in raw it predicts
   itself perfectly and drives the football coefficient to zero. Fitted values: `b`
   0.31–1.60, `loy` 2.16–5.09, in-sample hit 70–83%. Predicted R28 picks:

   | Game | Claire | Thorners | Jake |
   |---|---|---|---|
   | NZW–DOL | NZW 81% | NZW 58% | NZW 57% |
   | CRO–NQL | CRO 88% | CRO 96% | CRO 69% |
   | PEN–SYD | PEN 99% | PEN 95% | PEN 98% |

3. **That they might play strategically too.** With probability 0.25 a rival plays a
   comp-aware line for a whole round: cover with favourites if level or ahead, otherwise
   take the underdog in the ⌈deficit/2⌉ most winnable games. The mode is *latent and
   per-round*, which is what makes their picks within a round correlated — and correlation
   is what makes one observed pick informative about the others. This number is a
   construction, not something fitted; §7 shows the answer survives it being 0 or 0.5.

4. **The countback.** Modelled as a race on accumulated error: with `Dᵣ` = (their error −
   her error) in round *r*, she keeps a tie iff `currentLead + ΣDᵣ > 0`, priced
   closed-form as a normal from each member's own per-round margin history.

Only the three biggest live threats are carried (a fourth costs ~25× the state space and
won't run in a browser). Rivals are taken highest-score-first among those still
mathematically alive, so truncating can only *overstate* her chances — measured, in 2026,
at **0.61%**. Deltas are clamped into an absorbing band, which is exact rather than
approximate: once a rival is further ahead than everything still available, nothing later
can change the answer.

Cost: **~330 ms** for a Finals Week 1 bracket. The page shows the last good answer
instantly and quietly replaces it when the solve lands, so nobody ever sees it working.

---

## 5. Enter the tips game by game — it's worth about +0.8 points

footytips locks and reveals picks **one game at a time, at each kick-off**. All three
rivals' R28 tips were already in by Saturday morning. Brigitte was the only person who
could still move — and she could watch the others' cards turn over as the weekend went.

Using that is worth **+0.8 pts of win chance** (44.7% → 45.5%), for free:

1. **Before 16:05 Saturday** — enter the **Dolphins**. That's the only tip that has to be
   in.
2. **Before 19:50 Saturday** — now the NZW–DOL result is known *and* everyone's pick in it
   is public. Choose CRO–NQL with that in hand.
3. **Sunday morning** — same again for PEN–SYD.

The contingency table for step 2 (ordered by how likely each branch is):

| Claire | Thorners | Jake | NZW-DOL result | P(branch) | tip CRO | tip NQL | **do** |
|---|---|---|---|---|---|---|---|
| NZW | NZW | NZW | NZW | 15.2% | 32.1% | 28.7% | CRO |
| NZW | NZW | NZW | DOL | 11.2% | 65.1% | 54.3% | CRO |
| NZW | NZW | DOL | NZW | 11.6% | 32.9% | 29.1% | CRO |
| NZW | DOL | NZW | NZW | 11.1% | 34.0% | **35.1%** | **NQL** |
| NZW | NZW | DOL | DOL | 8.6% | 62.8% | 53.1% | CRO |
| NZW | DOL | NZW | DOL | 8.2% | 62.9% | 49.5% | CRO |
| NZW | DOL | DOL | NZW | 8.5% | 34.8% | **35.7%** | **NQL** |
| NZW | DOL | DOL | DOL | 6.3% | 60.7% | 48.1% | CRO |
| DOL | NZW | NZW | NZW | 3.6% | 38.1% | 37.1% | CRO |
| DOL | NZW | NZW | DOL | 2.7% | 47.5% | 47.4% | CRO |
| DOL | NZW | DOL | NZW | 2.8% | 40.1% | 38.5% | CRO |
| DOL | DOL | NZW | NZW | 2.7% | 41.7% | 41.7% | line-ball |
| DOL | NZW | DOL | DOL | 2.1% | 46.8% | 46.4% | CRO |
| DOL | DOL | NZW | DOL | 2.0% | 43.7% | 43.3% | CRO |
| DOL | DOL | DOL | NZW | 2.0% | 43.3% | 42.8% | CRO |
| DOL | DOL | DOL | DOL | 1.5% | 43.1% | 42.4% | CRO |

Read it as: **the Sharks, unless Claire was on the Warriors, the Warriors won, and at
least one of Thorners/Jake was on the Dolphins** — in which case she is a point further
behind Claire but level-or-better with a chaser, and a second split becomes marginally
right. Every branch is worth ≤1.2 pts, so if the plan has to be simple: **just tip the
Sharks.**

> **The app does not do this for her.** The solver commits all of a round's free tips at
> once. Deciding late is a human action, and this table is the crib sheet for it. If the
> app is ever asked to advise "wait until 19:40", that is a real feature and it is not
> built.

---

## 6. The margin game, and Brigitte's habit

Every round, footytips asks for a predicted margin on the round's **first** game, and the
error accumulates all season as the tie-break. Reconstructing what each member actually
typed (the API publishes only the error; the number is recoverable because the sign has to
agree with the side they tipped) turned up something useful:

| Member | Margins entered, R24–R28 | Mean error |
|---|---|---|
| **Brigitte** | 4, 4, 4, 4, 4 | **12.0** |
| Claire | 6, 6, 10, 6, 6 | 13.2 |
| Thorners | 4, 0, 8, 8, 8 | 13.6 |
| Jake | 14, 8, 22, 16, 12 | 15.2 |

**She enters "4" every single week.** It has served her extremely well — the best error in
the group, which is precisely why she holds the countback — but it is a shade under the
mark. On this sample the error-minimising constant is **6** (11.6 vs 12.0), and the
model's median margins for the possible R29 openers are 4–7 points. Moving from 4 to 6 is
worth about 0.4 points of error per round; it lifts the countback against Claire from
95.8% to 96.7% and P(1st) by about **+0.2 pts**. Free money, if a small pile of it.

The app now says so: the margin line under the panel reads *"You've entered 4 in each of
the last 7 rounds — the number above is the one to beat."*

**Recommended R29 calls**, by whichever matchup ends up first on the card:

| Matchup | Call |
|---|---|
| PEN v NQL | Panthers by 7 |
| PEN v CRO | Panthers by 6 |
| NZW v NEW | Warriors by 6 |
| DOL v NEW | Dolphins by 6 |
| SYD v NQL | Roosters by 5 |
| SYD v CRO | Roosters by 4 |

**Should she play the margin safe to protect the lead?** No — there is no such thing. The
countback is a race on *accumulated error*, so the move that protects a 16-point cushion
is simply the most accurate number available, which is the model's median margin. (The
app's advice deliberately sits slightly *below* the mean margin — ×0.85 — because margins
are right-skewed and the median beats the mean for an absolute-error loss.) There is no
variance trade worth making while she is ahead on countback against all three rivals.

---

## 7. Sensitivities — what this survives, and what it doesn't

| Dial | Setting | Best line | P(1st) | Favourites |
|---|---|---|---|---|
| Rival strategic awareness | 0.00 | DOL/CRO/PEN | 45.50% | 44.70% |
| | 0.25 (default) | DOL/CRO/PEN | 44.73% | 41.74% |
| | 0.50 | DOL/CRO/PEN | 45.93% | 40.71% |
| Market weight `oddsW` | 0.00 (pure Elo) | DOL/CRO/PEN | 45.42% | 42.65% |
| | 0.50 | DOL/CRO/PEN | 45.01% | 42.09% |
| | 0.75 (default) | DOL/CRO/PEN | 44.73% | 41.74% |
| | 1.00 (pure market) | DOL/CRO/PEN | 44.40% | 41.36% |
| Tie-breaks | **she always loses them** | **NZW/CRO/PEN** | **31.63%** | 31.63% |
| | model (default) | DOL/CRO/PEN | 44.73% | 41.74% |
| | she always wins them | DOL/CRO/PEN | 45.80% | 42.80% |
| Rival predictability | **×0.0 (coin flips)** | **NZW/CRO/PEN** | **51.08%** | 51.08% |
| | ×0.5 | DOL/CRO/PEN | 44.58% | 43.97% |
| | ×1.0 (as fitted) | DOL/CRO/PEN | 44.73% | 41.74% |
| | ×1.5 | DOL/CRO/PEN | 46.21% | 40.93% |
| Home advantage | 0 pts (the learned value) | DOL/CRO/PEN | 44.17% | 42.32% |
| | 2 pts (app default) | DOL/CRO/PEN | 44.73% | 41.74% |
| | 3 pts | DOL/CRO/PEN | 44.35% | 40.65% |

The recommendation survives every dial except two, and both are worth understanding:

1. **Her entire edge is the countback.** Take it away and P(1st) falls from 44.7% to
   31.6%, and the right play reverts to plain favourites — with no tie-break she has to
   out-score Claire outright, and differentiating stops paying.
2. **The split only pays because the rivals are predictable.** If they were coin flips
   there would be nothing to split *from*, and favourites would be optimal (51.1% — note
   that unpredictable rivals are *good* for her overall, they just remove the edge from
   splitting). At half the fitted predictability the split still wins, but by 0.6 pts.
   This is the assumption the whole thing leans on hardest.

Strategic awareness is **non-monotonic** — 0.25 is her worst setting — because a *moderate*
amount of strategic play puts Thorners and Jake on the Dolphins alongside her (killing the
differentiation), while *a lot* of it makes them bleed expected points on splits that
don't land.

**Other known limits**, in rough order of how much they matter:

1. The rival pick model is fitted on 127 picks from R24–R27, which were mostly lopsided
   games, and the recommendation turns on its behaviour at a near-coin-flip. The affinity
   table also covers the fitting rounds, so the in-sample hit rate is mildly optimistic.
2. The countback treats the four tie-breaks as **independent**. A bad margin guess by her
   hurts against everyone at once, so this slightly overstates P(1st) in tied states. An
   exact dead heat on cumulative margin is treated as impossible; footytips would show a
   shared rank.
3. `STRAT_AWARE = 0.25` is a construction. There is nothing in R24–R27 to fit it on.
4. Injury adjustments for R28 were back-solved from the app's published probabilities;
   rounds 29–31 carry **no injury information at all**, which understates uncertainty in
   the later rounds.
5. Elo is held static through the finals (≤10 points of drift over three weeks, ~1.5% on a
   win probability).
6. Only three rivals are modelled — overstates by ≤0.61% in 2026.

---

## 8. What to re-check at the start of each finals week

A short, ordered checklist. Most of it is confirming the pipeline did its job.

1. **Did the workflow run since the last game finished?** `last_run.json` timestamp, and
   `nrl_data.js` should show the new round with real fixtures (between finals weeks the
   site legitimately shows the *played* week until Zero Tackle posts the next pairings —
   usually within a day; don't invent fixtures).
2. **Is the bracket right?** The app derives it from the ladder. Open the app and check
   the round's matchups against the NRL's own draw. If a game is missing or the pairing is
   wrong, the exact solver quietly falls back to the Monte-Carlo path and the numbers get
   noticeably vaguer — `plan.sim.exact` is the tell.
3. **Re-run the reference solver for the new week.** `python3 reference_finals_solver.py`
   (~4 min) with the week's results and standings, then `node reference/crosscheck.mjs`.
   Expect the page to sit ~2–3 points above the reference uniformly; what matters is that
   they agree on the *best line*.
4. **Re-read the standings and the countback.** Specifically: is Brigitte still ahead on
   `totalMargin` against everyone who can still catch her? If that flips, the whole
   strategy changes character — differentiation stops paying and favourites become right.
   The panel's mini ladder shows the ± countback column.
5. **Check who is mathematically alive.** With fewer games left, rivals drop out fast; the
   app keeps a provably-beaten rival out of the model but *keeps* an out-of-reach leader
   (that asymmetry is deliberate — see GOTCHAS).
6. **The margin game is the round's FIRST game.** Confirm which fixture that is on
   footytips, and enter the number from §6's table (or the panel's advice line) — she must
   enter it before that game kicks off or it scores as maximum error.
7. **Enter tips game by game** where the schedule allows it (§5). In a two-game week the
   value is smaller but non-zero.
8. **Grand Final week is special**: one game, and a correct tip pays **3** (1 + the perfect
   round bonus). Being 1 or 2 behind is survivable; 3 behind needs the countback; 4 behind
   is over. The solver knows this — but it is also the week to sanity-check the answer by
   hand, because there is only one decision in it.
9. **Daylight saving starts Sun 4 Oct 2026 — Grand Final day.** All the cron slots are
   UTC; one extra Sunday slot exists precisely for this. If the pre-game odds refresh
   looks like it fired late that day, that is why.

---

## 9. If you're Brigitte and you just want to know what to do

- Open the app. The Tips screen tells you who to tip.
- A **🎯** on a game means *the tip there is deliberately not the favourite*, because it
  gives you a better chance of winning the comp. The line under it says how much better
  and who is on the other side. It is not a mistake and it is not a hunch.
- The line at the top of the comp panel is the only number that matters: **your chance of
  winning the comp**, and what you'd be on if you just tipped favourites from here.
- If you can, **enter each tip closer to its kick-off** rather than all at once — you get
  to see what everyone else picked in the earlier games first, and that's worth about a
  point of win chance.
- On the round's **first** game, enter the margin the app suggests. You've typed "4" every
  week for two months; it's been good, but 6 is very slightly better, and the margin is
  what wins you a tie — which is the most likely way you win this thing.
