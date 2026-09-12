#!/usr/bin/env python3
# =============================================================================
# reference_finals_solver.py — REFERENCE ONLY. Not part of the pipeline.
#
# This is the standalone Python solver written on 2026-09-12 for Round 28 (NRL
# Finals Week 1) of the 2026 season. The in-page exact finals DP in
# nrl-tipping-guide.html (finalsPlan()/finalsCtx(), see docs/MODEL.md) was
# validated against it: reference/crosscheck.mjs boots the real page in jsdom
# and compares P(Brigitte 1st) for all eight R28 tip vectors against the numbers
# this script printed. They do not agree to the decimal — the rival pick model
# is fitted differently here (one global logistic, no intercept, R24-R27) than
# in cloud_fetch.py (per-member with an intercept, whole season, leave-one-out
# loyalty), and this file hard-codes a 2-point home-ground edge where the page
# uses the learned one. What matched: the best line (DOL/CRO/PEN), the set of
# top-three lines, and "every line containing the Roosters ranks below every
# line without one".
#
# Its constants are FROZEN AT 2026-09-12 (standings after SOU 10-20 NEW, R28
# market prices, the 2026 ladder). It will NOT self-update — do not treat its
# output as current. It is kept so that a future change to the in-page DP can be
# checked against an independent implementation of the same maths.
#
# It also needs the raw footytips round dumps it was written against, which are
# NOT in this repo; without them it falls back to default behavioural
# coefficients. Run it only as documentation of the method.
# =============================================================================

"""
finals_solver.py — EXACT solver for the 2026 NRL finals footytips comp
======================================================================

Objective: maximise P(Brigitte finishes 1st) in the "Family Feud" comp
(footytips comp 1372189 / ladder 381260129), over the remainder of the
2026 NRL finals series.

Everything here is FULL ENUMERATION (no Monte Carlo) except the optional
sanity cross-check at the end, which is a 200k-sample MC of the
recommended policy run against the same generative model.

Run:  python3 finals_solver.py
      python3 finals_solver.py --quick     (skip the MC cross-check)

Structure
---------
  §1  Constants: comp state, ladder, Elo, odds, bracket
  §2  Win-probability model (Elo + HGA + injuries, blended with de-vigged market)
  §3  Bracket engine (real NRL finals bracket, hosting rules)
  §4  Rival pick model  (behavioural fit on R24-R27 + strategic layer)
  §5  Margin tie-break model
  §6  The DP  (backward induction R29 -> R30 -> R31, exact)
  §7  Round 28 layer: all 8 commit-now combos + the adaptive policy
  §8  Sensitivities, diagnostics, MC cross-check, report

Author's notes on every assumption are in the report; anything marked
[ASSUMPTION] is a judgement call, not something read off the data.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
REPORTS = os.path.join(SCRATCH, "reports")
REPO = os.path.join(SCRATCH, "repo")


# =====================================================================
# §1  CONSTANTS — the comp state as at 2026-09-12, after SOU 10-20 NEW
# =====================================================================

# Players we model. Susie is mathematically eliminated and Josh is
# checked separately (see prove_irrelevance()); the DP carries B + 3.
ME = "Brigitte"
RIVALS = ["Claire", "Thorners", "Jake"]

# total score / cumulative margin error, AFTER R28 game 1 (SOU-NEW) was
# scored.  R28's margin game is already played => margin errors for R28
# are already locked into these totals.
STANDINGS = {
    "Claire":    (132, 492),
    "Brigitte":  (131, 476),
    "Thorners":  (130, 515),
    "Jake":      (128, 492),
    "Josh":      (121, 506),
    "Susie":     (112, 541),
}

# 2026 regular-season ladder positions of the eight finalists.
LADDER = {"PEN": 1, "NZW": 2, "DOL": 3, "SYD": 4, "CRO": 5, "SOU": 6, "NEW": 7, "NQL": 8}

# Elo from nrl_learned.js (2026-09-12, 205 games, lowConfidence: false).
ELO = {
    "PEN": 1619.6, "SYD": 1571.4, "NZW": 1649.9, "CRO": 1528.2,
    "DOL": 1639.6, "SOU": 1536.1, "NEW": 1543.4, "NQL": 1493.2,
    "MAN": 1500.5, "CAN": 1460.8, "CBR": 1498.1, "MEL": 1505.8,
    "BRI": 1405.9, "PAR": 1443.6, "WST": 1364.9, "GLD": 1372.8,
    "STI": 1366.2,
}

LOGISTIC_SCALE = 7.0        # pinned in the app (docs/MODEL.md §5)

# Closing market prices for the three live R28 games (decimal odds).
ODDS_R28 = {
    ("NZW", "DOL"): (1.60, 2.35),
    ("CRO", "NQL"): (1.42, 2.90),
    ("PEN", "SYD"): (1.34, 3.35),
}

# Injury / availability adjustment in POINTS on the home margin.
# Back-solved so the Elo+HGA+injury margin reproduces the app's published
# model probabilities for this round (DOL 48%, NQL 37%, SYD 32%).
# e.g. NZW are without Luke Metcalf -> -2.0 pts to the home side.
INJ_R28 = {
    ("NZW", "DOL"): -2.00,
    ("CRO", "NQL"): +0.30,
    ("PEN", "SYD"): +1.34,
}

# footytips team-id -> our Elo short code (built from the raw event feed)
TEAMID = {
    1: "BRI", 2: "CAN", 3: "CBR", 4: "MEL", 5: "NEW", 6: "MAN", 7: "NQL",
    8: "PAR", 9: "PEN", 10: "SYD", 11: "CRO", 12: "STI", 14: "NZW",
    15: "WST", 45: "SOU", 509: "GLD", 1706: "DOL",
}
SHORTCODE = {
    "BRIS": "BRI", "BULL": "CAN", "CANB": "CBR", "MELB": "MEL", "NEWC": "NEW",
    "MANL": "MAN", "NQLD": "NQL", "PARR": "PAR", "PENR": "PEN", "SYDR": "SYD",
    "SHRK": "CRO", "DRAG": "STI", "NZW": "NZW", "WTIG": "WST", "SSYD": "SOU",
    "TITN": "GLD", "DOL": "DOL",
}

# Season-long tipping affinities (times tipped / times that team played),
# from nrl_comp.js.  Used as the loyalty covariate.
# footytips display name -> our short key
NAME = {"Claire with an i": "Claire", "Brigitte": "Brigitte",
        "Thorners69": "Thorners", "Jake": "Jake",
        "Special unit": "Josh", "Susie loo": "Susie"}

AFF = {
    "Claire": {"NEW": 11/24, "NQL": 18/24, "CAN": 10/24, "STI": 8/24, "MEL": 7/24,
               "PAR": 3/24, "NZW": 18/24, "SYD": 12/24, "BRI": 5/24, "PEN": 23/24,
               "CRO": 14/24, "GLD": 2/24, "MAN": 21/24, "CBR": 13/24, "DOL": 17/24,
               "SOU": 13/24, "WST": 9/24},
    "Brigitte": {"NEW": 12/24, "NQL": 15/24, "CAN": 15/23, "STI": 3/24, "MEL": 10/24,
                 "PAR": 4/22, "NZW": 23/24, "SYD": 24/24, "BRI": 5/23, "PEN": 18/22,
                 "CRO": 14/24, "GLD": 1/24, "MAN": 15/24, "CBR": 10/24, "DOL": 16/24,
                 "SOU": 10/24, "WST": 6/24},
    "Thorners": {"NEW": 10/24, "NQL": 9/23, "CAN": 10/24, "STI": 5/24, "MEL": 13/23,
                 "PAR": 6/24, "NZW": 16/24, "SYD": 22/24, "BRI": 9/24, "PEN": 19/23,
                 "CRO": 18/24, "GLD": 6/23, "MAN": 11/23, "CBR": 15/24, "DOL": 13/23,
                 "SOU": 11/24, "WST": 8/24},
    "Jake": {"NEW": 10/22, "NQL": 11/23, "CAN": 12/24, "STI": 7/24, "MEL": 13/24,
             "PAR": 4/24, "NZW": 18/24, "SYD": 18/24, "BRI": 6/24, "PEN": 24/24,
             "CRO": 15/24, "GLD": 4/24, "MAN": 14/24, "CBR": 12/24, "DOL": 15/22,
             "SOU": 12/24, "WST": 7/24},
}


class Params:
    """Everything tunable in one place."""

    _uid = [0]

    def __init__(self, **kw):
        Params._uid[0] += 1
        self.uid = Params._uid[0]
        self.hga_points = 2.0        # home-ground advantage, in points of margin
        self.gf_hga = 0.0            # Grand Final is neutral (Accor)
        self.odds_w = 0.75           # market weight in the blend (app default)
        self.scale = LOGISTIC_SCALE
        self.strat_p = 0.25          # P(a rival plays the strategic layer this round)
        self.tie_edge = 0.0          # pts/round of margin accuracy she gains
        self.tie_mode = "model"      # "model" | "always" (=1.0) | "never" (=0.0)
        self.use_market_future = False   # no odds exist for R29+
        self.beh_a = None            # fitted at runtime
        self.beh_b = None
        for k, v in kw.items():
            setattr(self, k, v)

    def copy(self, **kw):
        p = Params()
        u = p.uid
        p.__dict__.update(self.__dict__)
        p.__dict__.update(kw)
        p.uid = u
        return p


# =====================================================================
# §2  WIN-PROBABILITY MODEL
# =====================================================================

def elo_gap_to_points(diff: float, scale: float) -> float:
    """docs/MODEL.md: eloGapToPoints(diff, scale) = diff * scale * ln(10) / 400."""
    return diff * scale * math.log(10.0) / 400.0


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def devig(o_home: float, o_away: float) -> float:
    """Proportional de-vig of two decimal prices -> fair home probability."""
    ih, ia = 1.0 / o_home, 1.0 / o_away
    return ih / (ih + ia)


def model_p_home(home: str, away: str, P: Params, hga: float | None = None,
                 inj: float = 0.0) -> float:
    """Pure model (Elo + HGA + injuries) probability the home team wins."""
    h = P.hga_points if hga is None else hga
    margin = elo_gap_to_points(ELO[home] - ELO[away], P.scale) + h + inj
    return logistic(margin / P.scale)


def p_home(home: str, away: str, P: Params, hga: float | None = None,
           odds=None, inj: float = 0.0) -> float:
    """Blended probability the home team wins (market-weighted if odds exist)."""
    mp = model_p_home(home, away, P, hga=hga, inj=inj)
    if odds is None:
        return mp
    mk = devig(*odds)
    return (1.0 - P.odds_w) * mp + P.odds_w * mk


def expected_margin(home: str, away: str, P: Params, hga: float | None = None,
                    odds=None, inj: float = 0.0) -> float:
    """Expected (median) home margin in points, consistent with the blended prob."""
    p = p_home(home, away, P, hga=hga, odds=odds, inj=inj)
    p = min(max(p, 1e-6), 1 - 1e-6)
    return P.scale * math.log(p / (1 - p))


# =====================================================================
# §3  BRACKET ENGINE — the real 2026 NRL finals bracket
# =====================================================================
#
# Week 1 (round 28):  QF1 = 1v4  PEN-SYD     [live]
#                     QF2 = 2v3  NZW-DOL     [live]
#                     EF1 = 5v8  CRO-NQL     [live]
#                     EF2 = 6v7  SOU-NEW     -> NEW won 20-10   [DONE]
# Week 2 (round 29):  SF1 = loser QF1 v winner EF1
#                     SF2 = loser QF2 v winner EF2 (= NEW)
#                     HOSTING: the losing qualifying finalist hosts.
# Week 3 (round 30):  PF1 = winner QF1 v winner SF2
#                     PF2 = winner QF2 v winner SF1
#                     HOSTING: the qualifying-final winner hosts.
# Week 4 (round 31):  GF  = winner PF1 v winner PF2, neutral venue.
#
# The three live week-1 games are ordered as footytips lists them
# (chronological): NZW-DOL (Sat 16:05), CRO-NQL (Sat 19:50),
# PEN-SYD (Sun 16:05).

R28_GAMES = [("NZW", "DOL"), ("CRO", "NQL"), ("PEN", "SYD")]
EF2_WINNER = "NEW"


def r29_games(qf1w, qf2w, ef1w):
    """(home, away) for the two semi-finals.  QF loser hosts."""
    qf1l = "SYD" if qf1w == "PEN" else "PEN"
    qf2l = "DOL" if qf2w == "NZW" else "NZW"
    sf1 = (qf1l, ef1w)          # QF1 loser hosts the EF1 winner
    sf2 = (qf2l, EF2_WINNER)    # QF2 loser hosts the EF2 winner (NEW)
    return [sf1, sf2]


def r30_games(qf1w, qf2w, sf1w, sf2w):
    """(home, away) for the two preliminary finals.  QF winner hosts."""
    pf1 = (qf1w, sf2w)
    pf2 = (qf2w, sf1w)
    return [pf1, pf2]


def r31_games(pf1w, pf2w):
    """Grand Final, neutral venue.  Listed higher-ladder team 'home'."""
    a, b = pf1w, pf2w
    if LADDER[b] < LADDER[a]:
        a, b = b, a
    return [(a, b)]


def round_probs(games, P: Params, neutral=False):
    """Blended P(home wins) for each game of a future round (no odds)."""
    hga = P.gf_hga if neutral else P.hga_points
    return [p_home(h, a, P, hga=hga) for (h, a) in games]


# =====================================================================
# §4  RIVAL PICK MODEL
# =====================================================================
#
# Two layers.
#
# (a) Behavioural: P(tips home) = sigma(a*logit(p_home) + b*(affHome-affAway)).
#     a and b are fitted by maximum likelihood on every pick made in
#     rounds 24-27 by all six comp members (190 picks).
#
# (b) Strategic: with probability `strat_p` a rival instead plays a
#     comp-aware line for the whole round — a rival level with the leader
#     covers (= tips favourites), a rival behind takes the underdog in the
#     game(s) where a split hurts the leader most.


def load_history():
    """Return [(round, [(home,away,home_won)], {name: {event: teamcode}})]."""
    out = []
    for rnd in (24, 25, 26, 27):
        fp = os.path.join(REPORTS, f"footytips_r{rnd}_raw.json")
        if not os.path.exists(fp):
            return []
        d = json.load(open(fp))
        games, order = {}, []
        for e in d["events"]:
            c = {x["homeAway"]: x for x in e["competitors"]}
            h, a = SHORTCODE[c["home"]["shortCode"]], SHORTCODE[c["away"]["shortCode"]]
            games[e["eventId"]] = (h, a, c["home"]["score"] > c["away"]["score"])
            order.append(e["eventId"])
        picks = {}
        for res in d["ladder"]["results"]:
            nm = NAME.get(res["user"]["displayName"], res["user"]["displayName"])
            picks[nm] = {t["eventId"]: TEAMID[t["teamId"]] for t in res["tips"]}
        out.append((rnd, order, games, picks))
    return out


def fit_behaviour(P: Params, verbose=True):
    """MLE of (a, b) in P(tip home) = sigma(a*logit(pHome) + b*dAff)."""
    hist = load_history()
    rows = []
    for rnd, order, games, picks in hist:
        for ev in order:
            h, a, _ = games[ev]
            lp = math.log(model_p_home(h, a, P) / (1 - model_p_home(h, a, P)))
            for nm, pk in picks.items():
                if ev not in pk:
                    continue
                aff = AFF.get(nm)
                if aff is None:               # Josh / Susie: no aff table
                    continue
                d = aff.get(h, 0.5) - aff.get(a, 0.5)
                rows.append((lp, d, 1 if pk[ev] == h else 0))
    if not rows:
        P.beh_a, P.beh_b = 2.0, 2.0
        return 0.0, 0

    RIDGE = 0.25   # weak L2 penalty: 96-190 picks, mostly unanimous, so the
                   # unpenalised MLE runs off towards separation.

    def ll(a, b):
        s = 0.0
        for lp, d, y in rows:
            z = a * lp + b * d
            z = max(-30, min(30, z))
            s += (z if y else 0.0) - math.log(1 + math.exp(z))
        return s - RIDGE * (a * a + b * b)

    best = (-1e18, 1.0, 1.0)
    for a in [x / 20 for x in range(0, 121)]:
        for b in [x / 20 for x in range(0, 121)]:
            v = ll(a, b)
            if v > best[0]:
                best = (v, a, b)
    _, A, B = best
    # one refinement pass on a finer grid
    fine = (-1e18, A, B)
    for a in [A + x / 200 for x in range(-12, 13)]:
        for b in [B + x / 200 for x in range(-12, 13)]:
            if a < 0 or b < 0:
                continue
            v = ll(a, b)
            if v > fine[0]:
                fine = (v, a, b)
    _, P.beh_a, P.beh_b = fine
    hits = sum(1 for lp, d, y in rows
               if (logistic(P.beh_a * lp + P.beh_b * d) >= .5) == bool(y))
    if verbose:
        print(f"  behavioural fit on R24-R27: a={P.beh_a:.3f} (form/market) "
              f"b={P.beh_b:.3f} (loyalty), n={len(rows)}, "
              f"in-sample hit={hits/len(rows):.1%}, logLik={fine[0]:.1f}")
    return hits / len(rows), len(rows)


def p_beh_home(rival: str, home: str, away: str, ph: float, P: Params) -> float:
    """Behavioural probability `rival` tips the home team."""
    ph = min(max(ph, 1e-6), 1 - 1e-6)
    lp = math.log(ph / (1 - ph))
    aff = AFF[rival]
    d = aff.get(home, 0.5) - aff.get(away, 0.5)
    return logistic(P.beh_a * lp + P.beh_b * d)


def strategic_picks(rival_deficit: int, games, probs, P: Params):
    """
    Comp-aware line for one round.  Returns a list of 0/1 (1 = tip home).

    A rival level with the leader COVERS: tips every favourite (identical
    to the field, so the gap cannot close against them).
    A rival behind by k takes the underdog in the n = ceil(k/2) games
    (capped at the round size, and only where the underdog is not hopeless)
    where the split has the best chance of landing — i.e. the games with
    the highest underdog probability, which is also where the leader is
    most likely to be on the favourite.
    """
    fav = [1 if p >= 0.5 else 0 for p in probs]
    if rival_deficit <= 0:
        return fav
    n_dev = min(len(games), max(1, (rival_deficit + 1) // 2))
    # underdog probability per game
    dogp = [(1 - p) if p >= 0.5 else p for p in probs]
    order = sorted(range(len(games)), key=lambda i: -dogp[i])
    out = list(fav)
    used = 0
    for i in order:
        if used >= n_dev:
            break
        if dogp[i] < 0.15:          # a hopeless split is worse than useless
            continue
        out[i] = 1 - out[i]
        used += 1
    return out


_PICK_CACHE = {}


def rival_pick_dist(rival: str, games, probs, deficit: int, P: Params):
    """
    Distribution over this rival's pick vector for one round, as a dict
    {tuple_of_0/1 : probability}.  The two layers are mixed with a LATENT
    per-round mode (strategic with prob strat_p), which is what makes a
    rival's picks correlated within a round — that correlation is what
    makes observing one of their picks informative about the others.

    `deficit` is capped at 2*len(games) because that is where the strategic
    layer saturates (it can deviate on at most every game in the round);
    this keeps the state space finite without changing any answer.
    """
    deficit = max(-1, min(deficit, 2 * len(games)))
    ck = (rival, tuple(games), tuple(probs), deficit, P.uid)
    hit = _PICK_CACHE.get(ck)
    if hit is not None:
        return hit
    out = {}
    # behavioural component: independent across games
    per = []
    for (h, a), ph in zip(games, probs):
        pb = p_beh_home(rival, h, a, ph, P)
        per.append(pb)
    for combo in itertools.product([0, 1], repeat=len(games)):
        pr = 1.0
        for c, pb in zip(combo, per):
            pr *= pb if c else (1 - pb)
        out[combo] = out.get(combo, 0.0) + (1 - P.strat_p) * pr
    if P.strat_p > 0:
        sp = tuple(strategic_picks(deficit, games, probs, P))
        out[sp] = out.get(sp, 0.0) + P.strat_p
    _PICK_CACHE[ck] = out
    return out


# =====================================================================
# §5  MARGIN TIE-BREAK
# =====================================================================
#
# rankByMargin: ties on total score go to the LOWER cumulative margin
# error.  R28's margin game (SOU-NEW) has already been played and scored,
# so the current totals are final for R28; three margin games remain
# (the first game of R29, of R30, and the GF).
#
# Per round, D = (rival's error) - (Brigitte's error).  Brigitte keeps the
# tie-break iff current_lead + sum(D over 3 rounds) > 0.
#
# mean(D) is taken from the full-season totals (28 rounds, so a reasonably
# tight estimate); sd(D) from the five rounds we have game-level data for.


def margin_stats():
    """Per-round mean/sd of (rival error - Brigitte error)."""
    per_round = {}
    for rnd in (24, 25, 26, 27, 28):
        fp = os.path.join(REPORTS, f"footytips_r{rnd}_raw.json")
        if not os.path.exists(fp):
            continue
        d = json.load(open(fp))
        per_round[rnd] = {NAME.get(r["user"]["displayName"],
                                   r["user"]["displayName"]): r["round"]["margin"]
                          for r in d["ladder"]["results"]}
    stats = {}
    for r in RIVALS:
        lead = STANDINGS[r][1] - STANDINGS[ME][1]        # >0 => Brigitte ahead
        mean = (STANDINGS[r][1] - STANDINGS[ME][1]) / 28.0
        diffs = [per_round[k][r] - per_round[k][ME] for k in per_round
                 if r in per_round[k] and ME in per_round[k]]
        if len(diffs) >= 2:
            m = sum(diffs) / len(diffs)
            sd = math.sqrt(sum((x - m) ** 2 for x in diffs) / (len(diffs) - 1))
        else:
            sd = 9.0
        sd = max(sd, 5.0)                                 # floor, small sample
        stats[r] = dict(lead=lead, mean=mean, sd=sd, obs=diffs)
    return stats


def margin_habits():
    """
    Reconstruct each member's actual margin PREDICTION for the designated
    margin game of R24-R28.

    footytips only publishes the error, err = |predicted - actual| on the
    signed (home - away) margin of the round's first game.  Two candidates
    solve that; the one whose sign agrees with the member's tip in that game
    is the prediction they entered.  (Where a member did not tip game 1 the
    entry is 0, which is what the feed implies.)
    """
    rows = []
    for rnd in (24, 25, 26, 27, 28):
        fp = os.path.join(REPORTS, f"footytips_r{rnd}_raw.json")
        if not os.path.exists(fp):
            continue
        d = json.load(open(fp))
        e = d["events"][0]
        c = {x["homeAway"]: x for x in e["competitors"]}
        h, a = SHORTCODE[c["home"]["shortCode"]], SHORTCODE[c["away"]["shortCode"]]
        actual = c["home"]["score"] - c["away"]["score"]
        for res in d["ladder"]["results"]:
            nm = NAME.get(res["user"]["displayName"], res["user"]["displayName"])
            err = res["round"]["margin"]
            tip = None
            for t in res["tips"]:
                if t["eventId"] == e["eventId"]:
                    tip = TEAMID[t["teamId"]]
            cands = [actual + err, actual - err]
            if tip is None:
                pred = 0
            else:
                want_home = (tip == h)
                ok = [x for x in cands if (x > 0) == want_home]
                pred = ok[0] if ok else cands[0]
            rows.append((rnd, nm, h, a, actual, err, tip, pred))
    return rows


def tie_probs(P: Params, rounds_left: int = 3, edge: float | None = None):
    """
    P(Brigitte wins the margin countback) against each rival.

    `edge` shifts the per-round mean in her favour (e.g. if she starts
    predicting margins more carefully than they do).
    """
    if edge is None:
        edge = getattr(P, "tie_edge", 0.0)
    st = margin_stats()
    out = {}
    for r in RIVALS:
        if P.tie_mode == "always":
            out[r] = 1.0
            continue
        if P.tie_mode == "never":
            out[r] = 0.0
            continue
        s = st[r]
        mu = s["lead"] + rounds_left * (s["mean"] + edge)
        sig = s["sd"] * math.sqrt(rounds_left)
        out[r] = 0.5 * (1 + math.erf(mu / (sig * math.sqrt(2))))
    return out, st


# =====================================================================
# §6  THE DP — exact backward induction over rounds 29, 30, 31
# =====================================================================
#
# State entering a round: (bracket state, score deltas of each rival
# relative to Brigitte).  Only the deltas matter for who finishes 1st,
# and the leader's identity (needed by the strategic layer) is
# recoverable from the deltas: leader_minus_me = max(0, dC, dT, dJ).
#
# Per round each player's gain is (#correct) + 2 if all correct:
#   2-game round -> gain in {0, 1, 4};  1-game round -> gain in {0, 3}.


class Solver:
    def __init__(self, P: Params):
        self.P = P
        self.tie, self.mstats = tie_probs(P)
        self._v31 = {}
        self._v30 = {}
        self._v29 = {}

    # ---- terminal ----------------------------------------------------
    def terminal(self, deltas):
        """P(Brigitte 1st) given final score deltas (rival - Brigitte)."""
        p = 1.0
        for r, d in zip(RIVALS, deltas):
            if d > 0:
                return 0.0
            if d == 0:
                p *= self.tie[r]
        return p

    # ---- generic one-round expansion ---------------------------------
    def play_round(self, games, deltas, probs, next_fn, swing_after):
        """
        Exactly evaluate one round.  Brigitte picks the tip vector that
        maximises the continuation value; rivals draw from their pick
        model.  Returns (best_value, best_tip_vector).

        `swing_after` = the largest amount a rival's delta can still move
        in her favour / against her AFTER this round.  Used only to clamp
        the successor state into an absorbing band, which is exact.
        """
        n = len(games)
        lo, hi = -(swing_after + 1), swing_after + 1
        lead = max(0, *deltas) if deltas else 0
        dists = [rival_pick_dist(r, games, probs, lead - d, self.P)
                 for r, d in zip(RIVALS, deltas)]
        outcomes = list(itertools.product([0, 1], repeat=n))   # 1 = home wins
        # For each outcome: its probability, and each rival's gain distribution
        pre = []
        for oc in outcomes:
            p_oc = 1.0
            for o, pr in zip(oc, probs):
                p_oc *= pr if o else (1 - pr)
            gd = []
            for dist in dists:
                g = {}
                for combo, pc in dist.items():
                    c = sum(1 for t, o in zip(combo, oc) if t == o)
                    gain = c + (2 if c == n else 0)
                    g[gain] = g.get(gain, 0.0) + pc
                gd.append(sorted(g.items()))
            pre.append((oc, p_oc, gd))

        # continuation value for (outcome, my_gain), computed once
        cache = {}

        def cont(oc, p_oc, gd, my_gain):
            key = (oc, my_gain)
            v = cache.get(key)
            if v is not None:
                return v
            d0, d1, d2 = deltas
            acc = 0.0
            for g0, p0 in gd[0]:
                n0 = min(hi, max(lo, d0 + g0 - my_gain))
                for g1, p1 in gd[1]:
                    n1 = min(hi, max(lo, d1 + g1 - my_gain))
                    p01 = p0 * p1
                    if p01 == 0.0:
                        continue
                    for g2, p2 in gd[2]:
                        n2 = min(hi, max(lo, d2 + g2 - my_gain))
                        acc += p01 * p2 * next_fn(oc, (n0, n1, n2))
            cache[key] = acc
            return acc

        best_v, best_t = -1.0, None
        for mytip in itertools.product([0, 1], repeat=n):
            tot = 0.0
            for oc, p_oc, gd in pre:
                if p_oc <= 0:
                    continue
                my_c = sum(1 for t, o in zip(mytip, oc) if t == o)
                my_gain = my_c + (2 if my_c == n else 0)
                tot += p_oc * cont(oc, p_oc, gd, my_gain)
            if tot > best_v:
                best_v, best_t = tot, mytip
        return best_v, best_t

    # ---- absorbing short-circuit -------------------------------------
    def absorbed(self, deltas, swing):
        """
        swing = largest relative move still available from here on.
        Returns None if undecided, else the exact value.
        """
        undecided = False
        for d in deltas:
            if d > swing:          # rival is ahead beyond recovery
                return 0.0
            if d >= -swing:        # rival can still draw level or pass
                undecided = True
        return None if undecided else 1.0

    # ---- round 31 (Grand Final) --------------------------------------
    def v31(self, pf1w, pf2w, deltas):
        key = (pf1w, pf2w, deltas)
        hit = self._v31.get(key)
        if hit is not None:
            return hit
        a = self.absorbed(deltas, 3)
        if a is not None:
            self._v31[key] = (a, None, None)
            return self._v31[key]
        games = r31_games(pf1w, pf2w)
        probs = round_probs(games, self.P, neutral=True)
        v, t = self.play_round(games, deltas, probs,
                               lambda oc, nd: self.terminal(nd), 0)
        self._v31[key] = (v, t, games)
        return self._v31[key]

    # ---- round 30 (Preliminary finals) -------------------------------
    def v30(self, qf1w, qf2w, sf1w, sf2w, deltas):
        key = (qf1w, qf2w, sf1w, sf2w, deltas)
        hit = self._v30.get(key)
        if hit is not None:
            return hit
        a = self.absorbed(deltas, 7)
        if a is not None:
            self._v30[key] = (a, None, None)
            return self._v30[key]
        games = r30_games(qf1w, qf2w, sf1w, sf2w)
        probs = round_probs(games, self.P)

        def nxt(oc, nd):
            pf1w = games[0][0] if oc[0] else games[0][1]
            pf2w = games[1][0] if oc[1] else games[1][1]
            return self.v31(pf1w, pf2w, nd)[0]

        v, t = self.play_round(games, deltas, probs, nxt, 3)
        self._v30[key] = (v, t, games)
        return self._v30[key]

    # ---- round 29 (Semi finals) --------------------------------------
    def v29(self, qf1w, qf2w, ef1w, deltas):
        key = (qf1w, qf2w, ef1w, deltas)
        hit = self._v29.get(key)
        if hit is not None:
            return hit
        a = self.absorbed(deltas, 11)
        if a is not None:
            self._v29[key] = (a, None, None)
            return self._v29[key]
        games = r29_games(qf1w, qf2w, ef1w)
        probs = round_probs(games, self.P)

        def nxt(oc, nd):
            sf1w = games[0][0] if oc[0] else games[0][1]
            sf2w = games[1][0] if oc[1] else games[1][1]
            return self.v30(qf1w, qf2w, sf1w, sf2w, nd)[0]

        v, t = self.play_round(games, deltas, probs, nxt, 7)
        self._v29[key] = (v, t, games)
        return self._v29[key]


# =====================================================================
# §7  ROUND 28 — the decision in front of her right now
# =====================================================================
#
# Three games left this round.  Nobody in the top four can get the R28
# perfect-round bonus (all four tipped SOU in game 1 and lost), so R28
# gains are simply 0-3 for B/C/T/J.
#
# Two decision structures:
#   (a) COMMIT NOW  — she locks all three tips before the 16:05 kickoff.
#                     Enumerate all 8 combinations.
#   (b) ADAPTIVE    — she locks NZW-DOL now, then decides CRO-NQL after
#                     the 16:05 game (whose result AND everyone's picks
#                     for it are then public), and PEN-SYD on Sunday
#                     knowing both Saturday results and both sets of
#                     picks.  Rivals CANNOT do this: their tips for all
#                     three games are already in.  This is free
#                     information and it is worth something.


def r28_setup(P: Params):
    games = R28_GAMES
    probs = [p_home(h, a, P, odds=ODDS_R28[(h, a)], inj=INJ_R28[(h, a)])
             for (h, a) in games]
    return games, probs


def r28_commit_now(S: Solver, verbose=False):
    """P(1st) for each of the 8 tip combinations, assuming optimal play later."""
    P = S.P
    games, probs = r28_setup(P)
    base = {r: STANDINGS[r][0] - STANDINGS[ME][0] for r in RIVALS}
    d0 = tuple(base[r] for r in RIVALS)
    lead = max(0, *d0)
    dists = [rival_pick_dist(r, games, probs, lead - base[r], P) for r in RIVALS]

    results = {}
    for mytip in itertools.product([0, 1], repeat=3):
        tot = 0.0
        for oc in itertools.product([0, 1], repeat=3):
            p_oc = 1.0
            for o, pr in zip(oc, probs):
                p_oc *= pr if o else (1 - pr)
            my_gain = sum(1 for t, o in zip(mytip, oc) if t == o)  # no bonus possible
            qf2w = "NZW" if oc[0] else "DOL"
            ef1w = "CRO" if oc[1] else "NQL"
            qf1w = "PEN" if oc[2] else "SYD"
            gd = []
            for dist in dists:
                g = {}
                for combo, pc in dist.items():
                    c = sum(1 for t, o in zip(combo, oc) if t == o)
                    g[c] = g.get(c, 0.0) + pc
                gd.append(g)
            acc = 0.0
            for g0, p0 in gd[0].items():
                for g1, p1 in gd[1].items():
                    for g2, p2 in gd[2].items():
                        nd = (d0[0] + g0 - my_gain,
                              d0[1] + g1 - my_gain,
                              d0[2] + g2 - my_gain)
                        acc += p0 * p1 * p2 * S.v29(qf1w, qf2w, ef1w, nd)[0]
            tot += p_oc * acc
        results[mytip] = tot
    return results, games, probs


def r28_adaptive(S: Solver):
    """
    Value of the adaptive policy: decide game k knowing the results and
    everyone's picks for games 1..k-1.

    Implemented by full enumeration of the atom space
        (rival mode + rival picks) x (game outcomes)
    and backward induction over the observation history.
    """
    P = S.P
    games, probs = r28_setup(P)
    base = {r: STANDINGS[r][0] - STANDINGS[ME][0] for r in RIVALS}
    d0 = tuple(base[r] for r in RIVALS)
    lead = max(0, *d0)
    dists = [rival_pick_dist(r, games, probs, lead - base[r], P) for r in RIVALS]

    # atoms: (picks of C,T,J) x outcome, with probability
    atoms = []
    for pc in dists[0]:
        for pt in dists[1]:
            for pj in dists[2]:
                w = dists[0][pc] * dists[1][pt] * dists[2][pj]
                if w <= 0:
                    continue
                for oc in itertools.product([0, 1], repeat=3):
                    po = 1.0
                    for o, pr in zip(oc, probs):
                        po *= pr if o else (1 - pr)
                    atoms.append((w * po, (pc, pt, pj), oc))

    def leaf_value(picks, oc, mytips):
        my_gain = sum(1 for t, o in zip(mytips, oc) if t == o)
        nd = []
        for i, r in enumerate(RIVALS):
            c = sum(1 for t, o in zip(picks[i], oc) if t == o)
            nd.append(d0[i] + c - my_gain)
        qf2w = "NZW" if oc[0] else "DOL"
        ef1w = "CRO" if oc[1] else "NQL"
        qf1w = "PEN" if oc[2] else "SYD"
        return S.v29(qf1w, qf2w, ef1w, tuple(nd))[0]

    # stage 3: history = (picks g1,g2 of all rivals; outcomes g1,g2) + my g1,g2
    def solve(stage, subset, mytips):
        """
        Expected value (weighted, NOT normalised) over `subset`, given that
        games 0..stage-1 have been observed and tipped as `mytips`.
        She must commit her tip for game `stage` BEFORE seeing it.
        """
        if stage == 3:
            return sum(w * leaf_value(pk, oc, mytips) for (w, pk, oc) in subset)
        # what becomes public once game `stage` kicks off / finishes
        groups = {}
        for a in subset:
            _, pk, oc = a
            obs = (tuple(pk[i][stage] for i in range(3)), oc[stage])
            groups.setdefault(obs, []).append(a)
        best = -1.0
        for t in (0, 1):
            v = sum(solve(stage + 1, g, mytips + (t,)) for g in groups.values())
            best = max(best, v)
        return best

    def policy_stage1(t0):
        """Best CRO-NQL tip for each thing she could see after game 1."""
        groups = {}
        for a in atoms:
            _, pk, oc = a
            groups.setdefault((tuple(pk[i][0] for i in range(3)), oc[0]), []).append(a)
        rows = []
        for obs, g in sorted(groups.items()):
            w = sum(x[0] for x in g)
            vals = []
            for t in (0, 1):
                sub = {}
                for a in g:
                    _, pk, oc = a
                    sub.setdefault((tuple(pk[i][1] for i in range(3)), oc[1]), []).append(a)
                vals.append(sum(solve(2, gg, (t0, t)) for gg in sub.values()))
            rows.append((obs, w, vals[1] / w, vals[0] / w))   # (home-tip, away-tip)
        return rows

    best_v = solve(0, atoms, ())
    # recover her opening tip
    best_t0 = None
    for t0 in (0, 1):
        groups = {}
        for a in atoms:
            _, pk, oc = a
            groups.setdefault((tuple(pk[i][0] for i in range(3)), oc[0]), []).append(a)
        v = sum(solve(1, g, (t0,)) for g in groups.values())
        if abs(v - best_v) < 1e-12:
            best_t0 = t0
            break
    return best_v, best_t0, atoms, policy_stage1


# =====================================================================
# §8  DIAGNOSTICS, SENSITIVITY, MC CROSS-CHECK
# =====================================================================

def prove_irrelevance():
    """One line each for Josh and Susie."""
    # remaining points available to anyone still perfect in R28:
    #   R28: 3 games (+2 bonus if all 4 correct)  = 5
    #   R29: 2 games +2 = 4 ; R30: 2 +2 = 4 ; R31: 1 +2 = 3
    max_r28_alive = 5     # Josh got game 1 right, bonus still live
    max_rest = 4 + 4 + 3
    josh_max = STANDINGS["Josh"][0] + max_r28_alive + max_rest
    susie_max = STANDINGS["Susie"][0] + max_r28_alive + max_rest
    b_floor = STANDINGS[ME][0]
    lines = [
        f"Susie: 112 + 16 (every remaining tip AND every bonus) = {susie_max} "
        f"< Brigitte's floor of {b_floor}  ->  mathematically eliminated.",
        f"Josh:  121 + 16 = {josh_max} >= {b_floor}, so NOT strictly eliminated: he "
        f"needs a literal 9-from-9 with all three bonuses AND Brigitte to win "
        f"<= {josh_max - b_floor} of the 14 points still on her table.",
    ]
    return lines, josh_max


def josh_exact(S: Solver, mytips):
    """
    EXACT P(Josh finishes at or above Brigitte), by enumerating all 256
    remaining result paths.

    Josh can only reach her by winning every remaining game AND every bonus
    (121 + 16 = 137).  His tips are deterministic: the Roosters whenever the
    Roosters play, the favourite otherwise.  On any path where he is perfect,
    every result is pinned, so Brigitte's score on that path is determined by
    her own policy (her R28 tips `mytips`, the DP's tips thereafter).
    """
    P = S.P
    games, probs = r28_setup(P)

    def josh_tip(h, a, pr):
        if h == "SYD":
            return 1
        if a == "SYD":
            return 0
        return 1 if pr >= .5 else 0

    total = 0.0
    d0 = tuple(STANDINGS[r][0] - STANDINGS[ME][0] for r in RIVALS)
    for oc28 in itertools.product([0, 1], repeat=3):
        p28 = 1.0
        for o, pr in zip(oc28, probs):
            p28 *= pr if o else (1 - pr)
        if any(josh_tip(g[0], g[1], pr) != o
               for g, pr, o in zip(games, probs, oc28)):
            continue                                   # Josh already dead
        my28 = sum(1 for t, o in zip(mytips, oc28) if t == o)
        b = STANDINGS[ME][0] + my28
        j = STANDINGS["Josh"][0] + 3 + 2
        qf2w = "NZW" if oc28[0] else "DOL"
        ef1w = "CRO" if oc28[1] else "NQL"
        qf1w = "PEN" if oc28[2] else "SYD"
        nd = tuple(d0[i] - my28 for i in range(3))      # rivals' gains irrelevant here
        for oc29 in itertools.product([0, 1], repeat=2):
            g29 = r29_games(qf1w, qf2w, ef1w)
            pr29 = round_probs(g29, P)
            p29 = 1.0
            for o, q in zip(oc29, pr29):
                p29 *= q if o else (1 - q)
            if any(josh_tip(g[0], g[1], q) != o for g, q, o in zip(g29, pr29, oc29)):
                continue
            tip29 = S.v29(qf1w, qf2w, ef1w, nd)[1] or \
                tuple(1 if q >= .5 else 0 for q in pr29)
            c = sum(1 for t, o in zip(tip29, oc29) if t == o)
            b29 = b + c + (2 if c == 2 else 0)
            j29 = j + 4
            sf1w = g29[0][0] if oc29[0] else g29[0][1]
            sf2w = g29[1][0] if oc29[1] else g29[1][1]
            for oc30 in itertools.product([0, 1], repeat=2):
                g30 = r30_games(qf1w, qf2w, sf1w, sf2w)
                pr30 = round_probs(g30, P)
                p30 = 1.0
                for o, q in zip(oc30, pr30):
                    p30 *= q if o else (1 - q)
                if any(josh_tip(g[0], g[1], q) != o
                       for g, q, o in zip(g30, pr30, oc30)):
                    continue
                tip30 = tuple(1 if q >= .5 else 0 for q in pr30)
                c = sum(1 for t, o in zip(tip30, oc30) if t == o)
                b30 = b29 + c + (2 if c == 2 else 0)
                j30 = j29 + 4
                pf1w = g30[0][0] if oc30[0] else g30[0][1]
                pf2w = g30[1][0] if oc30[1] else g30[1][1]
                g31 = r31_games(pf1w, pf2w)
                pr31 = round_probs(g31, P, neutral=True)
                for oc31 in (0, 1):
                    p31 = pr31[0] if oc31 else 1 - pr31[0]
                    if josh_tip(g31[0][0], g31[0][1], pr31[0]) != oc31:
                        continue
                    tip31 = 1 if pr31[0] >= .5 else 0
                    b31 = b30 + (3 if tip31 == oc31 else 0)
                    j31 = j30 + 3
                    if j31 >= b31:
                        total += p28 * p29 * p30 * p31
    return total


def mc_check(S: Solver, mytips, n=200_000, seed=20260912):
    """
    Monte-Carlo cross-check of the DP on the recommended R28 policy.
    Future rounds are played with the DP's own optimal policy, so this is a
    genuine check of the enumeration arithmetic and the tie-break wiring.
    """
    rng = random.Random(seed)
    P = S.P
    games, probs = r28_setup(P)
    base = {r: STANDINGS[r][0] - STANDINGS[ME][0] for r in RIVALS}
    d0 = [base[r] for r in RIVALS]
    lead = max(0, *d0)
    dists = [rival_pick_dist(r, games, probs, lead - base[r], P) for r in RIVALS]
    dl = [(list(d.keys()), list(d.values())) for d in dists]

    def draw(dist):
        keys, ws = dist
        return rng.choices(keys, weights=ws, k=1)[0]

    wins = 0.0
    for _ in range(n):
        deltas = list(d0)
        oc = tuple(1 if rng.random() < pr else 0 for pr in probs)
        my = sum(1 for t, o in zip(mytips, oc) if t == o)
        for i, dist in enumerate(dl):
            pk = draw(dist)
            c = sum(1 for t, o in zip(pk, oc) if t == o)
            deltas[i] += c - my
        qf2w = "NZW" if oc[0] else "DOL"
        ef1w = "CRO" if oc[1] else "NQL"
        qf1w = "PEN" if oc[2] else "SYD"

        # round 29
        for stage in (29, 30, 31):
            if stage == 29:
                g = r29_games(qf1w, qf2w, ef1w)
                pr_ = round_probs(g, P)
                _, tip, _ = S.v29(qf1w, qf2w, ef1w, tuple(deltas))
            elif stage == 30:
                g = r30_games(qf1w, qf2w, sf1w, sf2w)
                pr_ = round_probs(g, P)
                _, tip, _ = S.v30(qf1w, qf2w, sf1w, sf2w, tuple(deltas))
            else:
                g = r31_games(pf1w, pf2w)
                pr_ = round_probs(g, P, neutral=True)
                _, tip, _ = S.v31(pf1w, pf2w, tuple(deltas))
            if tip is None:            # absorbing state: any tip, value is fixed
                tip = tuple(1 if q >= .5 else 0 for q in pr_)
            n_g = len(g)
            ld = max(0, *deltas) if deltas else 0
            rds = [rival_pick_dist(r, g, pr_, ld - d, P)
                   for r, d in zip(RIVALS, deltas)]
            oc2 = tuple(1 if rng.random() < q else 0 for q in pr_)
            c = sum(1 for t, o in zip(tip, oc2) if t == o)
            mygain = c + (2 if c == n_g else 0)
            for i, dd in enumerate(rds):
                pk = rng.choices(list(dd.keys()), weights=list(dd.values()), k=1)[0]
                cc = sum(1 for t, o in zip(pk, oc2) if t == o)
                deltas[i] += cc + (2 if cc == n_g else 0) - mygain
            if stage == 29:
                sf1w = g[0][0] if oc2[0] else g[0][1]
                sf2w = g[1][0] if oc2[1] else g[1][1]
            elif stage == 30:
                pf1w = g[0][0] if oc2[0] else g[0][1]
                pf2w = g[1][0] if oc2[1] else g[1][1]
        wins += S.terminal(tuple(deltas))
    return wins / n


# =====================================================================
#  REPORT
# =====================================================================

def name_tip(game, t):
    return game[0] if t else game[1]


def fmt_combo(games, combo):
    return " / ".join(name_tip(g, t) for g, t in zip(games, combo))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the MC cross-check")
    ap.add_argument("--mc", type=int, default=200_000)
    args = ap.parse_args()

    P = Params()
    print("=" * 78)
    print("NRL 2026 FINALS — footytips comp solver (exact enumeration)")
    print("Objective: maximise P(Brigitte finishes 1st).  Date 2026-09-12.")
    print("=" * 78)

    print("\n[1] Field")
    for ln in prove_irrelevance()[0]:
        print("  " + ln)
    _josh_slot = []

    print("\n[2] Rival pick model")
    fit_behaviour(P)

    print("\n[3] Win probabilities, remaining R28 games "
          f"(oddsW={P.odds_w}, hga={P.hga_points}pts, scale={P.scale})")
    games, probs = r28_setup(P)
    for (h, a), pr in zip(games, probs):
        mk = devig(*ODDS_R28[(h, a)])
        mp = model_p_home(h, a, P, inj=INJ_R28[(h, a)])
        print(f"  {h:>3} v {a:<3}  model {mp:5.1%} | market {mk:5.1%} | "
              f"blend {pr:5.1%}  (so {a} {1-pr:.1%})  "
              f"exp margin {h} by {expected_margin(h,a,P,odds=ODDS_R28[(h,a)],inj=INJ_R28[(h,a)]):.1f}")

    print("\n[3b] Predicted rival picks for the three remaining games")
    base_ = {r: STANDINGS[r][0] - STANDINGS[ME][0] for r in RIVALS}
    lead_ = max(0, *base_.values())
    print(f"      {'game':>9} " + " ".join(f"{r:>10}" for r in RIVALS))
    dists_ = [rival_pick_dist(r, games, probs, lead_ - base_[r], P) for r in RIVALS]
    for gi, (h, a) in enumerate(games):
        cells = []
        for d in dists_:
            ph_ = sum(w for c, w in d.items() if c[gi] == 1)
            cells.append(f"{h} {ph_:4.0%}" if ph_ >= .5 else f"{a} {1-ph_:4.0%}")
        print(f"      {h+'-'+a:>9} " + " ".join(f"{c:>10}" for c in cells))

    print("\n[4] Margin tie-break (rankByMargin: lower cumulative error wins)")
    tie, st = tie_probs(P)
    print("  NOTE: R28's margin game (SOU-NEW) is already played and scored —")
    print("        her R28 margin error of 14 is locked in.  Three margin games")
    print("        remain: game 1 of R29, game 1 of R30, and the Grand Final.")
    for r in RIVALS:
        s = st[r]
        print(f"  vs {r:<9} lead {s['lead']:+4d} pts of error, per-round diff "
              f"mean {s['mean']:+.2f} sd {s['sd']:.1f} (obs {s['obs']}) "
              f"-> P(Brigitte wins countback) = {tie[r]:.1%}")

    S = Solver(P)

    print("\n[5] All 8 commit-now combinations for the three remaining R28 games")
    res, games, probs = r28_commit_now(S)
    order = sorted(res.items(), key=lambda kv: -kv[1])
    fav = tuple(1 if p >= .5 else 0 for p in probs)
    print(f"  {'NZW-DOL':>8} {'CRO-NQL':>8} {'PEN-SYD':>8}   P(1st)     vs best")
    best = order[0][1]
    for combo, v in order:
        tag = []
        if combo == fav:
            tag.append("all favourites")
        if combo[2] == 0:
            tag.append("SYD (loyalty)")
        print(f"  {name_tip(games[0],combo[0]):>8} {name_tip(games[1],combo[1]):>8} "
              f"{name_tip(games[2],combo[2]):>8}   {v:7.3%}   {v-best:+7.3%}"
              f"   {', '.join(tag)}")

    print("\n[6] Which game matters most (swing in P(1st) from flipping just that game,")
    print("    holding the other two at their optimum)")
    bestc = order[0][0]
    for i, g in enumerate(games):
        alt = list(bestc)
        alt[i] = 1 - alt[i]
        sw = res[bestc] - res[tuple(alt)]
        print(f"  {g[0]}-{g[1]}: {sw:+.3%}")

    print("\n[7] Value of waiting (she can decide each game after seeing the")
    print("    previous games' results AND everyone's picks; rivals cannot)")
    av, t0, _, pol1 = r28_adaptive(S)
    print(f"  commit-now optimum      : {best:.3%}")
    print(f"  adaptive (decide late)  : {av:.3%}   (+{av-best:.3%})")
    print(f"  first tip under adaptive: {name_tip(games[0], t0)}")
    print("\n    Contingency table for the 19:50 game (CRO-NQL), given what the")
    print("    16:05 game reveals (rivals' NZW-DOL picks become public at kickoff):")
    print(f"      {'C':>4} {'T':>4} {'J':>4} | {'result':>6} | {'P(obs)':>7} | "
          f"{'tip CRO':>8} {'tip NQL':>8} | best")
    for (pk, oc), w, v_home, v_away in pol1(t0):
        nm = [name_tip(games[0], x) for x in pk]
        print(f"      {nm[0]:>4} {nm[1]:>4} {nm[2]:>4} | "
              f"{name_tip(games[0], oc):>6} | {w:7.3%} | "
              f"{v_home:8.2%} {v_away:8.2%} | "
              f"{'CRO' if v_home >= v_away else 'NQL'}")

    print("\n[8] Sensitivities")
    print("  (a) rival strategic-awareness probability")
    for s in (0.0, 0.25, 0.5):
        Q = P.copy(strat_p=s)
        SQ = Solver(Q)
        r2, g2, _ = r28_commit_now(SQ)
        o2 = sorted(r2.items(), key=lambda kv: -kv[1])
        print(f"    strat_p={s:<5} best = {fmt_combo(g2,o2[0][0]):<24} "
              f"{o2[0][1]:7.3%}   (favourites {r2[fav]:7.3%})")
    print("  (b) market weight oddsW")
    for w in (0.0, 0.5, 0.75, 1.0):
        Q = P.copy(odds_w=w)
        SQ = Solver(Q)
        r2, g2, _ = r28_commit_now(SQ)
        o2 = sorted(r2.items(), key=lambda kv: -kv[1])
        print(f"    oddsW={w:<5}   best = {fmt_combo(g2,o2[0][0]):<24} "
              f"{o2[0][1]:7.3%}   (favourites {r2[fav]:7.3%})")
    print("  (c) tie-break resolution")
    for m in ("never", "model", "always"):
        Q = P.copy(tie_mode=m)
        SQ = Solver(Q)
        r2, g2, _ = r28_commit_now(SQ)
        o2 = sorted(r2.items(), key=lambda kv: -kv[1])
        print(f"    ties={m:<7} best = {fmt_combo(g2,o2[0][0]):<24} "
              f"{o2[0][1]:7.3%}   (favourites {r2[fav]:7.3%})")
    print("  (d) rival predictability (scaling the fitted behavioural coefficients;")
    print("      1.0 = as fitted, 0.0 = rivals are coin flips)")
    for k in (0.0, 0.5, 1.0, 1.5):
        Q = P.copy(beh_a=P.beh_a * k, beh_b=P.beh_b * k)
        SQ = Solver(Q)
        r2, g2, _ = r28_commit_now(SQ)
        o2 = sorted(r2.items(), key=lambda kv: -kv[1])
        print(f"    scale={k:<5}   best = {fmt_combo(g2,o2[0][0]):<24} "
              f"{o2[0][1]:7.3%}   (favourites {r2[fav]:7.3%})")
    print("  (e) home-ground advantage, points")
    for h in (0.0, 2.0, 3.0):
        Q = P.copy(hga_points=h)
        SQ = Solver(Q)
        r2, g2, _ = r28_commit_now(SQ)
        o2 = sorted(r2.items(), key=lambda kv: -kv[1])
        print(f"    hga={h:<5}     best = {fmt_combo(g2,o2[0][0]):<24} "
              f"{o2[0][1]:7.3%}   (favourites {r2[fav]:7.3%})")

    print("\n[9] Margin prediction")
    print("  R28 is DONE (her SOU +4 gave an error of 14; she gained 2 on Claire).")
    print("  Next margin game = game 1 of R29.  Recommended calls, by matchup:")
    seen = set()
    for qf1w in ("PEN", "SYD"):
        for qf2w in ("NZW", "DOL"):
            for ef1w in ("CRO", "NQL"):
                for g in r29_games(qf1w, qf2w, ef1w):
                    if g in seen:
                        continue
                    seen.add(g)
                    m = expected_margin(g[0], g[1], P)
                    side = g[0] if m >= 0 else g[1]
                    print(f"    {g[0]:>3} v {g[1]:<3}  -> {side} by {abs(m):.0f}")
    hab = margin_habits()
    print("  What each member actually enters (reconstructed from the error):")
    for nm in [ME] + RIVALS:
        mine = [r for r in hab if r[1] == nm]
        preds = [abs(r[7]) for r in mine]
        errs = [r[5] for r in mine]
        print(f"    {nm:<9} |margin| entered R24-R28: {preds}  "
              f"mean err {sum(errs)/len(errs):.1f}")
    mine = [r for r in hab if r[1] == ME]
    print("  Would a different habitual number have been better for her?")
    for cand in (4, 5, 6, 7, 8, 10, 12):
        tot = 0
        for (_, _, _, _, actual, _, _, pred) in mine:
            sgn = 1 if pred >= 0 else -1
            tot += abs(sgn * cand - actual)
        print(f"    always entering {cand:>2} (same side she tipped): "
              f"mean error {tot/len(mine):.1f}")

    st2 = margin_stats()
    for r in ("Claire", "Jake"):
        base_tie = tie[r]
        e_tie, _ = tie_probs(P, edge=0.4)
        print(f"    switching her habitual 4 to 6 (worth ~0.4 pts/round here): "
              f"countback vs {r} {base_tie:.1%} -> {e_tie[r]:.1%}")
    Q = P.copy(tie_edge=0.4)
    SQ = Solver(Q)
    r2, g2, _ = r28_commit_now(SQ)
    print(f"    ... which lifts P(1st) from {best:.2%} to "
          f"{max(r2.values()):.2%} (+{max(r2.values())-best:.2%}).")

    print("\n[10] Sanity checks")
    tot = 0.0
    for oc in itertools.product([0, 1], repeat=3):
        p = 1.0
        for o, pr in zip(oc, probs):
            p *= pr if o else (1 - pr)
        tot += p
    print(f"  R28 outcome probabilities sum to {tot:.12f}")
    d = rival_pick_dist("Claire", games, probs, 0, P)
    print(f"  Claire's R28 pick distribution sums to {sum(d.values()):.12f}")
    print(f"  P(1st) over all 8 combos in [0,1]: "
          f"{min(res.values()):.4%} .. {max(res.values()):.4%}")
    if not args.quick:
        mc = mc_check(S, bestc, n=args.mc)
        print(f"  MC cross-check of {fmt_combo(games,bestc)} "
              f"({args.mc:,} samples): {mc:.3%}  vs DP {best:.3%}  "
              f"(diff {mc-best:+.3%}, 2se ~ {2*math.sqrt(best*(1-best)/args.mc):.3%})")

    jp = josh_exact(S, bestc)
    print(f"\n  [1b] EXACT P(Josh reaches Brigitte) on the recommended line: "
          f"{jp:.5%}  -> excluding him from the DP costs at most that.")

    print("\n[11] RECOMMENDATION")
    print(f"  Tip: {fmt_combo(games, bestc)}")
    print(f"  P(1st) following it            : {best:.2%}")
    print(f"  P(1st) tipping all favourites  : {res[fav]:.2%}")
    syd = (bestc[0], bestc[1], 0)
    print(f"  P(1st) if she tips SYD instead : {res[syd]:.2%}  "
          f"(Roosters cost {res[bestc]-res[syd]:+.2%})")
    print("=" * 78)


if __name__ == "__main__":
    main()
