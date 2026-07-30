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

    fixture = { home, away, venue, city, kickoff, tz,
                odds: {open:{home,away}|null, close:{home,away}|null}
                      | {home,away} (legacy flat, still accepted) | null,
                weather: string | null, h2h: null }

`fixture.kickoff` is ISO WITH a UTC offset and `fixture.tz` is the IANA zone
of the ground (Australia/Brisbane for Townsville, Australia/Sydney for Sydney,
Pacific/Auckland for Mt Smart, ...). A naive kickoff string is read by
Date.parse() as the READER's local wall clock, so a phone outside AEST renders
a Townsville game at the wrong time with no warning. Queensland doesn't observe
daylight saving, which is why the offset is derived per-ground via zoneinfo
rather than hardcoded to +10:00.

The payload also carries `generatedAt`, `changes[]` and `changesSince` — the
"what changed today" feed described in DESIGN_SPEC.md §2.1. It is a ROLLING
window (default 36h), not a per-run diff, because the workflow runs every four
hours and Josh should still see at breakfast what moved overnight.

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

WEATHER (optional, --weather): plain text, one line per city or per
city+game-day:
    Townsville|2026-07-30: Thu 30 Jul: 26°C, 14% rain chance, overcast
    Townsville: Fine, 26C, light breeze.
The dated form is that city's forecast for a game's LOCAL date and is matched
to each fixture by resolved `city` + the date of its kick-off; the dateless
form is the legacy city-wide fallback. Cities with no line get `weather: null`.

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

# --- Home timezone for date stamping ---------------------------------------
# GitHub's runners are UTC. The 6am-Sydney cron fires at ~20:00 UTC the PREVIOUS
# day, so datetime.date.today() there returns yesterday and the site shows a date
# one day behind. Stamp dates in the app's real home timezone instead.
try:
    from zoneinfo import ZoneInfo
    _SYD_TZ = ZoneInfo("Australia/Sydney")
except Exception:
    ZoneInfo = None
    _SYD_TZ = None

def local_today_iso():
    """Today's date in Australia/Sydney as ISO YYYY-MM-DD (UTC-safe).
    Falls back to the runner's local date if tz data is unavailable."""
    if _SYD_TZ is not None:
        return datetime.datetime.now(_SYD_TZ).date().isoformat()
    return datetime.date.today().isoformat()

def now_local():
    """Timezone-AWARE 'now' in Australia/Sydney. The change feed's rolling
    window compares timestamps across runs, so a naive datetime here would
    blow up the moment one run stamped an offset and another didn't."""
    if _SYD_TZ is not None:
        return datetime.datetime.now(_SYD_TZ)
    return datetime.datetime.now(datetime.timezone.utc)
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
    "CRO": {"name": "Sharks", "aliases": ["cronulla-sutherland sharks", "cronulla sutherland sharks",
                                          "cronulla sharks", "cronulla-sutherland", "cronulla", "sharks"]},
    "DOL": {"name": "Dolphins", "aliases": ["redcliffe dolphins", "the dolphins", "dolphins"]},
    "SOU": {"name": "Rabbitohs", "aliases": ["south sydney rabbitohs", "south sydney", "rabbitohs", "souths"]},
    "NEW": {"name": "Knights", "aliases": ["newcastle knights", "newcastle", "knights"]},
    "NQL": {"name": "Cowboys", "aliases": ["north queensland cowboys", "north queensland", "cowboys"]},
    "MAN": {"name": "Sea Eagles", "aliases": ["manly-warringah sea eagles", "manly warringah sea eagles",
                                             "manly sea eagles", "manly", "sea eagles"]},
    "CAN": {"name": "Bulldogs", "aliases": ["canterbury-bankstown bulldogs", "canterbury bankstown bulldogs",
                                            "canterbury bulldogs", "canterbury", "bulldogs"]},
    "CBR": {"name": "Raiders", "aliases": ["canberra raiders", "canberra", "raiders"]},
    "MEL": {"name": "Storm", "aliases": ["melbourne storm", "melbourne", "storm"]},
    "BRI": {"name": "Broncos", "aliases": ["brisbane broncos", "brisbane", "broncos"]},
    "PAR": {"name": "Eels", "aliases": ["parramatta eels", "parramatta", "eels"]},
    "WST": {"name": "Wests Tigers", "aliases": ["wests tigers", "west tigers", "tigers"]},
    "GLD": {"name": "Titans", "aliases": ["gold coast titans", "gold coast", "titans"]},
    "STI": {"name": "Dragons", "aliases": ["st. george illawarra dragons", "st george-illawarra dragons",
                                           "st george illawarra dragons", "st george illawarra",
                                           "st. george illawarra", "dragons"]},
}
# The longer full-club-name aliases above exist for The Odds API, which names teams
# in full ("Cronulla Sutherland Sharks", "Canterbury Bankstown Bulldogs" — often
# without the hyphen the club itself uses). They all used to resolve anyway, but only
# via find_short()'s loose substring pass; an exact alias is deterministic and cheap.
# Add new source names HERE — never build a second mapping in a fetcher (GOTCHAS.md).

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
    "ocean protect stadium": "Sydney",     # Cronulla's current naming-rights name
    "pointsbet stadium": "Sydney",         # ditto, earlier sponsor
    "queensland country bank stadium": "Townsville",
    "industree group stadium": "Gosford",
    "netstrata jubilee stadium": "Sydney",
    "leichhardt oval": "Sydney",
    "kogarah": "Sydney",
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


# Host city -> IANA timezone for the GROUND. The front-end needs this (and an ISO
# kickoff carrying a real UTC offset) because Date.parse() reads a naive string as
# the READER's local wall clock — a phone in London would render a Townsville 7:50pm
# game as 7:50pm BST with no warning.
#
# Do NOT collapse this to a single "+10:00": Queensland does not observe daylight
# saving, so Townsville/Brisbane/Gold Coast/Redcliffe/Rockhampton are +10:00 all year
# while Sydney/Melbourne swing to +11:00 in AEDT. A hardcoded offset is wrong for
# roughly half the season on one side or the other.
CITY_TZ = {
    "sydney": "Australia/Sydney",
    "newcastle": "Australia/Sydney",
    "wollongong": "Australia/Sydney",
    "canberra": "Australia/Sydney",
    "mudgee": "Australia/Sydney",
    "gosford": "Australia/Sydney",
    "bathurst": "Australia/Sydney",
    "wagga wagga": "Australia/Sydney",
    "dubbo": "Australia/Sydney",
    "tamworth": "Australia/Sydney",
    "coffs harbour": "Australia/Sydney",
    "brisbane": "Australia/Brisbane",
    "gold coast": "Australia/Brisbane",
    "townsville": "Australia/Brisbane",
    "redcliffe": "Australia/Brisbane",
    "rockhampton": "Australia/Brisbane",
    "cairns": "Australia/Brisbane",
    "mackay": "Australia/Brisbane",
    "toowoomba": "Australia/Brisbane",
    "sunshine coast": "Australia/Brisbane",
    "melbourne": "Australia/Melbourne",
    "geelong": "Australia/Melbourne",
    "adelaide": "Australia/Adelaide",
    "perth": "Australia/Perth",
    "darwin": "Australia/Darwin",
    "auckland": "Pacific/Auckland",
    "wellington": "Pacific/Auckland",
    "christchurch": "Pacific/Auckland",
    "dunedin": "Pacific/Auckland",
    "port moresby": "Pacific/Port_Moresby",
    "las vegas": "America/Los_Angeles",
}
DEFAULT_TZ = "Australia/Sydney"   # the NRL draw is published in AEST/AEDT


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


def resolve_tz(city, home_short):
    """IANA timezone name for the ground. Falls back to the home club's usual
    city, then to Sydney (stating the assumption beats a silent wrong answer)."""
    for candidate in (city, TEAM_HOME_CITY.get(home_short)):
        key = (candidate or "").strip().lower()
        if key in CITY_TZ:
            return CITY_TZ[key]
    return DEFAULT_TZ


def _zone(tz_name):
    """ZoneInfo for a name, or None if tzdata isn't available on this box."""
    if ZoneInfo is None or not tz_name:
        return None
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return None


def utc_iso_to_local(utc_iso, tz_name):
    """'2026-07-30T09:50:00Z' + 'Australia/Brisbane' -> '2026-07-30T19:50:00+10:00'.

    Returns "" if the input isn't a parseable instant. If tzdata is missing the
    UTC form is returned unchanged — still a correct instant with an explicit
    offset, which is the property the front-end actually depends on."""
    if not utc_iso:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(str(utc_iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    zone = _zone(tz_name)
    if zone is None:
        return dt.astimezone(datetime.timezone.utc).isoformat()
    return dt.astimezone(zone).isoformat()


def localise_naive_iso(naive_iso, tz_name):
    """A naive '2026-07-30T19:50:00' is a WALL time at the ground. Attach the
    ground's real offset so the front-end (and validate_data.py) get an instant
    instead of an ambiguous string. Already-offset strings pass through."""
    if not naive_iso:
        return ""
    s = str(naive_iso)
    if re.search(r"(?:[Zz]|[+-]\d{2}:?\d{2})$", s):
        return s
    try:
        dt = datetime.datetime.fromisoformat(s)
    except ValueError:
        return s
    if dt.tzinfo is not None:
        return dt.isoformat()
    zone = _zone(tz_name) or _SYD_TZ
    if zone is None:
        return s
    return dt.replace(tzinfo=zone).isoformat()


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


def norm_name(s):
    """Canonical player-name key. MUST stay byte-identical in behaviour to
    normName() in nrl-tipping-guide.html — lowercase, strip accents, keep
    apostrophes and hyphens, collapse whitespace. If the two drift, every
    nrl_players.js lookup silently falls through to the fringe fallback.

    Lives here (not in cloud_fetch.py) so there is exactly ONE Python copy;
    cloud_fetch.py imports it."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z\s'-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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
# Draw metadata (--draw-meta, default draw_meta.json) — venue / city / kick-off.
#
# WHY A STRUCTURED SIDECAR AND NOT MORE PROSE IN draw_dump.html:
# parse_draw() above scans the lines *after* a matchup line for anything that
# looks like a venue ("...Stadium") or a time ("Thu 30 Jul, 7:50pm"). That works
# only if some upstream step happens to render those strings in that order, and
# cloud_fetch.py's emit_draw() never did — which is exactly why every fixture
# shipped venue:"" and kickoff:"" for months. GOTCHAS.md's repeated lesson on
# this project is to trust structured data over a rendered-text illusion, so the
# kick-off and venue now travel as JSON straight from nrl.com's own draw payload,
# with the prose scanner kept only as a fallback for a hand-made dump.
# ---------------------------------------------------------------------------
def parse_draw_meta(raw_text):
    """Parse a draw_meta.json sidecar. Returns {} on any problem — this feed is
    best-effort and must never block a publish."""
    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("fixtures"), dict):
        return {}
    return data


def apply_draw_meta(fixtures, meta, round_num):
    """Fill venue / city / kickoff / tz from the structured draw metadata.

    Keyed on "HOME-AWAY" short codes, with a home/away-agnostic fallback so a
    disagreement about which side is home doesn't silently drop the venue.
    Skipped entirely when the metadata is for a different round than the one
    being built — stale metadata is worse than none."""
    if not meta:
        return 0
    meta_round = meta.get("round")
    if round_num and meta_round and int(meta_round) != int(round_num):
        print(f"[parse_nrl] WARNING: draw metadata is for round {meta_round} but this build is "
              f"round {round_num} — ignoring it (venue/kick-off will fall back).", file=sys.stderr)
        return 0
    by_key = meta.get("fixtures") or {}
    by_pair = {}
    for key, val in by_key.items():
        parts = str(key).split("-")
        if len(parts) == 2:
            by_pair.setdefault(frozenset(parts), val)
    applied = 0
    for f in fixtures:
        rec = by_key.get(f"{f['home']}-{f['away']}") or by_pair.get(frozenset((f["home"], f["away"])))
        if not isinstance(rec, dict):
            continue
        venue = (rec.get("venue") or "").strip()
        city = (rec.get("city") or "").strip()
        if venue:
            f["venue"] = venue
        if not city:
            city = resolve_city(f.get("venue") or "", f["home"])
        if city:
            f["city"] = city
        tz_name = (rec.get("tz") or "").strip() or resolve_tz(f.get("city"), f["home"])
        f["tz"] = tz_name
        kickoff = utc_iso_to_local(rec.get("kickoffUtc"), tz_name)
        if kickoff:
            f["kickoff"] = kickoff
        applied += 1
    return applied


def finalise_fixture_times(fixtures):
    """Guarantee every fixture carries a `tz` and, when it has a kick-off at all,
    an ISO string with a real UTC offset. Runs after every other source so it also
    repairs the naive strings the prose scanner produces and any naive value
    inherited from an older nrl_data.js."""
    for f in fixtures:
        if not f.get("city"):
            f["city"] = resolve_city(f.get("venue") or "", f.get("home"))
        tz_name = (f.get("tz") or "").strip() or resolve_tz(f.get("city"), f.get("home"))
        f["tz"] = tz_name
        if f.get("kickoff"):
            f["kickoff"] = localise_naive_iso(f["kickoff"], tz_name)


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
    """Return {key: weather_text} where key is either "city" (legacy city-wide
    line) or "city|YYYY-MM-DD" (that city's forecast for a game's LOCAL date —
    cloud_fetch emits one per game-day since 2026-07-30). Both shapes come
    through the same lowercasing pass; apply_weather() prefers the dated one."""
    return parse_line_dump(raw_text, lambda s: s.strip().lower() or None)


def apply_injuries(teams, news_by_short):
    for t in teams:
        if t["short"] in news_by_short:
            t["news"] = news_by_short[t["short"]]


def apply_weather(fixtures, weather_by_city):
    """Dated key first — "city|YYYY-MM-DD", the game's local date, read straight
    off the fixture's kick-off (already local-at-the-ground with offset, so the
    first 10 chars ARE the date). Falls back to the legacy city-wide key so an
    old-format dump, or a fixture with no kick-off, still gets a forecast."""
    for f in fixtures:
        city = (f.get("city") or "").strip().lower()
        if not city:
            continue
        day = (f.get("kickoff") or "")[:10]
        hit = weather_by_city.get(f"{city}|{day}") if day else None
        if hit is None:
            hit = weather_by_city.get(city)
        if hit is not None:
            f["weather"] = hit


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
            "updated": local_today_iso(),
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


def load_results_memory(learned_path):
    """Return the append-only results log from nrl_learned.js (or [] if missing/
    unreadable). Used to derive form + home/away splits, which the ladder source
    doesn't provide."""
    try:
        p = Path(learned_path)
        if p.exists():
            return load_learned(p).get("results", []) or []
    except Exception:
        pass
    return []


def derive_form_and_splits(teams, results):
    """Fill each team's `last5` (wins in its last 5 games) and `home`/`away` split
    records ({P,W,L,PF,PA}) from the results memory.

    Why: the scraped ladder carries only season totals — no recent-form column and no
    home/away split tables — so without this, `last5` stays 0 and `home`/`away` stay
    null, and the front-end's form nudge + venue-adjustment silently do nothing.

    Only games present in the memory count, so this is naturally partial early in the
    season and sharpens as the log grows. That's safe: the front-end's splitWeight
    (P/(P+6), capped 0.5) trusts a small split sample only lightly, leaning on the
    overall season margin until enough home/away games accumulate."""
    from collections import defaultdict
    per = defaultdict(list)  # short -> list of (round, is_home, points_for, points_against, won)
    for r in results or []:
        try:
            rnd = int(r["round"]); h = r["home"]; a = r["away"]
            hs = int(r["hs"]); as_ = int(r["as"])
        except (KeyError, ValueError, TypeError):
            continue
        per[h].append((rnd, True, hs, as_, hs > as_))
        per[a].append((rnd, False, as_, hs, as_ > hs))
    for t in teams:
        gl = sorted(per.get(t["short"], []), key=lambda x: x[0])
        if not gl:
            continue
        t["last5"] = sum(1 for g in gl[-5:] if g[4])       # wins in the last 5 games
        for side, is_home in (("home", True), ("away", False)):
            sub = [g for g in gl if g[1] == is_home]
            if sub:
                won = sum(1 for g in sub if g[4])
                t[side] = {"P": len(sub), "W": won, "L": len(sub) - won,
                           "PF": sum(g[2] for g in sub), "PA": sum(g[3] for g in sub)}
    return teams


# ---------------------------------------------------------------------------
# "What changed today" feed  (NRL_DATA.changes / NRL_DATA.changesSince)
#
# Contract: DESIGN_SPEC.md §2.1. Each entry is
#   {id, fixture, team, cat, sev, dir, text, pts}
# plus two fields the front-end ignores but this script needs:
#   ts   — ISO timestamp of first sighting, for the rolling window
#   rnd  — the round the entry belongs to, so last week's noise is purged
#
# ROLLING WINDOW, NOT "SINCE THE LAST RUN". The workflow runs every 4 hours, so
# a feed that only diffed against the immediately previous run would show Josh a
# 4-hour slice: anything that changed overnight would already be gone by
# breakfast. Instead entries accumulate, dedupe on `id`, and age out after
# CHANGES_WINDOW_HOURS. `id` therefore has to be stable for "the same change"
# and distinct for "a new change" — odds ids embed the new price, weather ids a
# hash of the new forecast, so a second, different line move is a new entry
# while a re-observation of the same one is not.
# ---------------------------------------------------------------------------
CHANGES_WINDOW_HOURS = 36
CHANGES_MAX = 60                 # hard cap so a pathological diff can't bloat the file
SQUAD_CHANGES_PER_CLUB = 5       # a wholesale re-list collapses into a summary line

# Mirrors playerImpact() in nrl-tipping-guide.html. Kept deliberately simple: it
# only has to be good enough to RANK a change's importance and print a points
# figure, and it uses the same nrl_players.js the front-end does, so the numbers
# agree with the card. If the front-end weights ever change, change these too.
SPINE_POS = {"Fullback", "Halfback", "Five-eighth", "Hooker"}
EDGE_POS = {"Centre", "Winger", "Second-row"}
BIG_SWING_PTS = 2.5              # DESIGN_SPEC §2.4: at/above this a change is sev 3


def load_js_assignment(path, var_name):
    """Read a `window.<VAR> = {...};` data file into a dict. Returns {} for any
    problem — every caller treats this as best-effort."""
    try:
        p = Path(path)
        if not p.exists():
            return {}
        text = p.read_text(encoding="utf-8", errors="ignore")
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
        m = re.search(r"window\.%s\s*=\s*(\{.*\})\s*;?\s*$" % re.escape(var_name), body, re.DOTALL)
        if not m:
            return {}
        return json.loads(m.group(1))
    except Exception:  # noqa: BLE001
        return {}


def player_impact(name, players):
    """(points, position) for a player, mirroring the front-end's weighting.
    An unrated player is the same low-impact 'fringe' fallback the app uses."""
    rec = players.get(norm_name(name)) if players else None
    if not isinstance(rec, dict):
        return (0.6 if players else 1.2), None
    pos = rec.get("pos")
    base = 3.6 if pos in SPINE_POS else 2.1 if pos in EDGE_POS else 1.2
    pct = rec.get("pct")
    pct = pct if isinstance(pct, (int, float)) and not isinstance(pct, bool) else 55
    q = max(0.55, min(1.4, pct / 70.0))
    return min(5.0, round(base * q, 1)), pos


def looks_like_player(name):
    """Same guard as the front-end's looksLikePlayer(): the news string mixes
    real names with prose ('near full strength', 'Team list Tue')."""
    s = (name or "").strip()
    if not s or len(s.split()) > 3:
        return False
    if re.match(r"^(near|settled|otherwise|several|team|no|full|squad|rotation|plenty|mostly)\b", s, re.I):
        return False
    return bool(re.match(r"^[A-Z]", s))


def news_entries(news):
    """Split a team-news string into its semicolon-separated entries."""
    return [e.strip() for e in str(news or "").split(";") if e.strip()]


def entry_player(entry):
    """'Tom Dearden (Hamstring) — back Round 24' -> 'Tom Dearden'."""
    name = (entry.split("(")[0] or entry)
    name = re.sub(r"\s+[—–-]\s+.*$", "", name).strip()
    return name


def _odds_used(odds):
    """Mirror of resolveOdds(): the price the app actually uses (close, else open,
    else the legacy flat shape). Returns {'home':x,'away':y} or None."""
    def ok(price):
        if not isinstance(price, dict):
            return None
        h, a = price.get("home"), price.get("away")
        if (isinstance(h, (int, float)) and not isinstance(h, bool)
                and isinstance(a, (int, float)) and not isinstance(a, bool)
                and h > 1 and a > 1):
            return {"home": float(h), "away": float(a)}
        return None

    if not isinstance(odds, dict):
        return None
    if odds.get("open") or odds.get("close"):
        # Validate BEFORE preferring the close, exactly as resolveOdds() in the
        # app now does: a half-written close must not discard a good open.
        return ok(odds.get("close")) or ok(odds.get("open"))
    return ok(odds)


def _market_home_prob(used):
    if not used:
        return None
    h, a = 1.0 / used["home"], 1.0 / used["away"]
    return h / (h + a)


def _slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(text or "").lower())).strip("-") or "x"


def _rain_pct(weather):
    m = re.search(r"(\d+)\s*%\s*rain", str(weather or ""), re.I)
    return int(m.group(1)) if m else None


RAIN_BAND = 20                   # weatherEffect()'s dead zone, and the band width


def _rain_band(pct):
    """Which 20-point rain band a forecast sits in, or None if unreadable.

    weatherEffect() in the app is flat below 20% rain and scales linearly above
    it, so a move INSIDE a band barely touches the tip while a move ACROSS one is
    the part worth reporting. Bands are what the weather change feed keys on, so
    "62% rain" becoming "65% rain" is not a change and cannot mint a new entry."""
    if pct is None:
        return None
    return max(0, min(5, int(pct) // RAIN_BAND))


def _instant(iso, tz_name):
    """Absolute UTC instant for a kick-off string, resolving a naive one against
    the ground's zone. Returns None if it can't be read."""
    if not iso:
        return None
    resolved = localise_naive_iso(iso, tz_name)
    try:
        dt = datetime.datetime.fromisoformat(str(resolved).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(datetime.timezone.utc)


def _fmt_kick(iso):
    """'2026-07-30T19:50:00+10:00' -> 'Thu 30 Jul 7:50pm' (in its own offset)."""
    if not iso:
        return "TBC"
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    hour = dt.hour % 12 or 12
    ap = "am" if dt.hour < 12 else "pm"
    return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')} {hour}:{dt.strftime('%M')}{ap}"


def _tname(short):
    info = TEAMS.get(short)
    return info["name"] if info else short


def _fx_index(data):
    """{short: (fixture_key, fixture_dict)} for every team playing this round."""
    out = {}
    for f in (data.get("fixtures") or []):
        key = f"{f.get('home')}-{f.get('away')}"
        out[f.get("home")] = (key, f)
        out[f.get("away")] = (key, f)
    return out


def _sev_for_pts(pts):
    return 3 if (pts or 0) >= BIG_SWING_PTS else 2


def build_changes(prev_data, data, prev_lineups, lineups, players, now_iso, round_num):
    """Diff the previous published payload against the one about to be written.

    `prev_data` may be None (first ever run) — in that case nothing is emitted,
    because "everything is new" is not information."""
    out = []
    if not isinstance(prev_data, dict):
        return out
    if not prev_data.get("generatedAt"):
        # The previous payload predates the change feed, so it has no honest
        # "when was this true" stamp — everything would diff, and a first screen
        # of 100+ rows is noise, not news. The front-end has a designed state for
        # exactly this ("Change tracking starts from the next data refresh").
        print("[parse_nrl] previous payload has no generatedAt stamp — skipping the first "
              "diff rather than reporting the whole file as 'changed'.", file=sys.stderr)
        return out

    def add(fixture, team, cat, sev, direction, text, pts=None, ident=None):
        out.append({
            "id": ident or f"r{round_num}-{fixture or 'all'}-{cat}-{_slug(text)[:40]}",
            "fixture": fixture,
            "team": team,
            "cat": cat,
            "sev": sev,
            "dir": direction,
            "text": text,
            "pts": pts,
            "ts": now_iso,
            "rnd": round_num,
        })

    prev_fx = {f"{f.get('home')}-{f.get('away')}": f for f in (prev_data.get("fixtures") or [])}
    prev_fx_pair = {frozenset((f.get("home"), f.get("away"))): f
                    for f in (prev_data.get("fixtures") or [])}

    # Two fixtures in the same city on the same LOCAL day share one forecast, so a
    # per-fixture weather entry would print the identical sentence twice (the doubled
    # "Forecast for Sydney updated" rows, 2026-07-30). Count the sharers up front;
    # a shared forecast is emitted ONCE, comp-wide (fixture=null), keyed on the city
    # + day + band rather than on either fixture.
    wx_share = {}
    for f in (data.get("fixtures") or []):
        ck = ((f.get("city") or "").strip().lower(), (f.get("kickoff") or "")[:10])
        if ck[0]:
            wx_share[ck] = wx_share.get(ck, 0) + 1
    wx_emitted = set()

    # ---- per-fixture: odds, weather, kick-off, venue -----------------------
    for f in (data.get("fixtures") or []):
        key = f"{f.get('home')}-{f.get('away')}"
        old = prev_fx.get(key) or prev_fx_pair.get(frozenset((f.get("home"), f.get("away"))))
        if not old:
            continue
        h, a = f.get("home"), f.get("away")
        hn, an = _tname(h), _tname(a)

        # odds -------------------------------------------------------------
        new_used, old_used = _odds_used(f.get("odds")), _odds_used(old.get("odds"))
        if new_used and not old_used:
            add(key, None, "line", 2, "neutral",
                f"Bookies opened this game — {hn} ${new_used['home']:.2f}, {an} ${new_used['away']:.2f}.",
                ident=f"r{round_num}-{key}-line-open-{new_used['home']:.2f}-{new_used['away']:.2f}")
        elif new_used and old_used and (abs(new_used["home"] - old_used["home"]) >= 0.01
                                        or abs(new_used["away"] - old_used["away"]) >= 0.01):
            p_new, p_old = _market_home_prob(new_used), _market_home_prob(old_used)
            swing = abs(p_new - p_old) * 100
            firming = h if new_used["home"] < old_used["home"] else a
            add(key, firming, "line", 2 if swing >= 5 else 1, "up",
                f"Line moved — {hn} ${old_used['home']:.2f} → ${new_used['home']:.2f}, "
                f"{an} ${old_used['away']:.2f} → ${new_used['away']:.2f}. "
                f"Market now {p_new * 100:.0f}% {hn} (was {p_old * 100:.0f}%).",
                ident=f"r{round_num}-{key}-line-{new_used['home']:.2f}-{new_used['away']:.2f}")

        # weather ----------------------------------------------------------
        # Only a move that changes what the MODEL does with the forecast is news.
        # Emitting on any string difference (a 1°C wobble) and id-ing by a hash of
        # that string minted a brand-new entry on every run: eight fixtures × six
        # runs a day = up to 48 sev-1 rows a day against a 60-slot window, which
        # is what pushed a "Cleary is out of the 17" entry off the feed inside its
        # window. Now: emit only on a rain-band crossing (or a ≥25pp jump, or the
        # first forecast published for a fixture), and key the id on the BAND so a
        # re-forecast inside the same band collapses onto the entry already there
        # instead of adding another.
        new_wx, old_wx = (f.get("weather") or ""), (old.get("weather") or "")
        if new_wx and new_wx != old_wx:
            rain_new, rain_old = _rain_pct(new_wx), _rain_pct(old_wx)
            # A forecast that carries no rain figure at all ("Fine, 22°C") is band
            # 0 to the model — weatherEffect() shrinks nothing — so a forecast that
            # LOSES its rain figure is a real crossing, not a silent no-op.
            band_new = _rain_band(rain_new) if rain_new is not None else (0 if new_wx else None)
            band_old = _rain_band(rain_old) if rain_old is not None else (0 if old_wx else None)
            crossed = (band_new is not None and band_old is not None and band_new != band_old)
            big = (rain_new is not None and rain_old is not None
                   and abs(rain_new - rain_old) >= 25)
            first = not old_wx
            if crossed or big or first:
                was = f" (was {rain_old}% rain)" if rain_old is not None else ""
                ck = ((f.get("city") or "").strip().lower(), (f.get("kickoff") or "")[:10])
                shared = bool(ck[0]) and wx_share.get(ck, 0) > 1
                if not (shared and ck in wx_emitted):
                    if shared:
                        wx_emitted.add(ck)
                    add(None if shared else key, None, "weather",
                        2 if (crossed or big) else 1, "neutral",
                        f"Forecast for {f.get('city') or hn} updated — {new_wx}{was}.",
                        ident=(f"r{round_num}-wx-{_slug(ck[0])}-{ck[1]}-{'new' if first else band_new}"
                               if shared else
                               f"r{round_num}-{key}-wx-{'new' if first else band_new}"))

        # kick-off ---------------------------------------------------------
        # Compare INSTANTS, not strings. The first run after this change ships
        # rewrites every naive "…T19:50:00" as "…T19:50:00+10:00"; string-diffing
        # would report a kick-off move for all eight games on that run alone.
        tz_name = f.get("tz") or resolve_tz(f.get("city"), h)
        new_kick = _instant(f.get("kickoff"), tz_name)
        old_kick = _instant(old.get("kickoff"), old.get("tz") or tz_name)
        if new_kick and old_kick and new_kick != old_kick:
            add(key, None, "time", 2, "neutral",
                f"Kick-off moved — {_fmt_kick(old.get('kickoff'))} → {_fmt_kick(f.get('kickoff'))} "
                f"(local at the ground).",
                ident=f"r{round_num}-{key}-time-{_slug(f.get('kickoff'))}")

        # venue ------------------------------------------------------------
        if (f.get("venue") or "") != (old.get("venue") or "") and f.get("venue") and old.get("venue"):
            add(key, None, "venue", 2, "neutral",
                f"Venue moved — {old.get('venue')} → {f.get('venue')}"
                + (f", {f.get('city')}" if f.get("city") else "") + ".",
                ident=f"r{round_num}-{key}-venue-{_slug(f.get('venue'))}")

    # ---- per-team: injury-table churn ------------------------------------
    idx = _fx_index(data)
    prev_news = {t.get("short"): t.get("news") for t in (prev_data.get("teams") or [])}
    for t in (data.get("teams") or []):
        short = t.get("short")
        if short not in idx:
            continue                       # bye team — nothing to tip, nothing to report
        fixture_key = idx[short][0]
        new_set = news_entries(t.get("news"))
        old_set = news_entries(prev_news.get(short))
        if new_set == old_set:
            continue
        new_by_player = {norm_name(entry_player(e)): e for e in new_set if looks_like_player(entry_player(e))}
        old_by_player = {norm_name(entry_player(e)): e for e in old_set if looks_like_player(entry_player(e))}
        for k in sorted(set(new_by_player) - set(old_by_player)):
            entry = new_by_player[k]
            name = entry_player(entry)
            pts, pos = player_impact(name, players)
            add(fixture_key, short, "injury", _sev_for_pts(pts), "down",
                f"{_tname(short)}: {entry} — new on the injury list.", pts,
                ident=f"r{round_num}-{short}-inj-{_slug(name)}")
        for k in sorted(set(old_by_player) - set(new_by_player)):
            name = entry_player(old_by_player[k])
            pts, pos = player_impact(name, players)
            add(fixture_key, short, "injury", 2, "up",
                f"{_tname(short)}: {name} is off the injury list.", pts,
                ident=f"r{round_num}-{short}-fit-{_slug(name)}")

    # ---- per-team: named 17 in / out -------------------------------------
    # Only diffed when BOTH lineup files describe the round being tipped. On the
    # Tuesday the lists first drop, the previous file is still last week's, so
    # this correctly emits nothing instead of 34 "named in the 17" rows per game.
    lu_round = (lineups or {}).get("round")
    prev_lu_round = (prev_lineups or {}).get("round")
    if (lineups and prev_lineups and lu_round and prev_lu_round
            and int(lu_round) == int(prev_lu_round)
            and (not round_num or int(lu_round) == int(round_num))):
        cur_teams = (lineups.get("teams") or {})
        old_teams = (prev_lineups.get("teams") or {})
        cur_news = {t.get("short"): {norm_name(entry_player(e)) for e in news_entries(t.get("news"))}
                    for t in (data.get("teams") or [])}
        for short, squad in sorted(cur_teams.items()):
            old_squad = old_teams.get(short)
            if short not in idx or not isinstance(squad, list) or not isinstance(old_squad, list):
                continue
            fixture_key = idx[short][0]
            cur_names = {norm_name(n): n for n in squad if n}
            old_names = {norm_name(n): n for n in old_squad if n}
            ins = sorted(set(cur_names) - set(old_names))
            outs = sorted(set(old_names) - set(cur_names))
            scored = []
            for k in ins:
                name = cur_names[k]
                pts, pos = player_impact(name, players)
                was_doubt = k in (cur_news.get(short) or set())
                scored.append((pts, "in", name, pos, was_doubt))
            for k in outs:
                name = old_names[k]
                pts, pos = player_impact(name, players)
                scored.append((pts, "out", name, pos, False))
            scored.sort(key=lambda x: -x[0])
            for pts, kind, name, pos, was_doubt in scored[:SQUAD_CHANGES_PER_CLUB]:
                where = f" ({pos})" if pos else ""
                if kind == "in":
                    text = (f"{name}{where} named in the {_tname(short)} 17"
                            + (" — was on the injury list." if was_doubt else "."))
                    add(fixture_key, short, "in", _sev_for_pts(pts), "up", text, pts,
                        ident=f"r{round_num}-{short}-in-{_slug(name)}")
                else:
                    add(fixture_key, short, "out", _sev_for_pts(pts), "down",
                        f"{name}{where} is out of the {_tname(short)} 17.", pts,
                        ident=f"r{round_num}-{short}-out-{_slug(name)}")
            spill = len(scored) - SQUAD_CHANGES_PER_CLUB
            if spill > 0:
                add(fixture_key, short, "other", 1, "neutral",
                    f"{_tname(short)}: {spill} further squad change{'' if spill == 1 else 's'}.",
                    ident=f"r{round_num}-{short}-squad-spill-{len(scored)}")
    return out


def merge_changes(prev_changes, new_changes, now, round_num, window_hours=CHANGES_WINDOW_HOURS):
    """Roll the previous window forward: keep entries from this round that are
    younger than `window_hours`, dedupe on `id` (the FIRST sighting's timestamp
    wins, so a persistent condition still ages out), then append what's new."""
    cutoff = now - datetime.timedelta(hours=window_hours)
    kept, seen = [], set()
    for c in (prev_changes or []):
        if not isinstance(c, dict) or not c.get("id") or not str(c.get("text", "")).strip():
            continue
        if round_num and c.get("rnd") is not None and int(c["rnd"]) != int(round_num):
            continue                                   # last round's news is not news
        ts = c.get("ts")
        try:
            when = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue                                   # unstampable -> can never expire; drop
        if when.tzinfo is None:
            when = when.replace(tzinfo=now.tzinfo)
        if when < cutoff:
            continue
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        kept.append(c)
    for c in new_changes or []:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        kept.append(c)
    # SEVERITY FIRST, then newest first — because of the CHANGES_MAX truncation
    # below. Sorting on `ts` first made severity a tie-break within the same
    # second, i.e. no protection at all: a run that produced 60 trivial entries
    # evicted a sev-3 "Cleary is out of the 17" half an hour into its 36-hour
    # window. With severity leading, the cap sheds trivia and keeps signal.
    # The front-end re-sorts for display (groups by fixture, orders by highest
    # severity then fixture order, and tallies the sev-1s into one footnote),
    # so this ordering is free to serve the truncation instead.
    kept.sort(key=lambda c: (int(c.get("sev") or 2), str(c.get("ts") or "")), reverse=True)
    return kept[:CHANGES_MAX]


def changes_since(changes, prev_data, now_iso, window_hours=CHANGES_WINDOW_HOURS):
    """The instant the window opens, for the header's "{n} updates since {time}".

    The oldest entry still on show is the floor, but it is NOT the answer on its
    own: on a busy run every entry was first seen a second ago, so min(ts) is
    "now" and the header read "18 updates since 8:42 pm" at 8:42 pm. Everything
    in the feed was in fact detected at or after the PREVIOUS run, so that stamp
    is the honest window opening — clamped to the rolling window so a workflow
    outage can't advertise a since-time older than anything on show."""
    stamps = sorted(str(c.get("ts")) for c in changes if c.get("ts"))
    oldest = stamps[0] if stamps else None
    prev_stamp = None
    if isinstance(prev_data, dict):
        prev_stamp = prev_data.get("generatedAt") or prev_data.get("changesSince")
    if prev_stamp:
        try:
            prev_dt = datetime.datetime.fromisoformat(str(prev_stamp).replace("Z", "+00:00"))
            now_dt = datetime.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=now_dt.tzinfo)
            floor = now_dt - datetime.timedelta(hours=window_hours)
            if prev_dt < floor:
                prev_stamp = floor.isoformat(timespec="seconds")
        except (ValueError, TypeError):
            pass
    if oldest and prev_stamp:
        return min(oldest, str(prev_stamp))
    return oldest or prev_stamp or now_iso


def attach_changes(data, prev_data, args, round_num, now):
    """Compute this run's change feed and stamp it onto `data`. Best-effort in
    every direction: any failure leaves the previous window untouched rather
    than blanking a feed Josh may not have read yet."""
    now_iso = now.isoformat(timespec="seconds")
    data["generatedAt"] = now_iso
    try:
        players = load_js_assignment(args.players, "NRL_PLAYERS")
        lineups = load_js_assignment(args.lineups, "NRL_LINEUPS")
        prev_lineups = load_js_assignment(args.lineups_prev, "NRL_LINEUPS")
        fresh = build_changes(prev_data, data, prev_lineups, lineups, players, now_iso, round_num)
    except Exception as exc:  # noqa: BLE001
        print(f"[parse_nrl] WARNING: change-feed diff failed ({exc}); "
              f"carrying the previous window forward.", file=sys.stderr)
        fresh = []
    prev_changes = (prev_data or {}).get("changes") if isinstance(prev_data, dict) else []
    data["changes"] = merge_changes(prev_changes, fresh, now, round_num, args.changes_window)
    data["changesSince"] = changes_since(data["changes"], prev_data, now_iso, args.changes_window)
    print(f"[parse_nrl] change feed: {len(fresh)} new, {len(data['changes'])} in the "
          f"{args.changes_window}h window (since {data['changesSince']})")
    return len(fresh)


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

    # Snapshot BEFORE anything is mutated — this is what the change feed diffs
    # against. Merge mode is the fast reactive path, so it has to produce changes
    # too; without this snapshot it would compare the file to itself.
    prev_data = json.loads(json.dumps(data))

    teams = data["teams"]
    fixtures = data["fixtures"]

    n_odds = n_injuries = n_weather = n_meta = 0

    if args.draw_meta:
        meta_path = Path(args.draw_meta)
        if meta_path.exists():
            meta = parse_draw_meta(meta_path.read_text(encoding="utf-8", errors="ignore"))
            n_meta = apply_draw_meta(fixtures, meta, data.get("round"))
            print(f"[parse_nrl] MERGE: refreshed venue/city/kick-off on {n_meta} fixture(s) "
                  f"from {meta_path}")

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

    finalise_fixture_times(fixtures)

    news_updated = args.updated or local_today_iso()
    data["newsUpdated"] = news_updated
    attach_changes(data, prev_data, args, data.get("round"), now_local())
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
    ap.add_argument("--draw-meta", dest="draw_meta", default="draw_meta.json",
                     help="structured venue/city/kick-off sidecar written by cloud_fetch.py from "
                          "nrl.com's own draw payload. Defaults to draw_meta.json and is skipped "
                          "silently if absent — it defaults ON deliberately: this feed being wired "
                          "up by an easily-forgotten flag is exactly how odds stayed null for months.")
    ap.add_argument("--players", default="nrl_players.js",
                     help="player ratings map, used to size a change's model-points swing")
    ap.add_argument("--lineups", default="nrl_lineups.js", help="this run's named 17s")
    ap.add_argument("--lineups-prev", dest="lineups_prev", default="nrl_lineups.prev.js",
                     help="the PREVIOUS run's named 17s, preserved by cloud_fetch.py, so "
                          "named/omitted players can be diffed")
    ap.add_argument("--changes-window", dest="changes_window", type=int, default=CHANGES_WINDOW_HOURS,
                     help="hours a change stays in the 'what changed' feed (default %(default)s). "
                          "The workflow runs every 4h, so a per-run feed would hide anything that "
                          "moved overnight.")
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

    updated = args.updated or local_today_iso()

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

    # The previously published payload: the baseline the change feed diffs
    # against, and the fallback when the draw won't parse.
    out_path = Path(args.out)
    prev_data = None
    if out_path.exists():
        try:
            prev_data = load_existing_data(out_path)
        except Exception as e:  # noqa: BLE001
            print(f"[parse_nrl] WARNING: existing {out_path} unreadable ({e}) — "
                  f"no change feed this run.", file=sys.stderr)

    # Degrade gracefully: if fixtures couldn't be parsed but an existing
    # nrl_data.js is present, keep its fixtures/round/bye rather than
    # emitting an empty round.
    if not fixtures and prev_data:
        fixtures = json.loads(json.dumps(prev_data.get("fixtures", [])))  # detached copy
        round_num = round_num or prev_data.get("round")
        print("[parse_nrl] draw missing — reused fixtures/round from existing nrl_data.js", file=sys.stderr)

    # Venue / host city / kick-off, from the structured nrl.com sidecar.
    if fixtures and args.draw_meta:
        meta_path = Path(args.draw_meta)
        if meta_path.exists():
            meta = parse_draw_meta(meta_path.read_text(encoding="utf-8", errors="ignore"))
            n_meta = apply_draw_meta(fixtures, meta, round_num)
            print(f"[parse_nrl] applied venue/city/kick-off metadata to {n_meta}/{len(fixtures)} "
                  f"fixture(s) from {meta_path}")
        else:
            print(f"[parse_nrl] NOTE: no draw metadata at {meta_path} — venue/kick-off fall back "
                  f"to whatever the draw dump's text carries.", file=sys.stderr)

    if not teams:
        print("[parse_nrl] ERROR: no ladder data available — cannot build a valid nrl_data.js. Aborting.", file=sys.stderr)
        sys.exit(1)

    # Recent form + home/away splits aren't in the scraped ladder — derive them from
    # the results memory (which we may have just grown above). Without this, last5
    # stays 0 and home/away stay null and the model's form/venue features are inert.
    derive_form_and_splits(teams, load_results_memory(args.learned))
    n_form = sum(1 for t in teams if t.get("last5"))
    n_split = sum(1 for t in teams if t.get("home") or t.get("away"))
    print(f"[parse_nrl] derived form for {n_form} team(s), home/away splits for {n_split} team(s) from results memory")

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

    # Every fixture ends up with a `tz` and an offset-bearing `kickoff`.
    finalise_fixture_times(fixtures)

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

    attach_changes(data, prev_data, args, data["round"], now_local())

    emit_js(data, out_path)
    print(f"[parse_nrl] wrote {out_path} — {len(teams)} teams, round {data['round']}, "
          f"{len(fixtures)} fixtures, bye={bye_teams}")


if __name__ == "__main__":
    main()
