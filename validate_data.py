#!/usr/bin/env python3
"""
validate_data.py — Dev C (QA/tooling)

Validates a generated `nrl_data.js` against the data contract defined in
SPEC.md (window.NRL_DATA). Designed to be run standalone or by the weekly
automation job, right after parse_nrl.py produces nrl_data.js and before the
HTML is ever opened.

Usage:
    python3 validate_data.py                 # looks for ./nrl_data.js
    python3 validate_data.py path/to/file.js  # explicit path

Exit code: 0 = PASS, 1 = FAIL (or file/parse error).

Expected input format
----------------------
`nrl_data.js` is expected to be a small JS file whose only executable
content is a single assignment:

    window.NRL_DATA = { ... };

The object literal itself must be clean, JSON-compatible JSON (no trailing
commas, no comments, no single quotes, no unquoted keys) — this is the
"expected clean format" that parse_nrl.py should emit. This validator is a
little tolerant of common non-JSON JS artifacts (a trailing `;`, `//` and
/* */ comments, and trailing commas before `}`/`]`) so a hand-edited or
slightly-off file doesn't immediately blow up with a cryptic JSON error, but
it does NOT try to be a full JS parser. If parse_nrl.py always emits clean
JSON inside the wrapper (as it currently does), no tolerance behaviour is
ever exercised.
"""
import sys
import re
import json
import datetime

EXPECTED_TEAM_COUNT = 17
REQUIRED_TEAM_FIELDS = {
    "name": str,
    "short": str,
    "P": int,
    "W": int,
    "L": int,
    "PF": int,
    "PA": int,
    "last5": int,
}
REQUIRED_TOP_FIELDS = ["updated", "season", "round", "teams", "fixtures", "byeTeams"]


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


def _is_valid_odds_pair(obj):
    """True if `obj` is a well-formed decimal-odds {home,away} pair: both
    sides numeric and > 1 (decimal odds can't be <=1). Used for both the
    legacy flat odds shape and each side (open/close) of the new shape."""
    if not isinstance(obj, dict):
        return False
    h, a = obj.get("home"), obj.get("away")
    h_ok = isinstance(h, (int, float)) and not isinstance(h, bool) and h > 1
    a_ok = isinstance(a, (int, float)) and not isinstance(a, bool) and a > 1
    return h_ok and a_ok


def extract_json_object(raw_text):
    """Pull the object literal out of `window.NRL_DATA = { ... };` and parse it."""
    text = strip_js_comments(raw_text)
    m = re.search(r"window\.NRL_DATA\s*=\s*(\{.*\})\s*;?\s*$", text, re.DOTALL)
    if not m:
        # Fall back: maybe there's trailing content after the object (unlikely) —
        # try to find the first '{' after the assignment and match balanced braces.
        m2 = re.search(r"window\.NRL_DATA\s*=\s*(\{)", text)
        if not m2:
            raise ValueError(
                "Could not find `window.NRL_DATA = { ... }` assignment in file."
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
            raise ValueError("Unbalanced braces in nrl_data.js — could not extract object.")
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


def validate(data, rep: Reporter):
    # --- top-level fields present ---
    for f in REQUIRED_TOP_FIELDS:
        if f not in data:
            rep.fail(f"Missing top-level field: '{f}'")
    if not rep.ok():
        return  # no point going further without the basics

    # --- round is an int ---
    if not isinstance(data["round"], int):
        rep.fail(f"'round' must be an int, got {type(data['round']).__name__}: {data['round']!r}")

    # --- season is an int ---
    if not isinstance(data.get("season"), int):
        rep.fail(f"'season' must be an int, got {type(data.get('season')).__name__}")

    # --- updated date parses ---
    updated = data.get("updated")
    if not isinstance(updated, str):
        rep.fail("'updated' must be a date string")
    else:
        try:
            datetime.date.fromisoformat(updated)
        except ValueError:
            rep.fail(f"'updated' is not a valid ISO date (YYYY-MM-DD): {updated!r}")

    # --- teams ---
    teams = data.get("teams")
    if not isinstance(teams, list):
        rep.fail("'teams' must be a list")
        teams = []

    if len(teams) != EXPECTED_TEAM_COUNT:
        rep.fail(f"Expected exactly {EXPECTED_TEAM_COUNT} teams, found {len(teams)}")

    shorts_seen = {}
    for idx, t in enumerate(teams):
        if not isinstance(t, dict):
            rep.fail(f"teams[{idx}] is not an object")
            continue
        label = t.get("short", f"index {idx}")
        for field, typ in REQUIRED_TEAM_FIELDS.items():
            if field not in t:
                rep.fail(f"Team '{label}' missing field '{field}'")
                continue
            val = t[field]
            if typ is int:
                if not isinstance(val, int) or isinstance(val, bool):
                    rep.fail(f"Team '{label}' field '{field}' must be numeric, got {val!r}")
            elif typ is str:
                if not isinstance(val, str) or not val.strip():
                    rep.fail(f"Team '{label}' field '{field}' must be a non-empty string, got {val!r}")

        # sanity checks on numeric relationships (warnings, not hard failures,
        # since a mid-round data source could legitimately look odd briefly)
        if all(k in t for k in ("P", "W", "L")):
            try:
                if t["W"] + t["L"] > t["P"]:
                    rep.warn(f"Team '{label}': W+L ({t['W']}+{t['L']}) exceeds P ({t['P']})")
            except TypeError:
                pass

        short = t.get("short")
        if short:
            shorts_seen.setdefault(short, 0)
            shorts_seen[short] += 1

    dupe_shorts = [s for s, c in shorts_seen.items() if c > 1]
    if dupe_shorts:
        rep.fail(f"Duplicate team 'short' code(s): {dupe_shorts}")

    known_shorts = set(shorts_seen.keys())

    # --- fixtures ---
    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list):
        rep.fail("'fixtures' must be a list")
        fixtures = []
    elif len(fixtures) == 0:
        rep.warn("'fixtures' is empty")

    teams_in_round = []
    for idx, f in enumerate(fixtures):
        if not isinstance(f, dict):
            rep.fail(f"fixtures[{idx}] is not an object")
            continue
        home, away = f.get("home"), f.get("away")
        if not home or not away:
            rep.fail(f"fixtures[{idx}] missing 'home' or 'away'")
            continue
        if home == away:
            rep.fail(f"fixtures[{idx}]: home and away are the same team ('{home}')")
        if home not in known_shorts:
            rep.fail(f"fixtures[{idx}]: unknown home team short '{home}'")
        if away not in known_shorts:
            rep.fail(f"fixtures[{idx}]: unknown away team short '{away}'")
        teams_in_round.extend([home, away])

        kickoff = f.get("kickoff")
        if kickoff:
            try:
                # Accept trailing 'Z' (UTC) by normalising to +00:00 for fromisoformat
                datetime.datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                rep.fail(f"fixtures[{idx}]: 'kickoff' is not a valid ISO datetime: {kickoff!r}")
        else:
            rep.info(f"fixtures[{idx}] ({home} v {away}): no 'kickoff' set (optional field)")

        venue = f.get("venue")
        if not venue:
            rep.info(f"fixtures[{idx}] ({home} v {away}): no 'venue' set (optional field)")

        # --- odds: null, legacy flat {home,away}, or {open,close} (CLV) ---
        odds = f.get("odds")
        if odds is None:
            rep.info(f"fixtures[{idx}] ({home} v {away}): no 'odds' set (optional field)")
        elif isinstance(odds, dict) and ("open" in odds or "close" in odds):
            open_v, close_v = odds.get("open"), odds.get("close")
            if open_v is not None and not _is_valid_odds_pair(open_v):
                rep.fail(f"fixtures[{idx}] ({home} v {away}): 'odds.open' must be null or a "
                         f"{{home,away}} decimal-odds pair >1, got {open_v!r}")
            if close_v is not None and not _is_valid_odds_pair(close_v):
                rep.fail(f"fixtures[{idx}] ({home} v {away}): 'odds.close' must be null or a "
                         f"{{home,away}} decimal-odds pair >1, got {close_v!r}")
            if (open_v is not None and _is_valid_odds_pair(open_v)
                    and close_v is not None and _is_valid_odds_pair(close_v)):
                rep.info(f"fixtures[{idx}] ({home} v {away}): opening + closing odds both "
                         f"present — closing-line-value (CLV) trackable.")
        elif isinstance(odds, dict) and ("home" in odds or "away" in odds):
            # Legacy flat shape (pre-CLV schema) — still accepted for backward compatibility.
            if not _is_valid_odds_pair(odds):
                rep.fail(f"fixtures[{idx}] ({home} v {away}): legacy 'odds' must be a "
                         f"{{home,away}} decimal-odds pair >1, got {odds!r}")
        else:
            rep.fail(f"fixtures[{idx}] ({home} v {away}): 'odds' must be null, a legacy "
                     f"{{home,away}} object, or an {{open,close}} object, got {odds!r}")

    # no team plays twice in the round
    counts = {}
    for s in teams_in_round:
        counts[s] = counts.get(s, 0) + 1
    dupes_in_round = [s for s, c in counts.items() if c > 1]
    if dupes_in_round:
        rep.fail(f"Team(s) appear more than once in round's fixtures: {dupes_in_round}")

    # --- byeTeams ---
    bye_teams = data.get("byeTeams")
    if not isinstance(bye_teams, list):
        rep.fail("'byeTeams' must be a list")
        bye_teams = []
    for s in bye_teams:
        if s not in known_shorts:
            rep.fail(f"byeTeams contains unknown team short '{s}'")
        if s in teams_in_round:
            rep.fail(f"byeTeams contains '{s}' but that team also has a fixture this round")

    # every known team should be accounted for: either playing or on bye
    if known_shorts:
        accounted = set(teams_in_round) | set(bye_teams)
        missing = known_shorts - accounted
        if missing:
            rep.fail(f"Team(s) neither fixtured nor on bye this round: {sorted(missing)}")
        extra_byes = set(bye_teams) - known_shorts
        if extra_byes:
            rep.fail(f"byeTeams reference unknown teams: {sorted(extra_byes)}")

    # a normal 17-team competition has exactly one bye per round
    if len(teams) == EXPECTED_TEAM_COUNT and len(bye_teams) != 1:
        rep.warn(f"Expected exactly 1 bye team for a 17-team comp, found {len(bye_teams)}: {bye_teams}")

    # --- results[] (optional) ---
    results = data.get("results")
    if results is not None:
        if not isinstance(results, list):
            rep.fail("'results' must be a list when present")
        else:
            for idx, r in enumerate(results):
                if not isinstance(r, dict):
                    rep.fail(f"results[{idx}] is not an object")
                    continue
                for field in ("round", "home", "away", "hs", "as"):
                    if field not in r:
                        rep.fail(f"results[{idx}] missing field '{field}'")
                if "round" in r and not isinstance(r["round"], int):
                    rep.fail(f"results[{idx}]: 'round' must be an int")
                for field in ("hs", "as"):
                    if field in r and not isinstance(r[field], int):
                        rep.fail(f"results[{idx}]: '{field}' must be an int")
                if r.get("home") and r.get("home") not in known_shorts:
                    rep.fail(f"results[{idx}]: unknown home team short '{r.get('home')}'")
                if r.get("away") and r.get("away") not in known_shorts:
                    rep.fail(f"results[{idx}]: unknown away team short '{r.get('away')}'")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "nrl_data.js"
    print(f"validate_data.py — checking {path}")
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
        print(f"FAIL: could not parse NRL_DATA object: {e}")
        print("Hint: nrl_data.js must contain clean JSON inside")
        print("`window.NRL_DATA = { ... };` — no trailing commas or comments")
        print("inside the object unless this validator's tolerant mode covers them.")
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
        n_teams = len(data.get("teams", []))
        n_fix = len(data.get("fixtures", []))
        print(f"PASS: {n_teams} teams, {n_fix} fixtures, round {data.get('round')}, "
              f"updated {data.get('updated')}.")
        sys.exit(0)
    else:
        print(f"FAIL: {len(rep.errors)} error(s):")
        for e in rep.errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
