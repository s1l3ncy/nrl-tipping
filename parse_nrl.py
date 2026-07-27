#!/usr/bin/env python3
"""
parse_nrl.py — Dev A data pipeline for the NRL Tipping App.

PURE PARSER. Makes NO network calls. It reads raw page dumps that the
orchestrator has already fetched and saved to disk (e.g. via web-fetch
tools), extracts the ladder (incl. Home/Away splits) + next round's
fixtures, cross-checks the sources against each other, and writes a valid
nrl_data.js matching the SPEC.md / schema-v3 contract:

    window.NRL_DATA = { updated, season, round, source, teams[], fixtures[],
                         byeTeams[], results[]? };

    team = { name, short, colour, P, W, L, PF, PA, last5,
             home: {P,W,L,PF,PA} | null, away: {P,W,L,PF,PA} | null,
             news: string | null }

    fixture = { home, away, venue, city, kickoff,
                odds: {open:{home,away}|null, close:{home,away}|null}
                      | {home,away} (legacy flat, still accepted) | null,
                weather: string | null, h2h: null }

`fixture.odds` carries both the FIRST odds seen (`open`) and the LATEST
odds seen (`close`) so the app can compute closing-line-value (CLV) —
whether the model's read looked good against the market's opening price
vs where the market actually closed. On a full rebuild (this script run
without --merge), a fresh odds dump sets `open` and `close` to the same
freshly-parsed values (there's only one sighting so far). In `--merge`
mode, `open` is only ever set the FIRST time odds are seen for a fixture
and is never overwritten after that; `close` is updated to the newest
parsed odds on every merge run. The legacy flat `{home,away}` shape (no
open/close) is still accepted on read for backward compatibility with
older nrl_data.js files, and is normalised into the open/close shape the
next time odds are (re)applied.

`updated` is an ISO date (YYYY-MM-DD) stamped with the real run date
(`datetime.date.today()`) every time this script executes — never a
hardcoded literal. The front-end reads `NRL_DATA.updated` to decide whether
its cached copy is stale and to key its local-storage cache, so it must
reflect the actual day the data was generated. Pass `--updated` only to
backfill/override when running the script on a different day than the
source dumps were fetched (e.g. re-running against an older saved dump).

Usage:
    python3 parse_nrl.py [--ladder LADDER_FILE] [--draw DRAW_FILE]
                          [--out nrl_data.js] [--season 2026]
                          [--source "zerotackle.com"]
                          [--odds ODDS_FILE] [--injuries INJURIES_FILE]
                          [--weather WEATHER_FILE]

Defaults (used if flags omitted, so it "just works" in the project folder):
    --ladder  ladder_dump.html   (Zero Tackle NRL ladder page dump)
    --draw    draw_dump.html     (NRL.com draw page dump)
    --out     nrl_data.js
    --season  2026
    --source  zerotackle.com

--odds / --injuries / --weather are OPTIONAL local-file inputs (see
sources.md for the exact format expected of each). When omitted, the
corresponding fields (`fixture.odds`, `team.news`, `fixture.weather`) are
simply left as `null` — the front-end and validate_data.py both treat that
as normal, not an error. This script never fetches these itself; someone
(the orchestrator or a human) saves the raw dumps to disk first.

Either ladder/draw input file may be absent; the script degrades
gracefully (see `degrade` logic below) rather than crashing, but it will
refuse to WRITE a broken nrl_data.js — if it cannot assemble a valid
17-team roster it exits non-zero and leaves any existing nrl_data.js
untouched.

---------------------------------------------------------------------------
Expected source shapes (see sources.md for exact URLs/selectors)
---------------------------------------------------------------------------
LADDER (Zero Tackle "NRL Ladder" page, rendered to plain-ish text/HTML).
One row per team, columns in this order (typical WordPress ladder table):
    Pos  Team  P  W  D  L  PF  PA  Diff  Pts  [Form letters e.g. W W L W L]
Row example (HTML tags allowed and stripped automatically):
    1  Panthers  18  14  0  4  539  255  +284  30  W W W L W

The same page also carries separate "Home" and "Away" ladder tables
(each team's split P/W/L/PF/PA for games played at home vs away). Zero
Tackle marks these with a heading ("Home" / "Away") immediately before
the table. Row shape (Diff/Pts/form columns are ignored if present):
    Pos  Team  P  W  D  L  PF  PA
If a split table can't be found/parsed, that team's "home"/"away" value
is emitted as `null` (the app handles that gracefully) rather than guessed.

DRAW (NRL.com draw / fixtures page for the next round).
Expects lines that mention two teams separated by "v" / "vs", plus a
round heading like "Round 22" and, optionally, a venue and an ISO-ish or
"Day D Month, HH:MMpm" kickoff time nearby. Example:
    Round 22
    Cowboys v Roosters
    QLD Country Bank Stadium
    Wed 30 Jul, 7:50pm AEST
The host city for each fixture is derived from the venue name (a built-in
VENUE_CITY table), falling back to the home team's usual home city if the
venue isn't recognised.

ODDS (optional, --odds): plain text, one match per line, e.g.:
    Cowboys v Roosters: 1.85 / 1.95
The first decimal is the first-named team's price, the second is the
second-named team's price — they're matched back to whichever side is
actually home/away in the parsed draw, not by line order.

INJURIES / TEAM NEWS (optional, --injuries): plain text, one team per
line, "TeamName: free text", e.g.:
    Panthers: Nathan Cleary (calf) test, expected to play.
Unmatched lines are ignored; teams with no line get `news: null`.

WEATHER (optional, --weather): plain text, one city per line,
"City: free text", e.g.:
    Townsville: Fine, 26C, light breeze.
Matched to each fixture by its resolved `city`. Cities with no line get
`weather: null`.

RESULTS / LEARNING-LOOP MEMORY (optional, --results; the draw dump is also
scanned automatically). Once a round's games are finished, the draw page (or
a dedicated results/scores page saved to --results) usually prints final
scores. This script extracts any finished games it can find as
{round, home, away, hs, as} and APPENDS newly-seen ones (deduped on
round+home+away) to the append-only match-log memory kept in nrl_learned.js
(--learned, default nrl_learned.js) — never deleting prior entries, and
never writing at all if an existing nrl_learned.js can't be parsed. This
runs on BOTH a full rebuild and a --merge run. It does NOT recompute the
learned params/Elo/backtest itself — that's learn_model.py's job, meant to
be run right after. Recognised result-line shapes, one match per line
(round is whatever "Round N" heading most recently preceded the line):
    Cowboys 24 def Roosters 18
    Cowboys 24 d Roosters 18
    Cowboys 24 beat Roosters 18
    Cowboys 24 - 18 Roosters
"""

import argparse
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Team reference data: short code -> canonical name + all known aliases used
# across Zero Tackle / NRL.com text dumps.
# ---------------------------------------------------------------------------
TEAMS = {
    "PEN": {"name": "Panthers", "aliases": ["penrith panthers", "penrith", "panthers"]},
    "SYD": {"name": "Roosters", "aliases": ["sydney roosters", "roosters"]},
    "NZW": {"name": "Warriors", "aliases": ["new zealand warriors", "nz warriors", "warriors"]},
    "CRO": {"name": "Sharks", "aliases": ["cronulla sharks", "cronulla-sutherland", "cronulla", "sharks"]},
    "DOL": {"name": "Dolphins", "aliases": ["the dolphins", "dolphins"]},
    "SOU": {"name": "Rabbitohs", "aliases": ["south sydney rabbitohs", "south sydney", "rabbitohs", "souths"]},
    "NEW": {"name": "Knights", "aliases": ["newcastle knights", "newcastle", "knights"]},
    "NQL": {"name": "Cowboys", "aliases": ["north queensland cowboys", "north queensland", "cowboys"]},
    "MAN": {"name": "Sea Eagles", "aliases": ["manly warringah sea eagles", "manly sea eagles", "manly", "sea eagles"]},
    "CAN": {"name": "Bulldogs", "aliases": ["canterbury-bankstown bulldogs", "canterbury bulldogs", "canterbury", "bulldogs"]},
    "CBR": {"name": "Raiders", "aliases": ["canberra raiders", "canberra", "raiders"]},
    "MEL": {"name": "Storm", "aliases": ["melbourne storm", "melbourne", "storm"]},
    "BRI": {"name": "Broncos", "aliases": ["brisbane broncos", "brisbane", "broncos"]},
    "PAR": {"name": "Eels", "aliases": ["parramatta eels", "parramatta", "eels"]},
    "WST": {"name": "Wests Tigers", "aliases": ["wests tigers", "west tigers", "tigers"]},
    "GLD": {"name": "Titans", "aliases": ["gold coast titans", "gold coast", "titans"]},
    "STI": {"name": "Dragons", "aliases": ["st george illawarra dragons", "st george illawarra", "st. george illawarra", "dragons"]},
}

# Build alias -> short lookup, longest alias first so "sea eagles" beats "eagles".
ALIAS_TO_SHORT = []
for short, info in TEAMS.items():
    names = [info["name"]] + info["aliases"]
    for n in names:
        ALIAS_TO_SHORT.append((n.lower(), short))
ALIAS_TO_SHORT.sort(key=lambda t: -len(t[0]))

# ---------------------------------------------------------------------------
# Static reference data for schema-v3 fields: club colours + host cities.
# Colours copied verbatim from the committed nrl_data.js (source of truth).
# ---------------------------------------------------------------------------
CLUB_COLOUR = {
    "PEN": "#0a0a0a", "SYD": "#e2231a", "NZW": "#231f20", "CRO": "#00a9e0",
    "DOL": "#ee3524", "SOU": "#00954c", "NEW": "#00539b", "NQL": "#002b5c",
    "MAN": "#6f1a3c", "CAN": "#00337f", "CBR": "#8bc53f", "MEL": "#4b2e83",
    "BRI": "#6c1d45", "PAR": "#006eb5", "WST": "#f68b1f", "GLD": "#fbb040",
    "STI": "#e2231a",
}

# Each club's usual home city — used as the fallback for fixture.city when
# the venue name isn't recognised in VENUE_CITY below (e.g. a one-off
# regional/heritage-round venue we haven't seen yet).
TEAM_HOME_CITY = {
    "PEN": "Sydney", "SYD": "Sydney", "NZW": "Auckland", "CRO": "Sydney",
    "DOL": "Brisbane", "SOU": "Sydney", "NEW": "Newcastle", "NQL": "Townsville",
    "MAN": "Sydney", "CAN": "Sydney", "CBR": "Canberra", "MEL": "Melbourne",
    "BRI": "Brisbane", "PAR": "Sydney", "WST": "Sydney", "GLD": "Gold Coast",
    "STI": "Wollongong",
}

# Known venue name (lowercase substring) -> host city. Copied from/aligned
# with the committed nrl_data.js plus other common NRL venues so the parser
# still resolves a sensible city for venues not seen in the sample dumps.
VENUE_CITY = {
    "qld country bank stadium": "Townsville",
    "glen willow oval": "Mudgee",
    "cbus super stadium": "Gold Coast",
    "suncorp stadium": "Brisbane",
    "aami park": "Melbourne",
    "win stadium": "Wollongong",
    "sharks stadium": "Sydney",
    "commbank stadium": "Sydney",
    "bluebet stadium": "Canberra",
    "4 pines park": "Sydney",
    "allianz stadium": "Sydney",
    "accor stadium": "Sydney",
    "belmore sports ground": "Sydney",
    "mcdonald jones stadium": "Newcastle",
    "moreton daily stadium": "Redcliffe",
    "eprod city stadium": "Townsville",
    "browne park": "Rockhampton",
    "allegiant stadium": "Las Vegas",
    "campbelltown stadium": "Sydney",
    "mt smart stadium": "Auckland",
    "go media stadium": "Auckland",
}


def resolve_city(venue, home_short):
    """Best-effort host city for a fixture: match the venue name against
    VENUE_CITY (substring, case-insensitive); fall back to the home team's
    usual city; fall back to "" if even that's unknown."""
    if venue:
        v = venue.lower()
        for key, city in VENUE_CITY.items():
            if key in v:
                return city
    return TEAM_HOME_CITY.get(home_short, "")


def strip_html(text):
    """Turn a raw HTML dump into normalized plain text for regex scanning."""
    text = html.unescape(text)
    # Turn common block/row boundaries into newlines so regex works line-by-line.
    text = re.sub(r"(?i)</(tr|p|div|li|br)\s*>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)<td[^>]*>", " | ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text


def find_short(fragment):
    frag = fragment.lower().strip()
    for alias, short in ALIAS_TO_SHORT:
        if alias == frag:
            return short
    for alias, short in ALIAS_TO_SHORT:
        if alias in frag:
            return short
    return None


# ---------------------------------------------------------------------------
# Ladder parsing
# ---------------------------------------------------------------------------
LADDER_ROW_RE = re.compile(
    r"""
    (?P<name>[A-Za-z][A-Za-z .'\-]{2,30}?)\s*\|?\s*
    (?P<P>\d{1,2})\s*\|?\s*
    (?P<W>\d{1,2})\s*\|?\s*
    (?P<D>\d{1,2})\s*\|?\s*
    (?P<L>\d{1,2})\s*\|?\s*
    (?P<PF>\d{2,4})\s*\|?\s*
    (?P<PA>\d{2,4})\s*\|?\s*
    (?P<Diff>[+-]?\d{1,4})\s*\|?\s*
    (?P<Pts>\d{1,3})
    (?P<form>(?:\s*\|?\s*[WLD]){0,5})?
    """,
    re.VERBOSE,
)


def parse_ladder(raw_text):
    """Return list of team dicts (name, short, colour, P, W, L, PF, PA,
    last5, home, away, news) or [] if the ladder can't be confidently
    parsed. home/away are per-team {P,W,L,PF,PA} dicts or None if the
    Home/Away split tables aren't present on the page."""
    text = strip_html(raw_text)
    teams = {}
    for line in text.split("\n"):
        m = LADDER_ROW_RE.search(line)
        if not m:
            continue
        short = find_short(m.group("name"))
        if not short or short in teams:
            continue
        P, W, D, L = int(m.group("P")), int(m.group("W")), int(m.group("D")), int(m.group("L"))
        PF, PA = int(m.group("PF")), int(m.group("PA"))
        # sanity: played roughly equals W+D+L (allow off-by-1 for byes/misparse)
        if abs((W + D + L) - P) > 2:
            continue
        form = m.group("form") or ""
        letters = re.findall(r"[WLD]", form)
        last5 = letters.count("W") if letters else None
        teams[short] = {
            "name": TEAMS[short]["name"],
            "short": short,
            "colour": CLUB_COLOUR.get(short, "#000000"),
            "P": P, "W": W, "L": L + D, "PF": PF, "PA": PA,
            "last5": last5 if last5 is not None else 0,
        }

    home_splits, away_splits = parse_home_away_splits(raw_text)
    for short, t in teams.items():
        t["home"] = home_splits.get(short)
        t["away"] = away_splits.get(short)
        t["news"] = None  # filled in later from --injuries, if supplied

    return list(teams.values())


# ---------------------------------------------------------------------------
# Home/Away split-table parsing.
# Zero Tackle's ladder page carries separate "Home" and "Away" ladder
# tables below the main combined ladder. Each row is a lighter-weight
# version of the main row (no Diff/Pts/form columns required).
# ---------------------------------------------------------------------------
SPLIT_ROW_RE = re.compile(
    r"""
    (?P<name>[A-Za-z][A-Za-z .'\-]{2,30}?)\s*\|?\s*
    (?P<P>\d{1,2})\s*\|?\s*
    (?P<W>\d{1,2})\s*\|?\s*
    (?P<D>\d{1,2})\s*\|?\s*
    (?P<L>\d{1,2})\s*\|?\s*
    (?P<PF>\d{2,4})\s*\|?\s*
    (?P<PA>\d{2,4})
    """,
    re.VERBOSE,
)

# Matches a heading (HTML tag or bare text line) that introduces the Home
# or Away split table, e.g. <h2>Home</h2>, <h3>Home Ladder</h3>, or a bare
# "Home" / "Away" line once tags have been stripped.
SECTION_HEADING_RE = re.compile(
    r"(?is)(?:<h[1-4][^>]*>\s*(home|away)(?:\s+ladder)?\s*</h[1-4]>"
    r"|<caption[^>]*>\s*(home|away)(?:\s+ladder)?\s*</caption>"
    r"|^\s*(home|away)(?:\s+ladder)?\s*$)"
)


def _find_section_bounds(raw_text, label):
    """Return (start, end) char offsets in raw_text for the table content
    following a Home/Away heading, or None if not found. `end` is the start
    of the next recognised heading, or end-of-text."""
    matches = []
    for m in re.finditer(r"(?i)(?:<h[1-4][^>]*>|<caption[^>]*>)\s*(home|away)(?:\s+ladder)?\s*(?:</h[1-4]>|</caption>)", raw_text):
        matches.append((m.start(), m.end(), m.group(1).lower()))
    if not matches:
        # fall back to bare-line headings (after tag stripping this would be
        # awkward to bound in raw HTML, so only used when no tagged headings
        # exist at all — try a simple text-line heading match on raw_text).
        for m in re.finditer(r"(?im)^[ \t]*(home|away)(?:\s+ladder)?[ \t]*$", raw_text):
            matches.append((m.start(), m.end(), m.group(1).lower()))
    matches.sort(key=lambda x: x[0])
    for idx, (start, end, lbl) in enumerate(matches):
        if lbl != label:
            continue
        content_start = end
        content_end = matches[idx + 1][0] if idx + 1 < len(matches) else len(raw_text)
        return content_start, content_end
    return None


def parse_split_table(section_text):
    """Parse a Home or Away ladder section into {short: {P,W,L,PF,PA}}."""
    text = strip_html(section_text)
    out = {}
    for line in text.split("\n"):
        m = SPLIT_ROW_RE.search(line)
        if not m:
            continue
        short = find_short(m.group("name"))
        if not short or short in out:
            continue
        P, W, D, L = int(m.group("P")), int(m.group("W")), int(m.group("D")), int(m.group("L"))
        PF, PA = int(m.group("PF")), int(m.group("PA"))
        if abs((W + D + L) - P) > 2:
            continue
        out[short] = {"P": P, "W": W, "L": L + D, "PF": PF, "PA": PA}
    return out


def parse_home_away_splits(raw_text):
    """Return (home_splits, away_splits) dicts keyed by short code. Either
    dict is {} if that section couldn't be located/parsed — callers treat
    a missing entry as None (schema allows null)."""
    home_bounds = _find_section_bounds(raw_text, "home")
    away_bounds = _find_section_bounds(raw_text, "away")
    home_splits = parse_split_table(raw_text[home_bounds[0]:home_bounds[1]]) if home_bounds else {}
    away_splits = parse_split_table(raw_text[away_bounds[0]:away_bounds[1]]) if away_bounds else {}
    return home_splits, away_splits


# ---------------------------------------------------------------------------
# Draw / fixtures parsing
# ---------------------------------------------------------------------------
ROUND_RE = re.compile(r"round\s+(\d{1,2})", re.IGNORECASE)
MATCHUP_RE = re.compile(
    r"(?P<home>[A-Za-z][A-Za-z .'\-]{2,30}?)\s+v(?:s)?\.?\s+(?P<away>[A-Za-z][A-Za-z .'\-]{2,30})",
    re.IGNORECASE,
)
VENUE_HINT_RE = re.compile(r"(stadium|park|oval|field|arena|cbus|4pines|allegiant)", re.IGNORECASE)
# Captures "Wed 30 Jul, 7:50pm" style day/date/time strings so they can be
# converted to a real ISO datetime (validate_data.py requires 'kickoff' to be
# a valid ISO datetime when present, so free text alone isn't good enough).
KICKOFF_HINT_RE = re.compile(
    r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\s+(\d{1,2})\s+([A-Za-z]{3,9})\D*?"
    r"(\d{1,2}):(\d{2})\s*([ap]m)",
    re.IGNORECASE,
)
ISO_KICKOFF_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z?")
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def kickoff_to_iso(day, month_str, hour, minute, meridiem, season):
    """Best-effort convert a parsed 'D Mon, H:MMam/pm' fragment into an ISO
    datetime string using the given season year. Returns "" if any part is
    unrecognisable rather than guessing — callers should leave kickoff blank
    in that case instead of inventing a time."""
    month = MONTH_ABBR.get(month_str.lower()[:3])
    if not month:
        return ""
    try:
        hour = int(hour) % 12
        if meridiem.lower() == "pm":
            hour += 12
        dt = datetime.datetime(season, month, int(day), hour, int(minute))
    except ValueError:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_draw(raw_text, season):
    """Return (round_number_or_None, [fixture dicts])."""
    text = strip_html(raw_text)
    lines = [l.strip(" |") for l in text.split("\n") if l.strip(" |")]

    round_num = None
    m = ROUND_RE.search(text)
    if m:
        round_num = int(m.group(1))

    fixtures = []
    seen_teams = set()
    for i, line in enumerate(lines):
        m = MATCHUP_RE.search(line)
        if not m:
            continue
        home_short = find_short(m.group("home"))
        away_short = find_short(m.group("away"))
        if not home_short or not away_short or home_short == away_short:
            continue
        if home_short in seen_teams or away_short in seen_teams:
            continue  # avoid double-counting a team already in this round's list

        venue, kickoff = "", ""
        # scan a small window of following lines for venue/kickoff hints
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j]
            if MATCHUP_RE.search(nxt):
                break
            iso = ISO_KICKOFF_RE.search(nxt)
            hint = KICKOFF_HINT_RE.search(nxt)
            if iso and not kickoff:
                kickoff = iso.group(0)
            elif hint and not kickoff:
                day, month_str, hour, minute, meridiem = hint.groups()
                kickoff = kickoff_to_iso(day, month_str, hour, minute, meridiem, season)
            if VENUE_HINT_RE.search(nxt) and not venue:
                venue = nxt.strip()

        fixtures.append({
            "home": home_short, "away": away_short, "venue": venue,
            "city": resolve_city(venue, home_short), "kickoff": kickoff,
            "odds": None, "weather": None, "h2h": None,
        })
        seen_teams.add(home_short)
        seen_teams.add(away_short)

    return round_num, fixtures


# ---------------------------------------------------------------------------
# Optional inputs: odds, injuries/team-news, weather.
# All are local text dumps (see sources.md / module docstring for format);
# none of these trigger network access — they're just parsed if provided.
# ---------------------------------------------------------------------------
ODDS_LINE_RE = re.compile(
    r"(?P<a>[A-Za-z][A-Za-z .'\-]{2,30}?)\s+v(?:s)?\.?\s+(?P<b>[A-Za-z][A-Za-z .'\-]{2,30}?)\s*:\s*"
    r"(?P<oa>\d+(?:\.\d+)?)\s*/\s*(?P<ob>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def parse_odds(raw_text):
    """Return {frozenset({home_short, away_short}): {short: decimal_odds}}."""
    out = {}
    for line in raw_text.splitlines():
        m = ODDS_LINE_RE.search(line)
        if not m:
            continue
        a_short = find_short(m.group("a"))
        b_short = find_short(m.group("b"))
        if not a_short or not b_short or a_short == b_short:
            continue
        key = frozenset({a_short, b_short})
        out[key] = {a_short: float(m.group("oa")), b_short: float(m.group("ob"))}
    return out


def apply_odds(fixtures, odds_by_pair, mode="full"):
    """Apply freshly-parsed odds to fixtures' `odds` field, evolving it into
    the canonical {"open": {home,away}|None, "close": {home,away}|None}
    shape that enables closing-line-value (CLV) tracking.

    mode="full" (weekly full rebuild, the default): every fixture's `odds`
    starts as None (set by parse_draw). Odds parsed this run are the only
    sighting so far, so both `open` and `close` are set to the same fresh
    values.

    mode="merge" (daily/gameday reactive refresh, see run_merge()):
    fixtures already carry whatever the previous run left — None, the
    legacy flat {home,away} shape, or the open/close shape. For any
    fixture with fresh odds this batch:
      - `open` is set from these odds ONLY if there is no open odds yet
        (first sighting this fixture has ever had = its opening line); an
        existing `open` is NEVER overwritten.
      - `close` is ALWAYS overwritten with the newest parsed odds.
    A legacy flat value from an older run is treated as an existing
    `close` with an unknown `open` (rather than discarded), so upgrading
    an old nrl_data.js doesn't lose its most recent price.
    """
    for f in fixtures:
        key = frozenset({f["home"], f["away"]})
        pair = odds_by_pair.get(key)
        if not pair:
            continue
        home_odds, away_odds = pair.get(f["home"]), pair.get(f["away"])
        if home_odds is None or away_odds is None:
            continue
        fresh = {"home": home_odds, "away": away_odds}

        if mode == "full":
            f["odds"] = {"open": dict(fresh), "close": dict(fresh)}
            continue

        existing = f.get("odds")
        if isinstance(existing, dict) and ("open" in existing or "close" in existing):
            open_odds = existing.get("open")
        elif isinstance(existing, dict) and "home" in existing and "away" in existing:
            # Legacy flat shape from a pre-CLV run: it's a known close price
            # with an unrecorded open, not a value to discard.
            open_odds = None
        else:
            open_odds = None

        if open_odds is None:
            open_odds = dict(fresh)  # first sighting for this fixture -> open
        f["odds"] = {"open": open_odds, "close": dict(fresh)}


def parse_line_dump(raw_text, resolve_key):
    """Shared parser for 'Label: free text' line dumps (injuries, weather).
    `resolve_key` maps the label fragment before ':' to a dict key (team
    short code, or a normalised city name); lines that don't resolve are
    skipped. Later lines for the same key overwrite earlier ones."""
    out = {}
    for line in raw_text.splitlines():
        if ":" not in line:
            continue
        label, _, rest = line.partition(":")
        key = resolve_key(label.strip())
        rest = rest.strip()
        if key and rest:
            out[key] = rest
    return out


def parse_injuries(raw_text):
    """Return {short: news_text}."""
    return parse_line_dump(raw_text, find_short)


def parse_weather(raw_text):
    """Return {city_lower: weather_text}."""
    return parse_line_dump(raw_text, lambda s: s.strip().lower() or None)


def apply_injuries(teams, news_by_short):
    for t in teams:
        if t["short"] in news_by_short:
            t["news"] = news_by_short[t["short"]]


def apply_weather(fixtures, weather_by_city):
    for f in fixtures:
        city = (f.get("city") or "").strip().lower()
        if city in weather_by_city:
            f["weather"] = weather_by_city[city]


# ---------------------------------------------------------------------------
# Results / completed-scores parsing — feeds the learning-loop memory kept
# in nrl_learned.js. Network-free, best-effort: lines that don't match a
# recognised "final score" shape are simply skipped rather than guessed.
# ---------------------------------------------------------------------------
RESULT_ROUND_RE = re.compile(r"round\s+(\d{1,2})", re.IGNORECASE)

# "Cowboys 24 def Roosters 18" / "Cowboys 24 d Roosters 18" /
# "Cowboys 24 beat Roosters 18" / "Cowboys 24 - 18 Roosters" (single dash,
# score attached to the first-named team's side of the separator).
RESULT_LINE_RE = re.compile(
    r"(?P<a>[A-Za-z][A-Za-z .'\-]{2,30}?)\s+(?P<sa>\d{1,3})\s*"
    r"(?:def\.?|d\.?|beat|-|–)\s*"
    r"(?P<b>[A-Za-z][A-Za-z .'\-]{2,30}?)\s+(?P<sb>\d{1,3})\b",
    re.IGNORECASE,
)
# Fallback shape: "Cowboys 24-18 Roosters" (score-score glued together
# between the two team names, no def/beat word).
RESULT_LINE_RE2 = re.compile(
    r"(?P<a>[A-Za-z][A-Za-z .'\-]{2,30}?)\s+(?P<sa>\d{1,3})\s*[-–]\s*(?P<sb>\d{1,3})\s+"
    r"(?P<b>[A-Za-z][A-Za-z .'\-]{2,30})",
    re.IGNORECASE,
)


def parse_results(raw_text):
    """Return a list of finished-game dicts {round, home, away, hs, as}
    parsed from a page dump that carries completed match scores (the draw
    page once games are final, or a dedicated results/scores page passed
    via --results). Best-effort and network-free: the round number is
    whatever "Round N" heading most recently preceded the line in the text;
    lines before any round heading, or that don't resolve both team names,
    are skipped. `home`/`away` reflect the order teams appear in the
    line (first-named = home) — the convention used by the sample sources
    in sources.md; genuinely ambiguous sources should be normalised to that
    order before saving the dump."""
    text = strip_html(raw_text)
    lines = [l.strip(" |") for l in text.split("\n") if l.strip(" |")]

    out = []
    current_round = None
    for line in lines:
        m = RESULT_ROUND_RE.search(line)
        if m:
            current_round = int(m.group(1))
            continue

        m = RESULT_LINE_RE.search(line) or RESULT_LINE_RE2.search(line)
        if not m or current_round is None:
            continue
        a_short = find_short(m.group("a"))
        b_short = find_short(m.group("b"))
        if not a_short or not b_short or a_short == b_short:
            continue
        try:
            hs, aw = int(m.group("sa")), int(m.group("sb"))
        except (TypeError, ValueError):
            continue
        out.append({"round": current_round, "home": a_short, "away": b_short, "hs": hs, "as": aw})
    return out


# ---------------------------------------------------------------------------
# Learning-loop memory (nrl_learned.js `results` list) — append-only,
# deduped on (round, home, away), never deleted. learn_model.py owns
# re-fitting params/elo/backtest from this memory; this script only ever
# grows the `results` list.
# ---------------------------------------------------------------------------
DEFAULT_LEARNED_PARAMS = {"homeAdv": 4.0, "logisticScale": 400.0, "oddsWeight": 0.5, "eloK": 20, "eloHGA": 50}


def load_learned(path):
    """Load an existing nrl_learned.js `window.NRL_LEARNED = {...};` file.
    Raises on any failure (missing file, unparsable JS/JSON, or a shape
    without a 'results' list) — callers must NOT write anything if this
    raises, so a bad/missing memory file never destroys good history."""
    text = Path(path).read_text(encoding="utf-8")
    _body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))
    json_text = _body.split("=", 1)[1].rsplit(";", 1)[0]
    data = json.loads(json_text)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("missing/invalid 'results' list")
    return data


def emit_learned_js(data, out_path, note=""):
    body = json.dumps(data, indent=2, ensure_ascii=False)
    js = (
        "// Auto-generated / appended by parse_nrl.py + learn_model.py — DO NOT hand-edit\n"
        "// (edits will be overwritten next run). This is the LEARNING LOOP's permanent\n"
        "// memory: `results` is an append-only match log (never deleted, deduped on\n"
        "// round+home+away) that parse_nrl.py appends newly-finished games to on every\n"
        "// run; learn_model.py re-fits homeAdv/Elo/eloK/eloHGA/logisticScale/oddsWeight\n"
        "// from it and rewrites this file, appending one {date,games,brier} history\n"
        "// entry per run. See sources.md ('Learning loop') for details.\n"
        + (f"// {note}\n" if note else "")
        + f"window.NRL_LEARNED = {body};\n"
    )
    # Atomic write: write to a temp file then rename, so a concurrent/interrupted
    # run can never leave a half-written file that clobbers good data.
    _tmp = Path(str(out_path) + ".tmp")
    _tmp.write_text(js, encoding="utf-8")
    os.replace(_tmp, out_path)


def append_finished_results(learned_path, new_results):
    """Append newly-parsed finished games to the nrl_learned.js results
    memory, deduped on (round, home, away). Never deletes existing entries.
    If the existing file is present but unparseable, ABORTS without writing
    (returns -1) — a corrupt learning-loop file must never silently lose
    history. If the file doesn't exist yet, creates a minimal placeholder
    shell (conservative defaults, lowConfidence=True) that learn_model.py
    will properly re-fit on its next run. Returns the number of NEW games
    appended (0 if none/nothing to do)."""
    path = Path(learned_path)
    data = None
    if path.exists():
        try:
            data = load_learned(path)
        except Exception as e:
            print(f"[parse_nrl] WARNING: {path} exists but is unparseable ({e}) — "
                  "learning-loop memory NOT touched this run.", file=sys.stderr)
            return -1

    if not new_results:
        return 0

    existing = data["results"] if data else []
    seen = {(r["round"], r["home"], r["away"]) for r in existing}
    added = 0
    for r in new_results:
        key = (r["round"], r["home"], r["away"])
        if key in seen:
            continue
        existing.append({"round": r["round"], "home": r["home"], "away": r["away"], "hs": r["hs"], "as": r["as"]})
        seen.add(key)
        added += 1

    if added == 0:
        return 0

    if data is None:
        data = {
            "updated": datetime.date.today().isoformat(),
            "gamesLearned": len(existing),
            "lowConfidence": True,
            "params": dict(DEFAULT_LEARNED_PARAMS),
            "elo": {short: 1500 for short in TEAMS},
            "backtest": {"games": 0, "brier": None, "logloss": None, "hit": None, "marketBrier": None},
            "history": [],
            "results": existing,
        }
    else:
        data["results"] = existing
        data["gamesLearned"] = len(existing)

    emit_learned_js(
        data, path,
        note="parse_nrl.py appended new finished-game results this run — "
             "run learn_model.py next to re-fit params/elo/backtest from the grown memory.",
    )
    return added


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(teams, fixtures):
    errors = []
    if len(teams) != 17:
        errors.append(f"expected 17 teams, got {len(teams)}")
    shorts = {t["short"] for t in teams}
    if len(shorts) != len(teams):
        errors.append("duplicate team shorts detected")
    for t in teams:
        if t["PF"] < 0 or t["PA"] < 0 or t["P"] <= 0:
            errors.append(f"implausible stats for {t['short']}")
        if not (0 <= t["last5"] <= 5):
            errors.append(f"last5 out of range for {t['short']}")

    seen_in_round = set()
    for f in fixtures:
        if f["home"] not in shorts or f["away"] not in shorts:
            errors.append(f"fixture references unknown team: {f}")
        if f["home"] in seen_in_round or f["away"] in seen_in_round:
            errors.append(f"team appears twice in round fixtures: {f}")
        seen_in_round.add(f["home"])
        seen_in_round.add(f["away"])
    return errors


def compute_bye(teams, fixtures):
    shorts = {t["short"] for t in teams}
    playing = set()
    for f in fixtures:
        playing.add(f["home"])
        playing.add(f["away"])
    return sorted(shorts - playing)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def emit_js(data, out_path):
    body = json.dumps(data, indent=2, ensure_ascii=False)
    js = (
        "// Auto-generated by parse_nrl.py — DO NOT hand-edit "
        "(edits will be overwritten next run).\n"
        "// To regenerate: python3 parse_nrl.py --ladder ladder_dump.html "
        "--draw draw_dump.html --out nrl_data.js --season 2026 --source zerotackle.com "
        "[--odds odds_dump.txt] [--injuries injuries_dump.txt] [--weather weather_dump.txt]\n"
        "// (see sources.md for where to fetch fresh dumps).\n"
        f"// Data current to end of Round {data['round'] - 1}, {data['season']}.\n"
        "// Schema v3: teams add colour/home/away/news; fixtures add city/odds/weather/h2h.\n"
        "// fixture.odds now carries {open,close} decimal-odds snapshots for CLV\n"
        "// (closing-line-value); the legacy flat {home,away} shape and null are\n"
        "// still accepted everywhere for backward compatibility.\n"
        "// Time-sensitive fields (odds, weather, news) stay null unless the optional\n"
        "// --odds/--injuries/--weather dumps are supplied that week.\n"
        f"window.NRL_DATA = {body};\n"
    )
    # Atomic write: write to a temp file then rename, so a concurrent/interrupted
    # run can never leave a half-written file that clobbers good data.
    _tmp = Path(str(out_path) + ".tmp")
    _tmp.write_text(js, encoding="utf-8")
    os.replace(_tmp, out_path)


def load_existing_data(path):
    """Load and JSON-parse an existing `window.NRL_DATA = {...};` file for
    merge mode. Raises on any failure (missing file, unparsable JS/JSON,
    or a shape that doesn't look like a real NRL_DATA object) — callers
    must NOT write anything if this raises, so a bad/missing existing file
    never destroys good weekly data."""
    text = Path(path).read_text(encoding="utf-8")
    _body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))
    json_text = _body.split("=", 1)[1].rsplit(";", 1)[0]
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("parsed content is not a JSON object")
    if not isinstance(data.get("teams"), list) or not isinstance(data.get("fixtures"), list):
        raise ValueError("missing/invalid 'teams' or 'fixtures' list")
    return data


def run_merge(args):
    """DAILY reactive-merge mode: load an already-built nrl_data.js and
    refresh ONLY the fast-moving fields (fixture.odds, team.news,
    fixture.weather, and the top-level `newsUpdated` stamp) from whatever
    optional dumps are supplied. Everything else — `updated`, `round`,
    ladder numbers, home/away splits, the fixtures list itself — is left
    byte-for-byte as loaded. Never touches the network; parses local dumps
    only, same as the weekly full-rebuild helpers it reuses."""
    in_path = Path(args.in_file or args.out or "nrl_data.js")

    try:
        data = load_existing_data(in_path)
    except Exception as e:
        print(f"[parse_nrl] MERGE ERROR: could not read/parse existing data file "
              f"{in_path}: {e}", file=sys.stderr)
        print("[parse_nrl] MERGE ABORTED — nothing written, existing file (if any) left untouched.",
              file=sys.stderr)
        sys.exit(1)

    teams = data["teams"]
    fixtures = data["fixtures"]

    n_odds = n_injuries = n_weather = 0

    if args.odds:
        odds_path = Path(args.odds)
        if odds_path.exists():
            odds_by_pair = parse_odds(odds_path.read_text(encoding="utf-8", errors="ignore"))
            apply_odds(fixtures, odds_by_pair, mode="merge")
            n_odds = len(odds_by_pair)
            print(f"[parse_nrl] MERGE: applied odds (open/close) for {n_odds} matchup(s) from {odds_path}")
        else:
            print(f"[parse_nrl] WARNING: --odds file not found: {odds_path}", file=sys.stderr)

    if args.injuries:
        injuries_path = Path(args.injuries)
        if injuries_path.exists():
            news_by_short = parse_injuries(injuries_path.read_text(encoding="utf-8", errors="ignore"))
            apply_injuries(teams, news_by_short)
            n_injuries = len(news_by_short)
            print(f"[parse_nrl] MERGE: applied team news for {n_injuries} team(s) from {injuries_path}")
        else:
            print(f"[parse_nrl] WARNING: --injuries file not found: {injuries_path}", file=sys.stderr)

    if args.weather:
        weather_path = Path(args.weather)
        if weather_path.exists():
            weather_by_city = parse_weather(weather_path.read_text(encoding="utf-8", errors="ignore"))
            apply_weather(fixtures, weather_by_city)
            n_weather = len(weather_by_city)
            print(f"[parse_nrl] MERGE: applied weather for {n_weather} city/cities from {weather_path}")
        else:
            print(f"[parse_nrl] WARNING: --weather file not found: {weather_path}", file=sys.stderr)

    news_updated = args.updated or datetime.date.today().isoformat()
    data["newsUpdated"] = news_updated
    # NOTE: `updated`, `round`, ladder numbers (P/W/L/PF/PA/last5/home/away)
    # and the fixtures list are all left exactly as loaded above — only the
    # reactive fields mutated in place (odds/news/weather) and newsUpdated
    # change.

    # Learning-loop memory: scan the draw dump (if present) and/or an
    # explicit --results dump for newly-finished games and append them to
    # nrl_learned.js. This is independent of the nrl_data.js merge above —
    # it never touches `data`/`out_path`.
    finished = []
    draw_path = Path(args.draw) if args.draw else None
    if draw_path and draw_path.exists():
        finished += parse_results(draw_path.read_text(encoding="utf-8", errors="ignore"))
    if args.results:
        results_path = Path(args.results)
        if results_path.exists():
            finished += parse_results(results_path.read_text(encoding="utf-8", errors="ignore"))
        else:
            print(f"[parse_nrl] WARNING: --results file not found: {results_path}", file=sys.stderr)
    if finished:
        added = append_finished_results(args.learned, finished)
        if added > 0:
            print(f"[parse_nrl] MERGE: learning-loop memory: appended {added} new finished game(s) "
                  f"to {args.learned} (run learn_model.py next)")
        elif added == 0:
            print("[parse_nrl] MERGE: learning-loop memory: no new finished games to append")

    out_path = Path(args.out) if args.out else in_path
    emit_js(data, out_path)
    print(f"[parse_nrl] MERGE wrote {out_path} (newsUpdated={news_updated})")
    print(f"MERGED: odds={n_odds} injuries={n_injuries} weather={n_weather} newsUpdated={news_updated}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ladder", default="ladder_dump.html", help="Zero Tackle ladder page dump")
    ap.add_argument("--draw", default="draw_dump.html", help="NRL.com draw page dump")
    ap.add_argument("--out", default=None, help="output nrl_data.js path (default: nrl_data.js for a "
                    "full rebuild, or the --in file itself for --merge)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--source", default="zerotackle.com")
    ap.add_argument("--updated", default=None, help="ISO date override; defaults to today")
    ap.add_argument("--odds", default=None, help="optional local odds dump (see sources.md)")
    ap.add_argument("--injuries", default=None, help="optional local injuries/team-news dump")
    ap.add_argument("--weather", default=None, help="optional local weather dump")
    ap.add_argument("--results", default=None,
                     help="optional local results/completed-scores dump (see sources.md); the "
                          "--draw dump is also always scanned for finished-game scores")
    ap.add_argument("--learned", default="nrl_learned.js",
                     help="learning-loop memory file to append newly-finished results to "
                          "(default: nrl_learned.js)")
    ap.add_argument("--merge", action="store_true",
                     help="DAILY reactive-refresh mode: load an existing nrl_data.js (see --in) and "
                          "update ONLY odds/news/weather + newsUpdated, leaving the ladder, splits, "
                          "round and fixtures list untouched. No ladder/draw rebuild happens.")
    ap.add_argument("--in", dest="in_file", default=None,
                     help="existing nrl_data.js to load for --merge (default: --out, or ./nrl_data.js)")
    args = ap.parse_args()

    if args.merge:
        run_merge(args)
        return

    out_path_default = args.out or "nrl_data.js"
    args.out = out_path_default

    updated = args.updated or datetime.date.today().isoformat()

    ladder_path = Path(args.ladder)
    draw_path = Path(args.draw)

    teams = []
    if ladder_path.exists():
        teams = parse_ladder(ladder_path.read_text(encoding="utf-8", errors="ignore"))
        print(f"[parse_nrl] parsed {len(teams)} teams from {ladder_path}")
    else:
        print(f"[parse_nrl] WARNING: ladder file not found: {ladder_path}", file=sys.stderr)

    round_num, fixtures = None, []
    draw_raw_text = ""
    if draw_path.exists():
        draw_raw_text = draw_path.read_text(encoding="utf-8", errors="ignore")
        round_num, fixtures = parse_draw(draw_raw_text, args.season)
        print(f"[parse_nrl] parsed round={round_num}, {len(fixtures)} fixtures from {draw_path}")
    else:
        print(f"[parse_nrl] WARNING: draw file not found: {draw_path}", file=sys.stderr)

    # Learning-loop memory: scan the draw dump and/or an explicit --results
    # dump for newly-finished games and append them to nrl_learned.js. This
    # never touches nrl_data.js and runs regardless of whether the rest of
    # this full rebuild succeeds in producing a fresh nrl_data.js.
    finished = list(parse_results(draw_raw_text)) if draw_raw_text else []
    if args.results:
        results_path = Path(args.results)
        if results_path.exists():
            finished += parse_results(results_path.read_text(encoding="utf-8", errors="ignore"))
        else:
            print(f"[parse_nrl] WARNING: --results file not found: {results_path}", file=sys.stderr)
    if finished:
        added = append_finished_results(args.learned, finished)
        if added > 0:
            print(f"[parse_nrl] learning-loop memory: appended {added} new finished game(s) "
                  f"to {args.learned} (run learn_model.py next)")
        elif added == 0:
            print("[parse_nrl] learning-loop memory: no new finished games to append")

    # Cross-check: if both sources present, sanity-check team count / points.
    if teams and len(teams) != 17:
        print(f"[parse_nrl] WARNING: ladder source only yielded {len(teams)}/17 teams", file=sys.stderr)

    # Degrade gracefully: if fixtures couldn't be parsed but an existing
    # nrl_data.js is present, keep its fixtures/round/bye rather than
    # emitting an empty round.
    out_path = Path(args.out)
    if not fixtures and out_path.exists():
        try:
            old_text = out_path.read_text(encoding="utf-8")
            _ob = "\n".join(l for l in old_text.splitlines() if not l.lstrip().startswith("//"))
            old_json = _ob.split("=", 1)[1].rsplit(";", 1)[0]
            old = json.loads(old_json)
            fixtures = old.get("fixtures", [])
            round_num = round_num or old.get("round")
            print("[parse_nrl] draw missing — reused fixtures/round from existing nrl_data.js", file=sys.stderr)
        except Exception:
            pass

    if not teams:
        print("[parse_nrl] ERROR: no ladder data available — cannot build a valid nrl_data.js. Aborting.", file=sys.stderr)
        sys.exit(1)

    errors = validate(teams, fixtures)
    if errors:
        print("[parse_nrl] VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # Optional weekly-refresh inputs: odds / injuries / weather. Each is
    # entirely best-effort — if the flag isn't passed, or the file doesn't
    # exist/parse, the corresponding fields simply stay null (set above).
    if args.odds:
        odds_path = Path(args.odds)
        if odds_path.exists():
            odds_by_pair = parse_odds(odds_path.read_text(encoding="utf-8", errors="ignore"))
            apply_odds(fixtures, odds_by_pair, mode="full")
            print(f"[parse_nrl] applied odds (open+close) for {len(odds_by_pair)} matchup(s) from {odds_path}")
        else:
            print(f"[parse_nrl] WARNING: --odds file not found: {odds_path}", file=sys.stderr)

    if args.injuries:
        injuries_path = Path(args.injuries)
        if injuries_path.exists():
            news_by_short = parse_injuries(injuries_path.read_text(encoding="utf-8", errors="ignore"))
            apply_injuries(teams, news_by_short)
            print(f"[parse_nrl] applied team news for {len(news_by_short)} team(s) from {injuries_path}")
        else:
            print(f"[parse_nrl] WARNING: --injuries file not found: {injuries_path}", file=sys.stderr)

    if args.weather:
        weather_path = Path(args.weather)
        if weather_path.exists():
            weather_by_city = parse_weather(weather_path.read_text(encoding="utf-8", errors="ignore"))
            apply_weather(fixtures, weather_by_city)
            print(f"[parse_nrl] applied weather for {len(weather_by_city)} city/cities from {weather_path}")
        else:
            print(f"[parse_nrl] WARNING: --weather file not found: {weather_path}", file=sys.stderr)

    bye_teams = compute_bye(teams, fixtures) if fixtures else []
    data = {
        "updated": updated,
        "season": args.season,
        "round": round_num or 1,
        "source": args.source,
        "teams": teams,
        "fixtures": fixtures,
        "byeTeams": bye_teams,
    }

    emit_js(data, out_path)
    print(f"[parse_nrl] wrote {out_path} — {len(teams)} teams, round {data['round']}, "
          f"{len(fixtures)} fixtures, bye={bye_teams}")


if __name__ == "__main__":
    main()
