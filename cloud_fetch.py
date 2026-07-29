#!/usr/bin/env python3
"""
cloud_fetch.py — runs on GitHub Actions (NOT on the Mac).

Fetches the LIVE data the app needs and rebuilds the clean dump files that
parse_nrl.py expects (parse_nrl does its own tag handling, so it needs real
tags / the right line formats, not pre-flattened text).

  * ladder_dump.html   — current standings, from the live ladder table.
  * draw_dump.html     — the NEXT round's fixtures (lowest round whose games
                         aren't "fulltime" yet). Auto-advances every week.
  * weather_dump.txt   — game-weekend forecast per host city, from the free
                         Open-Meteo API (no key). "City: summary" lines.
  * injuries_dump.html — best-effort team-news per club from Zero Tackle's
                         injuries page. "Team: notes" lines. Falls back to the
                         committed file if the page won't parse cleanly.
  * nrl_players.js     — player -> {position, rating} from the NINE per-position
                         ratings pages (the /overall/ page splits the name across
                         two cells, which is what produced the first-name-only
                         keys that silently disabled every injury lookup).
  * nrl_lineups.js     — the named 1-17 per club from the current round's team-lists
                         article. The front-end uses it to cancel an injury-table
                         entry for anyone who is actually named in the side.
  * nrl_lineups.prev.js— the PREVIOUS run's copy of the above, kept so parse_nrl.py
                         can diff it and tell Josh who was named / who dropped out.
  * odds_dump.txt      — bookmaker head-to-head prices per fixture, from nrl.com's
                         own draw payload. In parse_nrl.parse_odds()'s existing
                         "Home v Away: 1.85 / 1.95" format.
  * draw_meta.json     — venue / host city / UTC kick-off per fixture, also from
                         nrl.com's draw payload. Structured on purpose: the old
                         path emitted prose and hoped a regex would find a venue
                         in it, which is why every fixture shipped venue:"".

Anything that can't be parsed confidently is left as the previous committed
file (never wipes good data). Network access is fine here (GitHub servers).
"""
import datetime
import html as html_mod
import json
import os
import re
import shutil
import sys

import requests
from bs4 import BeautifulSoup, NavigableString

# Shared with the parser so there is exactly ONE alias table and ONE name
# normaliser in the project (see docs/GOTCHAS.md — a second, parallel mapping is
# how feeds drift apart). Side-effect free import.
from parse_nrl import find_short, norm_name, TEAMS, TEAM_HOME_CITY  # noqa: F401

HEADERS = {"User-Agent": "footy-tipping-personal/1.0 (non-commercial; polite; low-frequency)"}
LADDER_URL = "https://www.zerotackle.com/nrl/nrl-ladder/"
FIXTURES_URL = "https://www.zerotackle.com/nrl/fixtures-results/"
INJURIES_URL = "https://www.zerotackle.com/nrl/injuries-suspensions/"
TEAMLISTS_INDEX_URL = "https://www.zerotackle.com/nrl/team-lists/"

# The NRL season is the calendar year (Mar–Oct), so today's year is right all
# season. NRL_SEASON overrides it for a replay/backfill run.
SEASON = int(os.environ.get("NRL_SEASON") or datetime.date.today().year)

# Player positions as they appear on the ratings page (closed set).
RATING_POSITIONS = ["Five-eighth", "Second-row", "Fullback", "Halfback", "Hooker",
                    "Winger", "Centre", "Prop", "Lock"]
_POS_RE = re.compile(r"\b(" + "|".join(RATING_POSITIONS) + r")\b", re.IGNORECASE)
_POS_CANON = {p.lower(): p for p in RATING_POSITIONS}

# Ratings come from the nine PER-POSITION pages, not /overall/. Two reasons:
#   1. the position is implied by the URL, so there's no position column to
#      mis-read; and
#   2. /overall/ renders a player's name across two table cells, so reading
#      "the cell after the rank" yields a FIRST NAME ONLY. That is exactly how
#      nrl_players.js ended up keyed "nathan"/"harry"/"payne", which made every
#      front-end lookup miss and quietly reduced every injured player — Munster,
#      Grant, anyone — to the 0.6pt fringe fallback. Do not switch back.
RATING_POS_BY_SLUG = {
    "fullback": "Fullback", "winger": "Winger", "centre": "Centre",
    "five-eighth": "Five-eighth", "halfback": "Halfback", "hooker": "Hooker",
    "prop": "Prop", "second-row": "Second-row", "lock": "Lock",
}
RATINGS_URL_TPL = "https://www.zerotackle.com/nrl-player-ratings/{}/"
PLAYER_HREF_RE = re.compile(r"/players/([a-z0-9'-]+)/?$", re.IGNORECASE)
TEAM_HREF_RE = re.compile(r"/teams/([a-z0-9-]+)/?$", re.IGNORECASE)
TEAMLIST_ARTICLE_RE = re.compile(r"/round-(\d+)-team-lists-(20\d\d)-(\d+)/?", re.IGNORECASE)

ZT_SLUG = {
    "PEN": "panthers", "SYD": "roosters", "NZW": "warriors", "CRO": "sharks",
    "DOL": "dolphins", "SOU": "rabbitohs", "NEW": "knights", "NQL": "cowboys",
    "MAN": "sea-eagles", "CAN": "bulldogs", "CBR": "raiders", "MEL": "storm",
    "BRI": "broncos", "PAR": "eels", "WST": "wests-tigers", "GLD": "titans",
    "STI": "dragons",
}
SLUG_TO_SHORT = {v: k for k, v in ZT_SLUG.items()}
SLUGS_BY_LEN = sorted(SLUG_TO_SHORT, key=len, reverse=True)
MATCH_SLUG_RE = re.compile(r"/(fulltime-)?([a-z0-9-]+)-round-(\d+)-20\d\d", re.IGNORECASE)

# Host-city coordinates for the weather lookup (matches parse_nrl TEAM_HOME_CITY / VENUE_CITY).
CITY_COORDS = {
    "Sydney": (-33.87, 151.21), "Brisbane": (-27.47, 153.03), "Melbourne": (-37.81, 144.96),
    "Gold Coast": (-28.00, 153.43), "Newcastle": (-32.93, 151.78), "Townsville": (-19.26, 146.82),
    "Canberra": (-35.28, 149.13), "Wollongong": (-34.42, 150.90), "Auckland": (-36.85, 174.76),
    "Mudgee": (-32.60, 149.59), "Redcliffe": (-27.23, 153.11), "Rockhampton": (-23.38, 150.51),
}
WMO = {0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow",
       75: "heavy snow", 80: "showers", 81: "showers", 82: "heavy showers",
       95: "thunderstorms", 96: "thunderstorms", 99: "thunderstorms"}


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


# --------------------------------------------------------------------------- ladder
def ints_in(cells):
    out = []
    for c in cells:
        for tok in re.findall(r"[+-]?\d+", c.replace(",", "")):
            out.append(int(tok))
    return out


def team_from_cells(cells):
    for c in cells:
        s = find_short(c)
        if s:
            return s
    return None


def extract_ladder(html):
    soup = BeautifulSoup(html, "html.parser")
    teams, debug = {}, []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        short = team_from_cells(cells)
        if not short or short in teams:
            continue
        nums = ints_in(cells)
        big = [n for n in nums if n >= 100]
        if len(big) < 2:
            continue
        pf, pa = big[0], big[1]
        smalls = [n for n in nums if 0 <= n < 100]
        cand = []
        if len(smalls) >= 5:
            cand.append((smalls[1], smalls[2], smalls[3], smalls[4]))
        if len(smalls) >= 4:
            cand.append((smalls[0], smalls[1], smalls[2], smalls[3]))
        pick = next(((P, W, L, D) for P, W, L, D in cand if abs((W + L + D) - P) <= 2 and 5 <= P <= 40), None)
        if pick is None:
            continue
        P, W, L, D = pick
        teams[short] = {"name": TEAMS[short]["name"], "P": P, "W": W, "L": L, "D": D, "PF": pf, "PA": pa}
        debug.append(f"{short}: P{P} W{W} L{L} D{D} PF{pf} PA{pa}")
    return teams, debug


def emit_ladder(teams):
    out = ['<!-- rebuilt by cloud_fetch.py from the live Zero Tackle ladder -->', '<table class="ladder">']
    for t in teams.values():
        diff = t["PF"] - t["PA"]
        out.append(
            f'<tr><td>{t["name"]}</td><td>{t["P"]}</td><td>{t["W"]}</td>'
            f'<td>{t["D"]}</td><td>{t["L"]}</td><td>{t["PF"]}</td><td>{t["PA"]}</td>'
            f'<td>{diff:+d}</td><td>0</td><td></td></tr>'
        )
    out.append("</table>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- draw
def split_matchup(teams_part):
    for home_slug in SLUGS_BY_LEN:
        prefix = home_slug + "-"
        if teams_part.startswith(prefix):
            away_slug = teams_part[len(prefix):]
            if away_slug in SLUG_TO_SHORT:
                return SLUG_TO_SHORT[home_slug], SLUG_TO_SHORT[away_slug]
    return None, None


def extract_draw(html):
    soup = BeautifulSoup(html, "html.parser")
    by_round = {}
    for a in soup.find_all("a", href=True):
        m = MATCH_SLUG_RE.search(a["href"])
        if not m:
            continue
        played = bool(m.group(1))
        home, away = split_matchup(m.group(2).lower())
        rnd = int(m.group(3))
        if not home or not away or home == away:
            continue
        key = frozenset((home, away))
        slot = by_round.setdefault(rnd, {})
        if key not in slot or played:
            slot[key] = (home, away, played)
    if not by_round:
        return None, []
    unplayed = sorted(r for r, games in by_round.items() if any(not p for (_, _, p) in games.values()))
    if not unplayed:
        return None, []
    rnd = unplayed[0]
    fixtures = [(h, a) for (h, a, _p) in by_round[rnd].values()]
    return rnd, fixtures


def emit_draw(rnd, fixtures):
    out = ["<!-- rebuilt by cloud_fetch.py from the live Zero Tackle fixtures page -->",
           f"<h2>Round {rnd}</h2>"]
    for home, away in fixtures:
        out.append(f"<p>{TEAMS[home]['name']} v {TEAMS[away]['name']}</p>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- nrl.com draw
# THE OFFICIAL DRAW, as structured data.
#
# Zero Tackle gives us which fixtures exist and which round is next, but nothing
# else: extract_draw() returns bare (home, away) pairs and emit_draw() wrote only
# "<h2>Round 22</h2>" + "<p>Cowboys v Roosters</p>". parse_nrl.parse_draw() then
# hunted those lines for a venue and a kick-off time that were never written, so
# every fixture published venue:"" and kickoff:"" — and the odds field had no
# source at all and had been null since the app was built.
#
# nrl.com's /draw/ page embeds the entire round as JSON in a `q-data` attribute
# on the #vue-draw element: venue, venueCity, a Z-suffixed UTC kickOffTimeLong,
# and each side's decimal head-to-head price. We read that blob rather than the
# rendered page — GOTCHAS.md's recurring lesson on this project is that the
# rendered text is an illusion and the underlying data is the truth.
NRL_COMPETITION_ID = 111                     # NRL Telstra Premiership
NRL_DRAW_URL = "https://www.nrl.com/draw/?competition={comp}&round={rnd}&season={season}"
NRL_DRAW_URL_CURRENT = "https://www.nrl.com/draw/?competition={comp}&season={season}"
QDATA_RE = re.compile(r'id="vue-draw"[^>]*\bq-data="([^"]*)"')
ROUND_TITLE_RE = re.compile(r"round\s+(\d{1,2})", re.IGNORECASE)


def fetch_nrl_draw(season, rnd=None):
    """Fetch and decode nrl.com's draw payload for a round (or the current round
    when `rnd` is None). Returns the decoded dict, or None on any failure —
    every caller degrades rather than aborting."""
    url = (NRL_DRAW_URL.format(comp=NRL_COMPETITION_ID, rnd=int(rnd), season=int(season))
           if rnd else NRL_DRAW_URL_CURRENT.format(comp=NRL_COMPETITION_ID, season=int(season)))
    try:
        page = fetch(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: nrl.com draw fetch failed ({exc}) — "
              f"no odds/venue/kick-off this run.", file=sys.stderr)
        return None
    m = QDATA_RE.search(page)
    if not m:
        print("[cloud_fetch] WARNING: nrl.com draw page carried no q-data blob "
              "(page redesign?) — no odds/venue/kick-off this run.", file=sys.stderr)
        return None
    try:
        data = json.loads(html_mod.unescape(m.group(1)))
    except (ValueError, TypeError) as exc:
        print(f"[cloud_fetch] WARNING: nrl.com q-data blob would not decode ({exc}).", file=sys.stderr)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("fixtures"), list):
        print("[cloud_fetch] WARNING: nrl.com payload has no fixtures list.", file=sys.stderr)
        return None
    return data


def _odds_value(team_block):
    """nrl.com ships odds as a STRING, and omits/blanks/nulls it before the
    market opens. Return a float > 1 or None; never a placeholder."""
    raw = (team_block or {}).get("odds")
    if raw in (None, "", "-"):
        return None
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return val if val > 1 else None


def parse_nrl_draw(data):
    """Decoded nrl.com payload -> (round, fixtures, byes, show_odds).

    fixtures is a list of dicts:
      {home, away, venue, city, kickoffUtc, homeOdds, awayOdds}
    with `home`/`away` as this project's short codes. A fixture whose two teams
    don't both resolve is skipped and logged rather than guessed at."""
    fixtures, rounds, unresolved = [], [], []
    for fx in data.get("fixtures") or []:
        if (fx.get("type") or "Match") != "Match":
            continue
        hb, ab = fx.get("homeTeam") or {}, fx.get("awayTeam") or {}
        home, away = find_short(hb.get("nickName") or ""), find_short(ab.get("nickName") or "")
        if not home or not away or home == away:
            unresolved.append(f"{hb.get('nickName')!r} v {ab.get('nickName')!r}")
            continue
        rm = ROUND_TITLE_RE.search(fx.get("roundTitle") or "")
        if rm:
            rounds.append(int(rm.group(1)))
        fixtures.append({
            "home": home, "away": away,
            "venue": (fx.get("venue") or "").strip(),
            "city": (fx.get("venueCity") or "").strip(),
            "kickoffUtc": ((fx.get("clock") or {}).get("kickOffTimeLong") or "").strip(),
            "homeOdds": _odds_value(hb),
            "awayOdds": _odds_value(ab),
        })
    byes = []
    for b in data.get("byes") or []:
        s = find_short(b.get("teamNickName") or "")
        if s:
            byes.append(s)
        elif b.get("teamNickName"):
            unresolved.append(f"bye {b.get('teamNickName')!r}")
    if unresolved:
        # A nickname nrl.com uses that our alias table doesn't know is a real
        # defect: the fix is a new alias in parse_nrl.TEAMS, never a second
        # parallel mapping in this file.
        print("[cloud_fetch] ERROR: nrl.com nickname(s) did not resolve to a short code — "
              "add the alias to TEAMS in parse_nrl.py: " + "; ".join(unresolved), file=sys.stderr)
    rnd = max(set(rounds), key=rounds.count) if rounds else None
    return rnd, fixtures, byes, bool(data.get("showOdds"))


def reconcile_draw(zt_round, zt_fixtures, nrl_round, nrl_fixtures):
    """Agree on one fixture list.

    Zero Tackle drives WHICH round is next (it's what the ladder/results feeds are
    keyed to, and it's the behaviour everything downstream already depends on), so
    a round disagreement is resolved in Zero Tackle's favour and shouted about.

    nrl.com is the OFFICIAL listing, so it wins on home/away designation. GOTCHAS
    records a past "Eels v Tigers looks swapped" report that turned out to be
    correct per the official listing — hence: prefer nrl.com, but log every flip
    loudly rather than reordering in silence.

    Returns (round, [(home, away), ...], flips)."""
    if not zt_fixtures:
        if nrl_fixtures:
            print(f"[cloud_fetch] Zero Tackle draw unusable — falling back to nrl.com's "
                  f"round {nrl_round} ({len(nrl_fixtures)} fixtures).", file=sys.stderr)
            return nrl_round, [(f["home"], f["away"]) for f in nrl_fixtures], []
        return zt_round, [], []
    if nrl_round and zt_round and int(nrl_round) != int(zt_round):
        print(f"[cloud_fetch] WARNING: round disagreement — Zero Tackle says round {zt_round}, "
              f"nrl.com says round {nrl_round}. Using {zt_round} (Zero Tackle drives the ladder, "
              f"results and injuries feeds); nrl.com odds/venues for this round will be dropped.",
              file=sys.stderr)
        return zt_round, list(zt_fixtures), []
    orient = {frozenset((f["home"], f["away"])): (f["home"], f["away"]) for f in nrl_fixtures}
    out, flips = [], []
    for home, away in zt_fixtures:
        official = orient.get(frozenset((home, away)))
        if official and official != (home, away):
            flips.append(f"{home} v {away} -> {official[0]} v {official[1]}")
            out.append(official)
        else:
            out.append((home, away))
    if flips:
        print("[cloud_fetch] NOTE: home/away designation taken from nrl.com (the official "
              "listing) over Zero Tackle for: " + "; ".join(flips), file=sys.stderr)
    zt_pairs = {frozenset(p) for p in zt_fixtures}
    only_nrl = [f"{f['home']} v {f['away']}" for f in nrl_fixtures
                if frozenset((f["home"], f["away"])) not in zt_pairs]
    only_zt = [f"{h} v {a}" for h, a in zt_fixtures if frozenset((h, a)) not in orient]
    if only_nrl:
        print(f"[cloud_fetch] NOTE: on nrl.com but not Zero Tackle: {'; '.join(only_nrl)}",
              file=sys.stderr)
    if only_zt:
        print(f"[cloud_fetch] NOTE: on Zero Tackle but not nrl.com: {'; '.join(only_zt)}",
              file=sys.stderr)
    return zt_round, out, flips


def emit_odds(rnd, fixtures, pairs):
    """Head-to-head prices in the EXACT line format parse_nrl.parse_odds()
    already reads: "Home v Away: 1.85 / 1.95". Nothing new is invented here —
    the parser and its {open, close} CLV handling are untouched.

    `pairs` is the reconciled [(home, away)] list, so the line is written in the
    same orientation the draw dump uses. (parse_odds keys on an unordered pair
    anyway, but a dump a human can read against the draw is worth the care.)"""
    by_pair = {frozenset((f["home"], f["away"])): f for f in fixtures}
    lines = [f"# Round {rnd} head-to-head odds, from nrl.com's own draw payload.",
             f"# Fetched {datetime.datetime.now().isoformat(timespec='seconds')}. "
             f"Decimal odds; a fixture is omitted entirely until its market opens."]
    n = 0
    for home, away in pairs:
        f = by_pair.get(frozenset((home, away)))
        if not f or f["homeOdds"] is None or f["awayOdds"] is None:
            continue
        ho, ao = (f["homeOdds"], f["awayOdds"]) if f["home"] == home else (f["awayOdds"], f["homeOdds"])
        lines.append(f"{TEAMS[home]['name']} v {TEAMS[away]['name']}: {ho:.2f} / {ao:.2f}")
        n += 1
    return "\n".join(lines) + "\n", n


def emit_draw_meta(season, rnd, fixtures, pairs):
    """Venue / host city / UTC kick-off per fixture, as JSON keyed "HOME-AWAY".

    A sidecar rather than more prose in draw_dump.html: parse_draw()'s venue and
    kick-off hints are regexes over rendered text, which is the exact pattern
    GOTCHAS.md blames for the team-list footer bug. The timezone conversion is
    left to parse_nrl.py (it owns VENUE_CITY / CITY_TZ and is the pure, testable
    half of the pipeline), so what travels here is the raw UTC instant."""
    by_pair = {frozenset((f["home"], f["away"])): f for f in fixtures}
    out = {}
    for home, away in pairs:
        f = by_pair.get(frozenset((home, away)))
        if not f:
            continue
        out[f"{home}-{away}"] = {
            "venue": f["venue"],
            "city": f["city"],
            "kickoffUtc": f["kickoffUtc"],
        }
    doc = {
        "_comment": ("Venue / host city / kick-off for the round below, from nrl.com's own draw "
                     "payload. kickoffUtc is a UTC instant; parse_nrl.py converts it to the "
                     "ground's local time and emits fixture.tz. Regenerated every run by "
                     "cloud_fetch.py — do not hand-edit."),
        "season": int(season),
        "round": rnd,
        "source": "nrl.com",
        "fetched": datetime.datetime.now().isoformat(timespec="seconds"),
        "fixtures": out,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n", len(out)


# --------------------------------------------------------------------------- results
def _nearest_int(lines, k, direction):
    """First 1-3 digit integer scanning outward from index k in the given direction."""
    j = k + direction
    while 0 <= j < len(lines):
        if re.fullmatch(r"\d{1,3}", lines[j]):
            return int(lines[j])
        j += direction
    return None


def extract_results(html):
    """Parse finished-game scores from the Zero Tackle fixtures/results page.

    Each played match links to a '/fulltime-<home>-<away>-round-N-...' match centre,
    and within the same match card the two scores sit either side of an 'FT' marker
    (home code, home score, FT, away score, away code). We take teams + round from the
    slug (reliable) and the two scores from the card. Returns
    [{round, home, away, hs, as}]; anything that doesn't resolve cleanly is skipped."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = MATCH_SLUG_RE.search(a["href"])
        if not m or not m.group(1):            # only 'fulltime-' (i.e. played) links
            continue
        home, away = split_matchup(m.group(2).lower())
        if not home or not away or home == away:
            continue
        rnd = int(m.group(3))
        # Climb to the nearest ancestor whose text contains the 'FT' marker — that's
        # this match's card. (Ancestors between the <a> and the card don't contain FT.)
        lines = []
        node = a
        for _ in range(8):
            node = node.parent
            if node is None:
                break
            lines = [x.strip() for x in node.get_text("\n").split("\n") if x.strip()]
            if "FT" in lines:
                break
        if "FT" not in lines:
            continue
        k = lines.index("FT")
        hs = _nearest_int(lines, k, -1)        # score just before FT = home
        aw = _nearest_int(lines, k, +1)        # score just after FT  = away
        if hs is None or aw is None:
            continue
        key = (rnd, home, away)
        if key in seen:
            continue
        seen.add(key)
        out.append({"round": rnd, "home": home, "away": away, "hs": hs, "as": aw})
    return out


def emit_results(results):
    """Write finished games in the 'Round N' + 'Home hs - Away aws' format that
    parse_nrl.py's parse_results()/--results already understands."""
    by_round = {}
    for r in results:
        by_round.setdefault(r["round"], []).append(r)
    out = ["<!-- rebuilt by cloud_fetch.py from the live Zero Tackle fixtures/results page -->"]
    for rnd in sorted(by_round):
        out.append(f"Round {rnd}")
        for r in by_round[rnd]:
            out.append(f"{TEAMS[r['home']]['name']} {r['hs']} - {TEAMS[r['away']]['name']} {r['as']}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- weather
def fetch_weather(cities):
    """Return {City: 'Day D Mon: 19C, 60% rain, showers'} for the wettest of the
    next few days (a useful game-weekend read). Best-effort per city."""
    out = {}
    for city in sorted(cities):
        co = CITY_COORDS.get(city)
        if not co:
            continue
        try:
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={co[0]}&longitude={co[1]}"
                   f"&daily=weather_code,temperature_2m_max,precipitation_probability_max"
                   f"&timezone=auto&forecast_days=7")
            d = requests.get(url, headers=HEADERS, timeout=30).json()["daily"]
            dates = d["time"]
            n = min(6, len(dates))
            pops = [d["precipitation_probability_max"][i] or 0 for i in range(n)]
            idx = max(range(n), key=lambda i: pops[i])  # wettest upcoming day
            code = d["weather_code"][idx]
            tmax = d["temperature_2m_max"][idx]
            pop = d["precipitation_probability_max"][idx]
            day = datetime.date.fromisoformat(dates[idx]).strftime("%a %-d %b")
            desc = WMO.get(code, "")
            out[city] = f"{day}: {round(tmax)}°C, {pop}% rain chance{(', ' + desc) if desc else ''}"
        except Exception as exc:  # noqa: BLE001
            print(f"[cloud_fetch] weather WARN {city}: {exc}", file=sys.stderr)
    return out


def emit_weather(weather_by_city):
    lines = ["# game-weekend forecast per host city (Open-Meteo)"]
    for city, txt in weather_by_city.items():
        lines.append(f"{city}: {txt}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- injuries
NOISE = ("news", "squad", "latest", "fixtures", "ladder", "draw", "tickets", "membership",
         "highlights", "video", "signing", "contract", "preview", "wrap")


def team_from_link(a):
    """Resolve a Zero Tackle team link to our short code. Handles both
    /nrl/teams/<slug>/ and /rugby-league/teams/<slug>/. Falls back to the link
    text ('Broncos') when the slug doesn't resolve."""
    m = TEAM_HREF_RE.search((a.get("href") or "").split("?")[0].rstrip("/") + "/")
    if m:
        s = find_short(m.group(1).replace("-", " "))
        if s:
            return s
    txt = a.get_text(" ", strip=True)
    return find_short(txt) if txt and len(txt) < 40 else None


def club_before(table):
    """Nearest preceding team link — the injuries page labels each club with a
    bare <a> to its team page, NOT a heading, so heading-tracking silently found
    zero clubs and the whole injuries parse returned {}. Scan backwards instead."""
    for a in table.find_all_previous("a", href=True):
        s = team_from_link(a)
        if s:
            return s
    return None


def extract_injuries(html):
    """Zero Tackle's injuries page lists each club as a link followed by a table
    of Player | Reason | Expected Return rows. Attribute each table to the
    nearest club label above it and parse its data rows into clean
    'Player (reason) — back Return' entries (header rows / photo cells / stray
    fragments skipped). First few per club."""
    soup = BeautifulSoup(html, "html.parser")
    teams, current = {}, None
    for el in soup.find_all(["h1", "h2", "h3", "h4", "strong", "table"]):
        if el.name != "table":
            txt = el.get_text(" ", strip=True)
            s = find_short(txt)
            if s and len(txt) < 40 and not any(w in txt.lower() for w in NOISE):
                current = s
                teams.setdefault(current, [])
            continue
        # A club link immediately above the table beats whatever heading we last
        # saw; headings are only a fallback for a future page redesign.
        club = club_before(el) or current
        if not club:
            continue
        current = club
        teams.setdefault(current, [])
        for tr in el.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if len(cells) < 2:
                continue
            joined = " ".join(cells).lower()
            if cells[0].lower() in ("player", "name") or ("reason" in joined and "return" in joined):
                continue  # header row
            player, reason = cells[0], cells[1]
            ret = cells[2] if len(cells) > 2 else ""
            entry = player
            if reason and reason.lower() != reason.upper():  # a word, not a stray code
                entry += f" ({reason})"
            if ret and ret.upper() not in ("TBC", "TBD", "UNKNOWN", "-"):
                entry += f" — back {ret}"
            teams[current].append(entry)
    out = {}
    for s, items in teams.items():
        seen = []
        for it in items:
            if it and it not in seen:
                seen.append(it)
        if seen:
            out[s] = "; ".join(seen[:6])
    return out


def emit_injuries(news_by_short):
    lines = ["<!-- rebuilt by cloud_fetch.py from the live Zero Tackle injuries page -->"]
    for short, txt in news_by_short.items():
        lines.append(f"{TEAMS[short]['name']}: {txt}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- player ratings
# norm_name() lives in parse_nrl.py and is imported at the top of this file — it
# must stay identical to normName() in the HTML, and one copy is easier to keep
# honest than two.


def _clean_name(raw):
    """Strip a trailing team block from a 'Player Name Team...' blob using the
    same team recogniser the ladder uses. Prefer the longest team suffix that
    still leaves a >=2-word name. Returns '' if nothing sensible left."""
    words = raw.split()
    n = len(words)
    for k in range(2, n):                         # longest team suffix, name>=2 words
        if find_short(" ".join(words[k:])):
            cand = " ".join(words[:k]).strip(" -–—")
            if 3 <= len(cand) <= 40:
                return cand
    for k in range(n - 1, 0, -1):                 # fallback: any trailing team
        if find_short(" ".join(words[k:])):
            cand = " ".join(words[:k]).strip(" -–—")
            if 3 <= len(cand) <= 40:
                return cand
    return raw.strip(" -–—") if 3 <= len(raw) <= 40 else ""


def _letters(s):
    return re.sub(r"[^a-z]", "", str(s or "").lower())


def name_from_anchor(a):
    """Zero Tackle renders a player's name TWICE inside the <a> (desktop + mobile
    variants) with no separator: 'Isaiah IongiIsaiah Iongi', or abbreviated+full
    'K. Leuluai-GoingKalani Leuluai-Going'. The href slug is canonical, so use it
    to pick the variant whose letters match — which also preserves real
    punctuation (Papali'i, Addo-Carr). Returns (display_name, slug_name)."""
    m = PLAYER_HREF_RE.search((a.get("href") or "").split("?")[0].rstrip("/") + "/")
    if not m:
        return "", ""
    slug = m.group(1)
    slug_name = " ".join(w.capitalize() for w in slug.split("-"))
    txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
    target = _letters(slug)
    if _letters(txt) == target:
        return txt, slug_name
    for i in range(1, len(txt)):
        right = txt[i:].strip()
        if _letters(right) == target:
            return right, slug_name
        left = txt[:i].strip()
        if _letters(left) == target:
            return left, slug_name
    return slug_name, slug_name                       # last resort: title-cased slug


def extract_ratings(html, pos=None):
    """Zero Tackle player-ratings page -> {norm_name: {name, pos, pct}}.

    Built for the PER-POSITION pages: rows are rank | Player | Team | Win % |
    Rating | move, with no position column because the position is implied by the
    URL — pass it in as `pos`. Still works on /overall/, where it reads a position
    cell instead. The name always comes from the /players/<slug>/ anchor, never
    from a cell index, and a one-word key is never emitted (see the note on
    RATING_POS_BY_SLUG — that bug disabled injuries entirely).

    Each page carries a season table then a monthly one; the season table comes
    first and setdefault keeps the first, which is what we want."""
    soup = BeautifulSoup(html, "html.parser")
    players = {}
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue
        pct = None
        for c in cells:
            m = re.match(r"^(\d{1,3}(?:\.\d+)?)\s*%$", c)
            if m:
                pct = float(m.group(1))
                break
        if pct is None:
            continue                                   # header / non-data row
        row_pos = pos or next((_POS_CANON[c.lower()] for c in cells
                               if c.lower() in _POS_CANON), None)
        if row_pos is None:
            continue
        anchors = [a for a in tr.find_all("a", href=True)
                   if PLAYER_HREF_RE.search((a.get("href") or "").rstrip("/") + "/")]
        if not anchors:
            continue
        name, slug_name = name_from_anchor(anchors[0])
        key = norm_name(name)
        if len(key.split()) < 2:                       # never emit a first-name-only key
            key = norm_name(slug_name)
            if len(key.split()) < 2:
                continue
            name = slug_name
        rec = {"name": name, "pos": row_pos, "pct": round(pct, 1)}
        players.setdefault(key, rec)
        alias = norm_name(slug_name)                   # punctuation-free alias, free matching
        if len(alias.split()) >= 2:
            players.setdefault(alias, rec)
    return players


def fetch_all_ratings():
    """Merge the nine per-position ratings pages into one {norm_name: {...}}."""
    players = {}
    for slug, pos in RATING_POS_BY_SLUG.items():
        try:
            got = extract_ratings(fetch(RATINGS_URL_TPL.format(slug)), pos)
        except Exception as exc:  # noqa: BLE001
            print(f"[cloud_fetch] ratings WARN {slug}: {exc}", file=sys.stderr)
            continue
        print(f"[cloud_fetch] ratings {slug}: {len(got)} keys")
        for k, v in got.items():
            players.setdefault(k, v)
    return players


def emit_players(players):
    import json
    body = ",\n".join(
        f'  {json.dumps(k)}: {{"pos": {json.dumps(v["pos"])}, "pct": {v["pct"]}}}'
        for k, v in sorted(players.items())
    )
    return ("/* rebuilt by cloud_fetch.py from the live Zero Tackle player ratings.\n"
            "   name -> {pos, pct}. Used by the front-end to weight injuries by the\n"
            "   real player: spine positions + higher rating = bigger tip impact. */\n"
            "window.NRL_PLAYERS = {\n" + body + "\n};\n")


# --------------------------------------------------------------------------- team lists
def latest_teamlists_url(index_html):
    """The team-lists section index links to ROOT-level articles, not children of
    /nrl/team-lists/ — e.g. /round-21-team-lists-2026-236116/. Return the URL for
    the highest round number found, or (None, None)."""
    soup = BeautifulSoup(index_html, "html.parser")
    best = (None, None)
    for a in soup.find_all("a", href=True):
        m = TEAMLIST_ARTICLE_RE.search(a["href"])
        if not m:
            continue
        rnd = int(m.group(1))
        if best[0] is None or rnd > best[0]:
            href = a["href"]
            if href.startswith("/"):
                href = "https://www.zerotackle.com" + href
            best = (rnd, href)
    return best


GAME_HEAD_RE = re.compile(r"\bvs\.?\b.*team list", re.I)
RESERVES_RE = re.compile(r"^\s*RESERVES?\s*$", re.I)


def _squad_tokens(box):
    """Ordered token stream for a candidate squad container.

    Zero Tackle leaves <tr> UNCLOSED on every player row, so html.parser nests
    the rows inside one another and per-row parsing is unreliable. Walking
    .descendants sidesteps that entirely: it is plain document order whatever
    the nesting. Yields ('num', int) for a bare jersey-number cell,
    ('player', <a>) for a /players/ link, ('mark', text) for an
    INTERCHANGE / RESERVES separator."""
    toks = []
    for node in box.descendants:
        if isinstance(node, NavigableString):
            s = str(node).replace("\xa0", " ").strip()
            if not s:
                continue
            if s.isdigit() and len(s) <= 2:
                toks.append(("num", int(s)))
            elif RESERVES_RE.match(s) or re.match(r"^\s*INTERCHANGE\s*$", s, re.I):
                toks.append(("mark", s.upper()))
        elif getattr(node, "name", None) == "a" and node.get("href"):
            if PLAYER_HREF_RE.search(node["href"].split("?")[0].rstrip("/") + "/"):
                toks.append(("player", node))
    return toks


def _is_squad(toks):
    """A real squad has both a pile of player links and a pile of jersey
    numbers. The site nav / footer mega-menu has /players/<slug>/ links too
    (Oldest & Youngest, Player Birthdays, OFF CONTRACT ...) but no numbers —
    that is what stops a menu being mistaken for a team list."""
    return (sum(1 for k, _ in toks if k == "player") >= 13
            and sum(1 for k, _ in toks if k == "num") >= 13)


def _home_first(toks):
    """True when the jersey number precedes the name (the home column)."""
    before = after = 0
    for i, (kind, _) in enumerate(toks):
        if kind != "player":
            continue
        if i and toks[i - 1][0] == "num":
            before += 1
        if i + 1 < len(toks) and toks[i + 1][0] == "num":
            after += 1
    return before >= after


def _squad_names(toks, drop_reserves=True):
    """Names in listed order. Stops at the RESERVES separator: 20-22 are
    emergencies who are NOT in the match-day squad, so counting them would
    wrongly cancel a genuine injury flag. Everything above it (the 13 starters
    plus the full interchange bench) is really named to play.

    Do NOT filter on jersey number <= 17 instead — the number is not a selection
    signal. Parramatta named #22 at centre in Round 21 while #11 and #14 sat on
    the bench. The structural separator is the only reliable cut."""
    names, seen = [], set()
    for kind, val in toks:
        if kind == "mark" and drop_reserves and RESERVES_RE.match(val):
            break
        if kind != "player":
            continue
        nm, slug_nm = name_from_anchor(val)
        for cand in (nm, slug_nm):
            if cand and cand not in seen:
                seen.add(cand)
                names.append(cand)
    return names


def extract_teamlists(html):
    """Round team-lists article -> {short: {"round": N, "opp": SHORT, "players": [...]}}.

    Layout: an <h2> per game ('Eels vs Panthers Team Lists: Round 21') followed
    by THREE <table width='100%'> blocks — home squad, a positions-only table,
    then the away squad. The home table puts the jersey number in the first
    <td> and the name in the second; the away table reverses them. INTERCHANGE
    and RESERVES separators are <td colspan='3'> rows. There are NO <ul>/<li>
    elements anywhere in the article — an earlier version of this function
    looked for <ul>s, found only the site's footer mega-menu, and published
    "Off Contract 2026" as a Wests Tigers player. The page renders as bullets
    in a markdown view, which is what caused that mistake; trust the DOM.

    Traversal is inverted deliberately: find the squad tables first by what they
    CONTAIN (>=13 player links AND >=13 jersey numbers), then attach each to its
    nearest preceding game heading. Scanning forward from a heading is what let
    the last game run off the end of the article into the nav menus.

    There are no 'Ins:'/'Outs:' labels on the page; this is the named squad,
    which is all the front-end needs to cancel a stale injury entry."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. every container that really looks like a squad, in document order.
    cands = []
    for box in soup.find_all(["table", "ul", "ol"]):
        toks = _squad_tokens(box)
        if _is_squad(toks):
            cands.append((box, toks))
    # drop outer wrappers when a nested container already qualified
    inner = [(b, t) for b, t in cands
             if not any(o is not b and o in b.descendants for o, _ in cands)]

    # 2. attach each squad to its nearest preceding game heading.
    by_head = {}
    for box, toks in inner:
        head = next((h for h in box.find_all_previous(["h1", "h2", "h3", "h4"])
                     if GAME_HEAD_RE.search(h.get_text(" ", strip=True))), None)
        if head is not None:
            by_head.setdefault(id(head), (head, []))[1].append((box, toks))

    out = {}
    for head, boxes in by_head.values():
        title = head.get_text(" ", strip=True)
        m = re.match(r"^(.*?)\s+vs\.?\s+(.*?)\s+Team List", title, re.I)
        if not m:
            continue
        home, away = find_short(m.group(1)), find_short(m.group(2))
        rm = re.search(r"Round\s+(\d+)", title, re.I)
        rnd = int(rm.group(1)) if rm else None

        # 3. home vs away: the number-first column is the home side. Document
        #    order breaks the tie if the two columns somehow look alike, and
        #    the orientation alone decides it when only one side has been
        #    published yet (lists trickle out on Tuesday afternoon).
        picked = boxes[:2]
        h_squad = a_squad = None
        if len(picked) == 2:
            if _home_first(picked[1][1]) and not _home_first(picked[0][1]):
                picked = [picked[1], picked[0]]
            h_squad, a_squad = (_squad_names(picked[0][1]),
                                _squad_names(picked[1][1]))
        elif picked:
            if _home_first(picked[0][1]):
                h_squad = _squad_names(picked[0][1])
            else:
                a_squad = _squad_names(picked[0][1])

        for short, squad, opp in ((home, h_squad, away),
                                  (away, a_squad, home)):
            if short and squad:
                out.setdefault(short, {"round": rnd, "opp": opp, "players": squad})
    return out


def emit_lineups(lineups, rnd):
    import json
    body = ",\n".join(
        f'    {json.dumps(s)}: {json.dumps(v["players"], ensure_ascii=False)}'
        for s, v in sorted(lineups.items())
    )
    return ("/* rebuilt by cloud_fetch.py from the live Zero Tackle team lists.\n"
            "   The named squad per club for the round below. The front-end uses this to\n"
            "   cancel an injury-table entry for a player who is actually named in the\n"
            "   side — without it, a season-long 'TBC' keeps a fit player half-out\n"
            "   forever. Empty/stale is safe: the model just falls back to the\n"
            "   injury table alone. */\n"
            "window.NRL_LINEUPS = {\n"
            f'  "round": {json.dumps(rnd)},\n'
            '  "teams": {\n' + body + "\n  }\n};\n")


def write(path, text):
    """Atomic write: temp file then os.replace, so an interrupted or crashing
    run can never leave a half-written dump that clobbers a good one."""
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def preserve(path, backup_path):
    """Keep the outgoing copy of a generated file so the next stage can diff it.
    Used for nrl_lineups.js: it is rewritten in place every run, so without a
    snapshot there is nothing to compare 'who is named this time' against."""
    try:
        if os.path.exists(path):
            shutil.copyfile(path, backup_path)
            return True
    except OSError as exc:
        print(f"[cloud_fetch] WARNING: could not preserve {path} -> {backup_path}: {exc}",
              file=sys.stderr)
    return False


def existing_draw(path):
    """(round, fixture_count) of the COMMITTED draw dump, or (None, 0).

    The publish gate needs the committed dump's own fixture count, not a bare
    range: if Zero Tackle's draw fails and nrl.com only resolves 6 of 8
    nicknames, "6 <= n <= 9" happily overwrites a good 8-fixture dump with a
    short one. ARCHITECTURE.md's promise is the opposite — a source that won't
    parse confidently leaves the committed dump untouched."""
    rnd, pairs = None, set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if rnd is None:
                    m = re.search(r"<h2>\s*Round\s+(\d{1,2})", line, re.IGNORECASE)
                    if m:
                        rnd = int(m.group(1))
                        continue
                m = re.match(r"\s*<p>(.+?)\s+v\s+(.+?)</p>", line, re.IGNORECASE)
                if not m:
                    continue
                # find_short(), not an exact name match: the committed dump may
                # carry fuller club names ("North Queensland Cowboys") than
                # emit_draw() writes today.
                home, away = find_short(m.group(1)), find_short(m.group(2))
                if home and away and home != away:
                    pairs.add(frozenset((home, away)))
    except OSError:
        return None, 0
    return rnd, len(pairs)


def existing_odds_round(path):
    """The round a committed odds dump was written for, or None."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for _ in range(3):
                line = fh.readline()
                if not line:
                    break
                m = re.search(r"round\s+(\d{1,2})", line, re.IGNORECASE)
                if m:
                    return int(m.group(1))
    except OSError:
        pass
    return None


# --------------------------------------------------------------------------- main
def main():
    # ----- ladder (critical) -----
    try:
        teams, debug = extract_ladder(fetch(LADDER_URL))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not fetch ladder: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"[cloud_fetch] ladder: extracted {len(teams)} teams")
    for line in debug[:20]:
        print("    " + line)
    if len(teams) < 17:
        print("[cloud_fetch] WARNING: <17 teams — leaving ladder_dump.html untouched.", file=sys.stderr)
        sys.exit(1)
    write("ladder_dump.html", emit_ladder(teams))
    print("[cloud_fetch] wrote ladder_dump.html")

    # ----- fixtures page: powers both the draw and the finished-results dump -----
    fixtures_html = None
    round_fixtures = []
    rnd = None
    try:
        fixtures_html = fetch(FIXTURES_URL)
        rnd, round_fixtures = extract_draw(fixtures_html)
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: fixtures fetch/parse failed ({exc}); keeping draw_dump.html", file=sys.stderr)
        rnd = None

    # ----- the official nrl.com draw: odds + venue + kick-off -----------------
    zt_round, zt_fixtures = rnd, list(round_fixtures)
    nrl_payload = fetch_nrl_draw(SEASON, zt_round)
    nrl_round, nrl_fixtures, nrl_byes, show_odds = None, [], [], False
    if nrl_payload is not None:
        nrl_round, nrl_fixtures, nrl_byes, show_odds = parse_nrl_draw(nrl_payload)
        print(f"[cloud_fetch] nrl.com: round {nrl_round}, {len(nrl_fixtures)} fixtures, "
              f"bye={nrl_byes or '-'}, showOdds={show_odds}")
        for f in nrl_fixtures:
            print(f"    {f['home']} v {f['away']} @ {f['venue'] or '?'} ({f['city'] or '?'}) "
                  f"{f['kickoffUtc'] or '?'} odds {f['homeOdds']}/{f['awayOdds']}")
    rnd, round_fixtures, _flips = reconcile_draw(zt_round, zt_fixtures, nrl_round, nrl_fixtures)

    # nrl.com data is only usable if it describes the round we're actually
    # publishing — stale metadata is worse than none.
    nrl_usable = bool(nrl_fixtures) and (not rnd or not nrl_round or int(nrl_round) == int(rnd))

    # Publish gate: a plausible count AND — for the round already on disk — never
    # fewer fixtures than the committed dump already has. A partial parse (Zero
    # Tackle down + nrl.com nicknames unresolved) is exactly the case that used to
    # slip through the bare 6..9 range and shrink a good 8-fixture dump.
    committed_round, committed_n = existing_draw("draw_dump.html")
    plausible = bool(rnd) and 6 <= len(round_fixtures) <= 9
    shrinks = (plausible and committed_n and committed_round == rnd
               and len(round_fixtures) < committed_n)
    if plausible and not shrinks:
        write("draw_dump.html", emit_draw(rnd, round_fixtures))
        print(f"[cloud_fetch] wrote draw_dump.html: Round {rnd}, {len(round_fixtures)} fixtures "
              f"({', '.join(h + 'v' + a for h, a in round_fixtures)})")
    elif shrinks:
        print(f"[cloud_fetch] draw parse came back short (round {rnd}: {len(round_fixtures)} "
              f"fixtures vs {committed_n} already committed for that round) — keeping the "
              f"committed draw_dump.html rather than shrinking it.", file=sys.stderr)
    else:
        print(f"[cloud_fetch] draw looked off (round={rnd}, {len(round_fixtures)} fixtures) — "
              f"keeping committed draw_dump.html.", file=sys.stderr)

    # ----- odds dump (best-effort; prices land around Tuesday) ----------------
    if nrl_usable and round_fixtures:
        if not show_odds:
            print("[cloud_fetch] nrl.com has showOdds=false this round — not publishing prices.",
                  file=sys.stderr)
        else:
            text, n_odds = emit_odds(rnd, nrl_fixtures, round_fixtures)
            if n_odds:
                write("odds_dump.txt", text)
                print(f"[cloud_fetch] wrote odds_dump.txt: {n_odds}/{len(round_fixtures)} fixtures priced")
            elif existing_odds_round("odds_dump.txt") not in (None, rnd):
                # No prices yet AND the committed dump is for a different round.
                # Leaving it would let last round's price attach to a repeat
                # matchup, so clear it down to the header instead.
                write("odds_dump.txt", text)
                print(f"[cloud_fetch] no prices yet for round {rnd} — cleared the stale "
                      f"odds_dump.txt from an earlier round.", file=sys.stderr)
            else:
                print(f"[cloud_fetch] no prices published yet for round {rnd} — keeping the "
                      f"committed odds_dump.txt. Normal before Tuesday.", file=sys.stderr)
    elif nrl_fixtures:
        print(f"[cloud_fetch] nrl.com data is for round {nrl_round}, not {rnd} — skipping "
              f"odds and venue/kick-off metadata this run.", file=sys.stderr)

    # ----- venue / city / kick-off metadata ----------------------------------
    if nrl_usable and round_fixtures:
        text, n_meta = emit_draw_meta(SEASON, rnd, nrl_fixtures, round_fixtures)
        if n_meta >= max(1, len(round_fixtures) - 1):
            write("draw_meta.json", text)
            print(f"[cloud_fetch] wrote draw_meta.json: {n_meta} fixtures with venue/kick-off")
        else:
            print(f"[cloud_fetch] draw metadata thin ({n_meta}/{len(round_fixtures)}) — keeping "
                  f"the committed draw_meta.json.", file=sys.stderr)

    # ----- finished results (best-effort): every played game's score -> results_dump.txt,
    # which parse_nrl.py appends to the learning-loop memory. This is what makes recent
    # form + home/away splits real and grows the model toward switching on Elo. -----
    if fixtures_html is not None:
        try:
            results = extract_results(fixtures_html)
        except Exception as exc:  # noqa: BLE001
            print(f"[cloud_fetch] WARNING: results parse failed ({exc}); keeping results_dump.txt", file=sys.stderr)
            results = []
        if len(results) >= 8:
            write("results_dump.txt", emit_results(results))
            rounds = sorted({r["round"] for r in results})
            print(f"[cloud_fetch] wrote results_dump.txt: {len(results)} finished games "
                  f"across rounds {rounds[0]}–{rounds[-1]}")
        else:
            print(f"[cloud_fetch] results parse thin ({len(results)} games) — keeping committed results_dump.txt.", file=sys.stderr)

    # ----- weather (best-effort; always leaves a valid file) -----
    # Forecast the city the game is ACTUALLY in. Deriving it from the home club
    # instead gives Penrith's Sydney forecast for a game in Mudgee — and now that
    # fixture.city comes from nrl.com's venueCity, parse_nrl's city-keyed lookup
    # would find no line at all for it and publish weather:null.
    home_shorts = {h for h, _a in round_fixtures} or set(TEAMS)
    cities = {TEAM_HOME_CITY.get(s) for s in home_shorts if TEAM_HOME_CITY.get(s)}
    if nrl_usable:
        venue_cities = {f["city"] for f in nrl_fixtures
                        if f["city"] and frozenset((f["home"], f["away"]))
                        in {frozenset(p) for p in round_fixtures}}
        unknown = {c for c in venue_cities if c not in CITY_COORDS}
        if unknown:
            print(f"[cloud_fetch] NOTE: no coordinates for host city/cities {sorted(unknown)} — "
                  f"add them to CITY_COORDS for a real forecast.", file=sys.stderr)
        cities = (cities | venue_cities)
    weather = fetch_weather(cities)
    if weather:
        write("weather_dump.txt", emit_weather(weather))
        print(f"[cloud_fetch] wrote weather_dump.txt for {len(weather)} cities: "
              + " | ".join(f"{c}: {t}" for c, t in weather.items()))
    else:
        write("weather_dump.txt", "# no weather this run\n")
        print("[cloud_fetch] WARNING: no weather fetched; wrote placeholder.", file=sys.stderr)

    # ----- injuries (best-effort; keep committed file if parse looks thin) -----
    try:
        news = extract_injuries(fetch(INJURIES_URL))
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: injuries fetch/parse failed ({exc}); keeping injuries_dump.html", file=sys.stderr)
        news = {}
    print(f"[cloud_fetch] injuries: parsed news for {len(news)} clubs")
    for short, txt in list(news.items())[:20]:
        print(f"    {short}: {txt[:80]}")
    if len(news) >= 6:
        write("injuries_dump.html", emit_injuries(news))
        print("[cloud_fetch] wrote injuries_dump.html")
    else:
        print("[cloud_fetch] injuries parse thin (<6 clubs) — keeping committed injuries_dump.html.", file=sys.stderr)

    # ----- player ratings -> nrl_players.js (best-effort; keep committed file if thin) -----
    try:
        players = fetch_all_ratings()
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: ratings fetch/parse failed ({exc}); keeping nrl_players.js", file=sys.stderr)
        players = {}
    multiword = sum(1 for k in players if " " in k)
    share = (multiword / len(players)) if players else 0.0
    print(f"[cloud_fetch] ratings: parsed {len(players)} players "
          f"({multiword} full-name keys, {share:.0%})")
    for k, v in list(players.items())[:8]:
        print(f"    {v['name']} — {v['pos']} {v['pct']}%")
    # Two gates, not one. Volume alone let a page of FIRST-NAME-ONLY keys through
    # and silently neutered every injury lookup for weeks; a name key that isn't
    # a full name can never match the front-end, so treat it as a failed parse.
    if len(players) >= 100 and share >= 0.8:
        write("nrl_players.js", emit_players(players))
        print("[cloud_fetch] wrote nrl_players.js")
    else:
        why = "thin (<100 players)" if len(players) < 100 else f"malformed ({share:.0%} full-name keys, need 80%)"
        print(f"[cloud_fetch] ERROR: ratings parse {why}. Keeping the committed nrl_players.js, "
              f"but injuries will NOT be weighted correctly until this is fixed.", file=sys.stderr)

    # ----- team lists -> nrl_lineups.js (best-effort; released ~4pm Tue AEST) -----
    lineups, tl_round = {}, None
    try:
        tl_round, tl_url = latest_teamlists_url(fetch(TEAMLISTS_INDEX_URL))
        if tl_url:
            print(f"[cloud_fetch] team lists: newest article is Round {tl_round} — {tl_url}")
            lineups = extract_teamlists(fetch(tl_url))
        else:
            print("[cloud_fetch] WARNING: no round team-lists article found on the index.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: team-lists fetch/parse failed ({exc}); keeping nrl_lineups.js", file=sys.stderr)
        lineups = {}
    for s, v in list(lineups.items())[:20]:
        print(f"    {s}: {len(v['players'])} named v {v['opp']}")
    if len(lineups) >= 6:
        # Snapshot the outgoing copy FIRST. nrl_lineups.js is rewritten in place,
        # so without this there is nothing for parse_nrl.py to diff and the
        # "named in the 17" / "out of the 17" half of the change feed can never
        # fire. Losing the snapshot is harmless — the diff just goes quiet.
        preserve("nrl_lineups.js", "nrl_lineups.prev.js")
        write("nrl_lineups.js", emit_lineups(lineups, tl_round))
        print(f"[cloud_fetch] wrote nrl_lineups.js: Round {tl_round}, {len(lineups)} clubs "
              f"(previous copy kept as nrl_lineups.prev.js for the change feed)")
    else:
        print(f"[cloud_fetch] team lists thin ({len(lineups)} clubs) — keeping committed nrl_lineups.js. "
              f"Normal on Mon/Tue morning: lists drop ~4pm Tuesday AEST.", file=sys.stderr)


if __name__ == "__main__":
    main()
