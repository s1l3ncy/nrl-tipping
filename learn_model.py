#!/usr/bin/env python3
"""
learn_model.py — Dev A learning-loop fitting engine for the NRL Tipping App.

PURE, NETWORK-FREE. Reads the append-only results memory that parse_nrl.py
maintains in nrl_learned.js (`results: [{round,home,away,hs,as}, ...]`),
re-fits the model's parameters from scratch every run, and rewrites
nrl_learned.js with fresh params/Elo/backtest, appending one history entry —
never deleting `results` or prior `history` entries.

WHAT GETS FITTED
-----------------
- params.homeAdv       = observed mean home winning margin (mean(hs-as))
                         across the whole memory.
- elo                  = current per-team Elo rating (short -> rating),
                         produced by replaying EVERY result chronologically
                         (by round, then discovery order), starting every
                         team at 1500, with a home-ground bump (eloHGA) and
                         a margin-of-victory multiplier on the K-factor
                         (eloK). Standard Elo probability base of 400 is
                         used for the rating UPDATE step, matching the
                         "ELO_PROB_BASE=400" convention the front-end
                         (nrl-tipping-guide.html) already assumes.
- eloK / eloHGA        = chosen by a small, deterministic grid search that
                         MINIMISES walk-forward log-loss over the memory:
                         each game is predicted using ratings as they stood
                         BEFORE that game (no leakage from its own result).
                         `logisticScale` is PINNED at 7 (2026-08-04, audit
                         A2): in this parameterisation the scale cancels
                         exactly for the Elo term, so the walk-forward loss
                         depends on it only through homeAdv/scale and the
                         old grid search drove it to the grid edge — an
                         accident that then governed how hard injuries and
                         HGA hit the logit at inference. It cannot be
                         learned from win/loss outcomes here, so it is a
                         constant. It is still PUBLISHED in params (the
                         front-end and freeze read it). `logisticScale` is
                         the points-space scale the front-end's own
                         logistic() curve uses to turn an Elo gap
                         (converted to an equivalent points margin via
                         eloGapToPoints, mirrored below) plus homeAdv into
                         a win probability — see nrl-tipping-guide.html
                         predict()/eloGapToPoints() for the exact formula
                         this script reproduces so the backtest numbers
                         mean what the live app will actually show.
- oddsWeight           = grid-searched in [0,1] to minimise Brier score
                         blending the model probability with the de-vigged
                         market probability, IF an optional --odds-history
                         file is supplied. Otherwise defaults to 0.5 and is
                         explicitly flagged as not-yet-learned in the
                         generated file's header comment.

GUARDRAILS
----------
If the memory holds fewer than ~30 games, `lowConfidence` is set True and
the emitted eloK/eloHGA/logisticScale are the fixed conservative defaults
(NOT the grid-search result) — a handful of games is nowhere near enough to
trust a fitted K-factor or scale, and the front-end already refuses to use
ANY of these learned params while lowConfidence is true (see
nrl-tipping-guide.html's `learnedActive` check), but we still want an
honest, non-degenerate backtest number to chart the accuracy-over-time
trend from day one. `homeAdv` is still the real observed mean margin (a
simple statistic, not a fragile multi-parameter fit) even when
lowConfidence.

Usage:
    python3 learn_model.py [--learned nrl_learned.js] [--odds-history FILE]
                            [--updated YYYY-MM-DD]

Requires nrl_learned.js to already exist with a `results` list (parse_nrl.py
creates/appends to it; see also the seeded starter file). Exits non-zero
without writing anything if nrl_learned.js is missing or unparseable.
"""

import argparse
import datetime
import math
import sys
from pathlib import Path

from parse_nrl import TEAMS, load_learned, emit_learned_js, find_short

# ---------------------------------------------------------------------------
# Fixed constants / grids
# ---------------------------------------------------------------------------
ELO_PROB_BASE = 400.0  # matches ELO_PROB_BASE in nrl-tipping-guide.html
LOW_CONFIDENCE_THRESHOLD = 30

DEFAULT_ELO_K = 20
DEFAULT_ELO_HGA = 50
# logisticScale is a POINTS-space value: it both maps an Elo gap to an
# equivalent points margin (eloGapToPoints) AND is the divisor in logistic().
# It MUST match nrl-tipping-guide.html's convention (fallback 7, sane range
# 0-50 in validate_learned.py). A pure-Elo (~400) value here would crush the
# points-space homeAdv/injury adjustments to near-zero — keep it in points.
DEFAULT_LOGISTIC_SCALE = 7.0
DEFAULT_ODDS_WEIGHT = 0.5

# Small, deterministic grids (kept short so the search is fast and repeatable).
# logisticScale is NOT in the search (audit A2, 2026-08-04): it is statistically
# unidentifiable in this parameterisation and is pinned at DEFAULT_LOGISTIC_SCALE.
ELOK_GRID = [10, 16, 24, 32, 40]
ELOHGA_GRID = [0, 20, 40, 60, 80, 100]
ODDSW_GRID = [round(x * 0.1, 1) for x in range(11)]  # 0.0 .. 1.0

LOCK_TEAM = "SYD"  # the Roosters lock — used for the walk-forward loyalty-tax backtest


# ---------------------------------------------------------------------------
# Elo replay
# ---------------------------------------------------------------------------
def sort_chronological(results):
    """Stable sort by season then round, preserving original (discovery/append)
    order within a round as the tiebreaker — the memory has no explicit kickoff
    order, so append order is the best available proxy. Entries with no season
    stamp predate 2027 and default to 2026 (audit A6): without the season key,
    2027's round 1 would sort BEFORE 2026's round 2 and scramble the Elo replay."""
    indexed = list(enumerate(results))
    indexed.sort(key=lambda p: (p[1].get("season") or 2026, p[1].get("round", 0), p[0]))
    return [r for _, r in indexed]


def replay_elo(results_sorted, elo_k, elo_hga):
    """Chronological Elo replay starting every team at 1500. Returns
    (final_elo_dict, per_game) where per_game[i] carries the ratings as they
    stood BEFORE that game was applied (for walk-forward evaluation)."""
    elo = {short: 1500.0 for short in TEAMS}
    per_game = []
    for r in results_sorted:
        home, away = r.get("home"), r.get("away")
        if home not in elo or away not in elo:
            continue
        hs, aw = r.get("hs"), r.get("as")
        if not isinstance(hs, (int, float)) or not isinstance(aw, (int, float)):
            continue
        rh, ra = elo[home], elo[away]
        per_game.append({
            "round": r.get("round"), "home": home, "away": away, "hs": hs, "as": aw,
            "eloHomeBefore": rh, "eloAwayBefore": ra,
        })

        expected_home = 1.0 / (1.0 + 10 ** (-((rh + elo_hga) - ra) / ELO_PROB_BASE))
        actual_home = 1.0 if hs > aw else (0.0 if hs < aw else 0.5)
        margin = abs(hs - aw)
        # Margin-of-victory multiplier (FiveThirtyEight): keyed on the WINNER-
        # relative pre-game Elo gap — winner's rating (incl. the home bump if
        # the winner was at home) minus the loser's. Negative for an upset, so
        # upsets are AMPLIFIED (mult > 1) and expected blowouts dampened. The
        # old abs() version dampened every big-gap game regardless of who won,
        # the exact opposite for upsets (audit A3, 2026-08-04). +1 inside the
        # log keeps a draw (margin=0) from zeroing the multiplier; a draw uses
        # winner_diff=0 (no winner). Denominator clamped positive.
        if hs > aw:
            winner_diff = (rh + elo_hga) - ra
        elif aw > hs:
            winner_diff = ra - (rh + elo_hga)
        else:
            winner_diff = 0.0
        mov_mult = (math.log(margin + 1) + 1) * (2.2 / max(0.001 * winner_diff + 2.2, 0.1))
        delta = elo_k * mov_mult * (actual_home - expected_home)
        elo[home] = rh + delta
        elo[away] = ra - delta
    return elo, per_game


# ---------------------------------------------------------------------------
# Points-space prediction — mirrors nrl-tipping-guide.html's
# eloGapToPoints()/logistic() exactly, so backtest numbers reflect what the
# live app will actually predict once these params are consumed.
# ---------------------------------------------------------------------------
def elo_gap_to_points(diff, logistic_scale):
    return diff * logistic_scale * math.log(10) / ELO_PROB_BASE


def logistic(margin, logistic_scale):
    try:
        return 1.0 / (1.0 + math.exp(-margin / logistic_scale))
    except OverflowError:
        return 0.0 if margin < 0 else 1.0


def predict_phome(elo_home_before, elo_away_before, home_adv, logistic_scale):
    margin = elo_gap_to_points(elo_home_before - elo_away_before, logistic_scale) + home_adv
    return logistic(margin, logistic_scale)


def actual_home_outcome(hs, aw):
    return 1.0 if hs > aw else (0.0 if hs < aw else 0.5)


def walk_forward_log_loss(per_game, home_adv, logistic_scale):
    if not per_game:
        return float("inf")
    total = 0.0
    for g in per_game:
        p = min(max(predict_phome(g["eloHomeBefore"], g["eloAwayBefore"], home_adv, logistic_scale), 1e-6), 1 - 1e-6)
        a = actual_home_outcome(g["hs"], g["as"])
        total += -(a * math.log(p) + (1 - a) * math.log(1 - p))
    return total / len(per_game)


def grid_search_elo_params(results_sorted, home_adv):
    """Deterministic grid search over (eloK, eloHGA) that minimises
    walk-forward log-loss, with logisticScale PINNED at
    DEFAULT_LOGISTIC_SCALE (audit A2 — the scale is unidentifiable from
    win/loss outcomes, so searching it just inflated homeAdv/scale).
    Returns (best_logloss, eloK, eloHGA). Ties keep the first (smallest
    grid-order) combo found, so results are 100% reproducible run to run
    on the same memory."""
    best = None
    for k in ELOK_GRID:
        for hga in ELOHGA_GRID:
            _, per_game = replay_elo(results_sorted, k, hga)
            ll = walk_forward_log_loss(per_game, home_adv, DEFAULT_LOGISTIC_SCALE)
            if best is None or ll < best[0] - 1e-12:
                best = (ll, k, hga)
    return best


# ---------------------------------------------------------------------------
# Optional odds-history blend (--odds-history)
# ---------------------------------------------------------------------------
import re  # noqa: E402  (kept local to this section for readability)

ODDS_HIST_LINE_RE = re.compile(
    r"round\s*(?P<round>\d{1,2})\s*[:\-]\s*"
    r"(?P<a>[A-Za-z][A-Za-z .'\-]{2,30}?)\s+v(?:s)?\.?\s+(?P<b>[A-Za-z][A-Za-z .'\-]{2,30}?)\s*:\s*"
    r"(?P<oa>\d+(?:\.\d+)?)\s*/\s*(?P<ob>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_odds_history(raw_text):
    """Return {(round, frozenset({a,b})): {short: decimal_odds}}. Optional,
    best-effort format (one line per historical match):
        Round 21: Cowboys v Roosters: 1.85/1.95
    """
    out = {}
    for line in raw_text.splitlines():
        m = ODDS_HIST_LINE_RE.search(line)
        if not m:
            continue
        a_short, b_short = find_short(m.group("a")), find_short(m.group("b"))
        if not a_short or not b_short or a_short == b_short:
            continue
        rnd = int(m.group("round"))
        out[(rnd, frozenset({a_short, b_short}))] = {a_short: float(m.group("oa")), b_short: float(m.group("ob"))}
    return out


def devig_home_prob(home_odds, away_odds):
    ih, ia = 1.0 / home_odds, 1.0 / away_odds
    total = ih + ia
    return ih / total if total > 0 else 0.5


def fit_odds_weight(per_game, home_adv, logistic_scale, odds_hist):
    """Grid-search oddsWeight in [0,1] to minimise Brier over games with a
    matched historical odds line. Returns (oddsWeight, marketBrier, learned)
    — learned=False (default 0.5, marketBrier=None) if no odds matched."""
    matched = []
    for g in per_game:
        pair = odds_hist.get((g["round"], frozenset({g["home"], g["away"]})))
        if not pair:
            continue
        h_odds, a_odds = pair.get(g["home"]), pair.get(g["away"])
        if not h_odds or not a_odds:
            continue
        market_p = devig_home_prob(h_odds, a_odds)
        model_p = predict_phome(g["eloHomeBefore"], g["eloAwayBefore"], home_adv, logistic_scale)
        matched.append((model_p, market_p, actual_home_outcome(g["hs"], g["as"])))

    if not matched:
        return DEFAULT_ODDS_WEIGHT, None, False

    best_w, best_brier = DEFAULT_ODDS_WEIGHT, None
    for w in ODDSW_GRID:
        brier = sum(((1 - w) * mp + w * mkp - a) ** 2 for mp, mkp, a in matched) / len(matched)
        if best_brier is None or brier < best_brier - 1e-12:
            best_brier, best_w = brier, w
    market_only_brier = sum((mkp - a) ** 2 for _, mkp, a in matched) / len(matched)
    return best_w, round(market_only_brier, 4), True


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
def backtest_metrics(per_game, home_adv, logistic_scale):
    if not per_game:
        return {"games": 0, "brier": None, "logloss": None, "hit": None, "marketBrier": None}
    briers, losses = [], []
    hits = hit_n = 0
    for g in per_game:
        p = predict_phome(g["eloHomeBefore"], g["eloAwayBefore"], home_adv, logistic_scale)
        p_clipped = min(max(p, 1e-6), 1 - 1e-6)
        a = actual_home_outcome(g["hs"], g["as"])
        briers.append((p - a) ** 2)
        losses.append(-(a * math.log(p_clipped) + (1 - a) * math.log(1 - p_clipped)))
        if g["hs"] != g["as"]:
            hit_n += 1
            predicted_home_win = p >= 0.5
            actual_home_win = g["hs"] > g["as"]
            if predicted_home_win == actual_home_win:
                hits += 1
    return {
        "games": len(per_game),
        "brier": round(sum(briers) / len(briers), 4),
        "logloss": round(sum(losses) / len(losses), 4),
        "hit": round(hits / hit_n, 4) if hit_n else None,
        "marketBrier": None,  # filled in by caller if odds history matched
    }


def lock_tax_metrics(per_game, home_adv, logistic_scale):
    """Walk-forward loyalty-tax figures for the Roosters lock (audit A4).

    Every Roosters game in the memory is graded with the Elo ratings as they
    stood BEFORE that game — never the final ratings, which already contain
    each game's own result (the hindsight pattern GOTCHAS 2026-08-02 bans).
    The front-end's renderAcc() displays these figures verbatim; it no longer
    computes its own. Draws are excluded, matching every other grading surface."""
    games = model_right = rk_wins = 0
    for g in per_game:
        if g["home"] != LOCK_TEAM and g["away"] != LOCK_TEAM:
            continue
        if g["hs"] == g["as"]:
            continue
        games += 1
        p = predict_phome(g["eloHomeBefore"], g["eloAwayBefore"], home_adv, logistic_scale)
        actual_home_win = g["hs"] > g["as"]
        if (p >= 0.5) == actual_home_win:
            model_right += 1
        rk_home = g["home"] == LOCK_TEAM
        if actual_home_win == rk_home:
            rk_wins += 1
    return {"games": games, "modelRight": model_right, "rkWins": rk_wins}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--learned", default="nrl_learned.js", help="learning-loop memory/output file")
    ap.add_argument("--odds-history", default=None, help="optional historical odds dump (see module docstring)")
    ap.add_argument("--updated", default=None, help="ISO date override; defaults to today")
    args = ap.parse_args()

    learned_path = Path(args.learned)
    try:
        data = load_learned(learned_path)
    except Exception as e:
        print(f"[learn_model] ERROR: could not read/parse {learned_path}: {e}", file=sys.stderr)
        print("[learn_model] ABORTED — nothing written. Seed nrl_learned.js with a `results` "
              "list first (see sources.md).", file=sys.stderr)
        sys.exit(1)

    results = data.get("results", [])
    games = len(results)
    low_confidence = games < LOW_CONFIDENCE_THRESHOLD

    # homeAdv: a direct statistic (observed mean home winning margin), not a
    # fragile multi-parameter fit — safe to report even with a thin sample.
    if games:
        home_adv = sum(r["hs"] - r["as"] for r in results) / games
    else:
        home_adv = DEFAULT_LEARNED_PARAMS_HOME_ADV = DEFAULT_ELO_K and None  # unreachable placeholder
    if not games:
        home_adv = 4.0

    results_sorted = sort_chronological(results)

    # logisticScale is always the pinned constant (audit A2) — never fitted.
    logistic_scale = DEFAULT_LOGISTIC_SCALE
    if low_confidence:
        # Guardrail: with this few games a grid search will happily overfit
        # to noise (e.g. picking an extreme K/HGA that "explains" 7
        # games perfectly). Use fixed conservative defaults instead, but
        # still replay/backtest with THOSE exact numbers so the accuracy
        # trend is honest about what would actually run if activated.
        elo_k, elo_hga = DEFAULT_ELO_K, DEFAULT_ELO_HGA
        best_logloss = walk_forward_log_loss(replay_elo(results_sorted, elo_k, elo_hga)[1], home_adv, logistic_scale)
    else:
        best_logloss, elo_k, elo_hga = grid_search_elo_params(results_sorted, home_adv)

    final_elo, per_game = replay_elo(results_sorted, elo_k, elo_hga)

    odds_hist = {}
    if args.odds_history:
        odds_path = Path(args.odds_history)
        if odds_path.exists():
            odds_hist = parse_odds_history(odds_path.read_text(encoding="utf-8", errors="ignore"))
        else:
            print(f"[learn_model] WARNING: --odds-history file not found: {odds_path}", file=sys.stderr)

    odds_weight, market_brier, odds_learned = fit_odds_weight(per_game, home_adv, logistic_scale, odds_hist)

    backtest = backtest_metrics(per_game, home_adv, logistic_scale)
    backtest["marketBrier"] = market_brier
    backtest["lockTax"] = lock_tax_metrics(per_game, home_adv, logistic_scale)

    updated = args.updated or datetime.date.today().isoformat()
    history = list(data.get("history", []))  # never lose prior entries
    # Self-heal: collapse consecutive identical points. A past bug appended one
    # entry every run regardless of whether anything actually changed, so the
    # "precision over time" trend filled up with duplicates.
    deduped = []
    for h in history:
        if deduped and deduped[-1].get("games") == h.get("games") and deduped[-1].get("brier") == h.get("brier"):
            continue
        deduped.append(h)
    history = deduped
    # Only record a new trend point when the games learned or the brier changed.
    entry = {"date": updated, "games": games, "brier": backtest["brier"]}
    if not history or history[-1].get("games") != entry["games"] or history[-1].get("brier") != entry["brier"]:
        history.append(entry)

    out = {
        "updated": updated,
        "gamesLearned": games,
        "lowConfidence": low_confidence,
        "params": {
            "homeAdv": round(home_adv, 2),
            "logisticScale": round(logistic_scale, 1),
            "oddsWeight": odds_weight,
            "eloK": elo_k,
            "eloHGA": elo_hga,
        },
        "elo": {short: round(final_elo.get(short, 1500.0), 1) for short in TEAMS},
        "backtest": backtest,
        "history": history,
        "results": results,  # untouched — parse_nrl.py owns growing this list
    }

    notes = []
    if low_confidence:
        notes.append(f"lowConfidence: only {games} game(s) in memory (<{LOW_CONFIDENCE_THRESHOLD}) — "
                      "eloK/eloHGA held at conservative defaults, not grid-searched; "
                      "front-end ignores these learned params entirely while lowConfidence=true.")
    else:
        notes.append(f"fitted via grid search: walk-forward logloss={round(best_logloss, 4)} "
                      f"over eloK{ELOK_GRID} x eloHGA{ELOHGA_GRID}; "
                      f"logisticScale pinned at {DEFAULT_LOGISTIC_SCALE:g} (unidentifiable from "
                      "win/loss outcomes — audit A2, 2026-08-04).")
    if not odds_learned:
        notes.append("oddsWeight defaulted to 0.5 — no --odds-history supplied/matched, not yet learned.")
    note = " ".join(notes)

    emit_learned_js(out, learned_path, note=note)

    print(f"[learn_model] wrote {learned_path}")
    print(f"[learn_model] gamesLearned={games} lowConfidence={low_confidence}")
    print(f"[learn_model] params={out['params']}")
    print(f"[learn_model] backtest={backtest}")
    print(f"[learn_model] history now has {len(history)} entr{'y' if len(history)==1 else 'ies'}")


if __name__ == "__main__":
    main()
