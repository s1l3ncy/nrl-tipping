#!/usr/bin/env python3
"""
validate_learned.py — Dev C (QA/tooling)

Validates a generated `nrl_learned.js` (window.NRL_LEARNED) — the app's
learned memory + fitted model parameters, regenerated each update by
learn_model.py. Designed to be run standalone or by the weekly/daily
automation job, right after learn_model.py runs and before the app is
ever allowed to pick the new file up.

Usage:
    python3 validate_learned.py                    # looks for ./nrl_learned.js
    python3 validate_learned.py path/to/file.js     # explicit path

Exit code: 0 = PASS, 1 = FAIL (or file/parse error).

Expected shape (see SPEC.md "Learning loop (v4)"):
    window.NRL_LEARNED = {
      updated: "2026-07-27",
      gamesLearned: 137,
      lowConfidence: false,
      params: { homeAdv, logisticScale, oddsWeight, eloK, eloHGA },
      elo: { <17 team shorts>: number, ... },
      backtest: { games, brier, logloss, hit, marketBrier|null },
      history: [ {date, games, brier}, ... ],
      results: [ {round, home, away, hs, as}, ... ]
    };

Expected input format
----------------------
`nrl_learned.js` is expected to be a small JS file whose only executable
content is a single assignment: `window.NRL_LEARNED = { ... };`, with the
object literal itself clean, JSON-compatible JSON (no trailing commas, no
comments, no single quotes, no unquoted keys) — mirroring the "expected
clean format" contract validate_data.py documents for nrl_data.js. As with
that validator, this one tolerates a trailing `;`, `//` / `/* */` comments,
and trailing commas before `}`/`]` so a hand-edited file doesn't immediately
blow up with a cryptic JSON error, but it is NOT a full JS parser. If
learn_model.py always emits clean JSON inside the wrapper, no tolerance
behaviour is ever exercised.
"""
import sys
import re
import json
import datetime

KNOWN_SHORTS = {
    "PEN", "SYD", "NZW", "CRO", "DOL", "SOU", "NEW", "NQL",
    "CAN", "MAN", "CBR", "MEL", "BRI", "PAR", "WST", "GLD", "STI",
}
EXPECTED_TEAM_COUNT = 17

REQUIRED_TOP_FIELDS = [
    "updated", "gamesLearned", "lowConfidence", "params", "elo",
    "backtest", "history", "results",
]
REQUIRED_PARAM_FIELDS = ["homeAdv", "logisticScale", "oddsWeight", "eloK", "eloHGA"]
REQUIRED_BACKTEST_FIELDS = ["games", "brier", "logloss", "hit"]  # marketBrier optional (may be null)

# Guardrail per SPEC.md: the app shouldn't trust the learned model until
# roughly this many games have been backtested.
LOW_CONFIDENCE_THRESHOLD = 30

# Sane ranges (hard fail outside these; a few also carry a tighter "typical"
# band that only warns, since fitted values can legitimately be unusual
# early in a season without being wrong).
RANGE_HOME_ADV = (-5, 20)
RANGE_LOGISTIC_SCALE = (0, 50)  # exclusive lower bound (>0)
RANGE_ELO_K = (0, 100)          # exclusive lower bound (>0)
RANGE_ELO_HGA = (-50, 400)
RANGE_ELO_RATING = (0, 4000)


def strip_js_comments(text):
    """Remove // line comments and /* */ block comments, respecting strings."""
    out = []
    i = 0
    n = len(text)
    in_str = None
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'"):
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def strip_trailing_commas(text):
    return re.sub(r",\s*([}\]])", r"\1", text)


def extract_json_object(raw_text):
    """Pull the object literal out of `window.NRL_LEARNED = { ... };` and parse it."""
    text = strip_js_comments(raw_text)
    m = re.search(r"window\.NRL_LEARNED\s*=\s*(\{.*\})\s*;?\s*$", text, re.DOTALL)
    if not m:
        m2 = re.search(r"window\.NRL_LEARNED\s*=\s*(\{)", text)
        if not m2:
            raise ValueError(
                "Could not find `window.NRL_LEARNED = { ... }` assignment in file."
            )
        start = m2.start(1)
        depth = 0
        end = None
        in_str = None
        i = start
        while i < len(text):
            c = text[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == in_str:
                    in_str = None
            elif c in ('"', "'"):
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        if end is None:
            raise ValueError("Unbalanced braces in nrl_learned.js — could not extract object.")
        obj_text = text[start:end]
    else:
        obj_text = m.group(1)

    obj_text = strip_trailing_commas(obj_text)
    return json.loads(obj_text)


class Reporter:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []

    def fail(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def ok(self):
        return not self.errors


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(data, rep: Reporter):
    # --- top-level fields present ---
    for f in REQUIRED_TOP_FIELDS:
        if f not in data:
            rep.fail(f"Missing top-level field: '{f}'")
    if not rep.ok():
        return

    # --- updated ---
    updated = data.get("updated")
    if not isinstance(updated, str):
        rep.fail("'updated' must be a date string")
    else:
        try:
            datetime.date.fromisoformat(updated)
        except ValueError:
            rep.fail(f"'updated' is not a valid ISO date (YYYY-MM-DD): {updated!r}")

    # --- gamesLearned ---
    games_learned = data.get("gamesLearned")
    if not isinstance(games_learned, int) or isinstance(games_learned, bool) or games_learned < 0:
        rep.fail(f"'gamesLearned' must be a non-negative int, got {games_learned!r}")
        games_learned = None

    # --- lowConfidence ---
    low_confidence = data.get("lowConfidence")
    if not isinstance(low_confidence, bool):
        rep.fail(f"'lowConfidence' must be a bool, got {low_confidence!r}")

    if games_learned is not None and isinstance(low_confidence, bool):
        if games_learned < LOW_CONFIDENCE_THRESHOLD and not low_confidence:
            rep.warn(
                f"guardrail: gamesLearned ({games_learned}) is below the "
                f"~{LOW_CONFIDENCE_THRESHOLD}-game trust threshold but "
                f"lowConfidence=false — the app may end up trusting the "
                f"learned model too early."
            )
        if games_learned >= LOW_CONFIDENCE_THRESHOLD and low_confidence:
            rep.info(
                f"lowConfidence=true even though gamesLearned ({games_learned}) is at/above "
                f"the ~{LOW_CONFIDENCE_THRESHOLD}-game threshold — fine, just conservative."
            )

    # --- params ---
    params = data.get("params")
    if not isinstance(params, dict):
        rep.fail("'params' must be an object")
        params = {}
    for f in REQUIRED_PARAM_FIELDS:
        if f not in params:
            rep.fail(f"'params' missing field '{f}'")

    home_adv = params.get("homeAdv")
    if "homeAdv" in params:
        if not _is_number(home_adv):
            rep.fail(f"params.homeAdv must be numeric, got {home_adv!r}")
        elif not (RANGE_HOME_ADV[0] <= home_adv <= RANGE_HOME_ADV[1]):
            rep.fail(f"params.homeAdv ({home_adv}) is outside sane range {RANGE_HOME_ADV}")

    logistic_scale = params.get("logisticScale")
    if "logisticScale" in params:
        if not _is_number(logistic_scale):
            rep.fail(f"params.logisticScale must be numeric, got {logistic_scale!r}")
        elif not (logistic_scale > RANGE_LOGISTIC_SCALE[0]):
            rep.fail(f"params.logisticScale must be > 0, got {logistic_scale}")
        elif logistic_scale > RANGE_LOGISTIC_SCALE[1]:
            rep.fail(f"params.logisticScale ({logistic_scale}) is outside sane range {RANGE_LOGISTIC_SCALE}")

    odds_weight = params.get("oddsWeight")
    if "oddsWeight" in params:
        if not _is_number(odds_weight):
            rep.fail(f"params.oddsWeight must be numeric, got {odds_weight!r}")
        elif not (0 <= odds_weight <= 1):
            rep.fail(f"params.oddsWeight must be in [0,1], got {odds_weight}")

    elo_k = params.get("eloK")
    if "eloK" in params:
        if not _is_number(elo_k):
            rep.fail(f"params.eloK must be numeric, got {elo_k!r}")
        elif not (elo_k > RANGE_ELO_K[0]):
            rep.fail(f"params.eloK must be > 0, got {elo_k}")
        elif elo_k > RANGE_ELO_K[1]:
            rep.fail(f"params.eloK ({elo_k}) is outside sane range {RANGE_ELO_K}")

    elo_hga = params.get("eloHGA")
    if "eloHGA" in params:
        if not _is_number(elo_hga):
            rep.fail(f"params.eloHGA must be numeric, got {elo_hga!r}")
        elif not (RANGE_ELO_HGA[0] <= elo_hga <= RANGE_ELO_HGA[1]):
            rep.fail(f"params.eloHGA ({elo_hga}) is outside sane range {RANGE_ELO_HGA}")

    # --- elo ---
    elo = data.get("elo")
    if not isinstance(elo, dict):
        rep.fail("'elo' must be an object mapping team shorts to numbers")
        elo = {}
    missing_shorts = KNOWN_SHORTS - set(elo.keys())
    if missing_shorts:
        rep.fail(f"'elo' is missing rating(s) for known team short(s): {sorted(missing_shorts)}")
    unknown_shorts = set(elo.keys()) - KNOWN_SHORTS
    if unknown_shorts:
        rep.fail(f"'elo' contains unknown team short(s): {sorted(unknown_shorts)}")
    for short, val in elo.items():
        if not _is_number(val):
            rep.fail(f"elo['{short}'] must be numeric, got {val!r}")
        elif not (RANGE_ELO_RATING[0] <= val <= RANGE_ELO_RATING[1]):
            rep.fail(f"elo['{short}'] ({val}) is outside sane range {RANGE_ELO_RATING}")
    if len(elo) != EXPECTED_TEAM_COUNT and not missing_shorts and not unknown_shorts:
        rep.warn(f"Expected exactly {EXPECTED_TEAM_COUNT} elo entries, found {len(elo)}")

    # --- backtest ---
    backtest = data.get("backtest")
    if not isinstance(backtest, dict):
        rep.fail("'backtest' must be an object")
        backtest = {}
    for f in REQUIRED_BACKTEST_FIELDS:
        if f not in backtest:
            rep.fail(f"'backtest' missing field '{f}'")

    bt_games = backtest.get("games")
    if "games" in backtest:
        if not isinstance(bt_games, int) or isinstance(bt_games, bool) or bt_games < 0:
            rep.fail(f"backtest.games must be a non-negative int, got {bt_games!r}")

    for f in ("brier", "hit"):
        v = backtest.get(f)
        if f in backtest:
            if not _is_number(v):
                rep.fail(f"backtest.{f} must be numeric, got {v!r}")
            elif not (0 <= v <= 1):
                rep.fail(f"backtest.{f} must be in [0,1], got {v}")

    logloss = backtest.get("logloss")
    if "logloss" in backtest:
        if not _is_number(logloss):
            rep.fail(f"backtest.logloss must be numeric, got {logloss!r}")
        elif logloss < 0:
            rep.fail(f"backtest.logloss must be >= 0, got {logloss}")

    if "marketBrier" in backtest:
        mb = backtest.get("marketBrier")
        if mb is not None:
            if not _is_number(mb):
                rep.fail(f"backtest.marketBrier must be numeric or null, got {mb!r}")
            elif not (0 <= mb <= 1):
                rep.fail(f"backtest.marketBrier must be in [0,1] or null, got {mb}")
    else:
        rep.info("backtest.marketBrier not present (optional — only meaningful when odds history exists)")

    if (
        games_learned is not None
        and isinstance(bt_games, int)
        and not isinstance(bt_games, bool)
        and bt_games != games_learned
    ):
        rep.warn(
            f"backtest.games ({bt_games}) does not match top-level gamesLearned "
            f"({games_learned}) — expected but not fatal if the backtest window differs."
        )

    # --- history ---
    history = data.get("history")
    if not isinstance(history, list):
        rep.fail("'history' must be a list")
        history = []
    if len(history) == 0:
        rep.fail("'history' must be non-empty (at least one learning snapshot expected)")

    for idx, h in enumerate(history):
        if not isinstance(h, dict):
            rep.fail(f"history[{idx}] is not an object")
            continue
        for f in ("date", "games", "brier"):
            if f not in h:
                rep.fail(f"history[{idx}] missing field '{f}'")
        if "date" in h:
            if not isinstance(h["date"], str):
                rep.fail(f"history[{idx}].date must be a date string")
            else:
                try:
                    datetime.date.fromisoformat(h["date"])
                except ValueError:
                    rep.fail(f"history[{idx}].date is not a valid ISO date: {h['date']!r}")
        if "games" in h:
            g = h["games"]
            if not isinstance(g, int) or isinstance(g, bool) or g < 0:
                rep.fail(f"history[{idx}].games must be a non-negative int, got {g!r}")
        if "brier" in h:
            b = h["brier"]
            if not _is_number(b):
                rep.fail(f"history[{idx}].brier must be numeric, got {b!r}")
            elif not (0 <= b <= 1):
                rep.fail(f"history[{idx}].brier must be in [0,1], got {b}")

    # --- results ---
    results = data.get("results")
    if not isinstance(results, list):
        rep.fail("'results' must be a list")
        results = []
    elif len(results) == 0:
        rep.warn("'results' is empty — the learned memory has nothing to learn from yet")

    seen_keys = set()
    for idx, r in enumerate(results):
        if not isinstance(r, dict):
            rep.fail(f"results[{idx}] is not an object")
            continue
        for f in ("round", "home", "away", "hs", "as"):
            if f not in r:
                rep.fail(f"results[{idx}] missing field '{f}'")

        rnd = r.get("round")
        if "round" in r and (not isinstance(rnd, int) or isinstance(rnd, bool)):
            rep.fail(f"results[{idx}].round must be an int, got {rnd!r}")

        home, away = r.get("home"), r.get("away")
        if home and home not in KNOWN_SHORTS:
            rep.fail(f"results[{idx}]: unknown home team short '{home}'")
        if away and away not in KNOWN_SHORTS:
            rep.fail(f"results[{idx}]: unknown away team short '{away}'")
        if home and away and home == away:
            rep.fail(f"results[{idx}]: home and away are the same team ('{home}')")

        for f in ("hs", "as"):
            v = r.get(f)
            if f in r and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                rep.fail(f"results[{idx}].{f} must be a non-negative int, got {v!r}")

        if isinstance(rnd, int) and not isinstance(rnd, bool) and home and away:
            # Season-aware (2026-08-04, audit A6): entries with no season field
            # predate 2027 and default to 2026, so a 2027 repeat of a 2026
            # round+pair is a legitimate new game, not a duplicate.
            key = (r.get("season", 2026), rnd, home, away)
            if key in seen_keys:
                rep.fail(f"results[{idx}]: duplicate entry for season {key[0]}, round {rnd}, {home} v {away}")
            seen_keys.add(key)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "nrl_learned.js"
    print(f"validate_learned.py — checking {path}")
    print("-" * 60)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as e:
        print(f"FAIL: could not read file: {e}")
        sys.exit(1)

    try:
        data = extract_json_object(raw)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"FAIL: could not parse NRL_LEARNED object: {e}")
        print("Hint: nrl_learned.js must contain clean JSON inside")
        print("`window.NRL_LEARNED = { ... };` — no trailing commas or comments")
        print("inside the object unless this validator's tolerant mode covers them.")
        sys.exit(1)

    if not isinstance(data, dict):
        print("FAIL: NRL_LEARNED must be a JSON object")
        sys.exit(1)

    rep = Reporter()
    validate(data, rep)

    if rep.warnings:
        print(f"WARNINGS ({len(rep.warnings)}):")
        for w in rep.warnings:
            print(f"  - {w}")
        print()

    if rep.infos:
        print(f"INFO ({len(rep.infos)}):")
        for i in rep.infos:
            print(f"  - {i}")
        print()

    if rep.ok():
        print(
            f"PASS: gamesLearned={data.get('gamesLearned')}, "
            f"lowConfidence={data.get('lowConfidence')}, "
            f"elo entries={len(data.get('elo', {}))}, "
            f"history snapshots={len(data.get('history', []))}, "
            f"results={len(data.get('results', []))}, "
            f"updated={data.get('updated')}."
        )
        sys.exit(0)
    else:
        print(f"FAIL: {len(rep.errors)} error(s):")
        for e in rep.errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
