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

Anything that can't be parsed confidently is left as the previous committed
file (never wipes good data). Network access is fine here (GitHub servers).
"""
import datetime
import re
import sys

import requests
from bs4 import BeautifulSoup

from parse_nrl import find_short, TEAMS, TEAM_HOME_CITY  # side-effect free import

HEADERS = {"User-Agent": "footy-tipping-personal/1.0 (non-commercial; polite; low-frequency)"}
LADDER_URL = "https://www.zerotackle.com/nrl/nrl-ladder/"
FIXTURES_URL = "https://www.zerotackle.com/nrl/fixtures-results/"
INJURIES_URL = "https://www.zerotackle.com/nrl/injuries-suspensions/"
RATINGS_URL = "https://www.zerotackle.com/nrl-player-ratings/overall/"

# Player positions as they appear on the ratings page (closed set).
RATING_POSITIONS = ["Five-eighth", "Second-row", "Fullback", "Halfback", "Hooker",
                    "Winger", "Centre", "Prop", "Lock"]
_POS_RE = re.compile(r"\b(" + "|".join(RATING_POSITIONS) + r")\b", re.IGNORECASE)
_POS_CANON = {p.lower(): p for p in RATING_POSITIONS}

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
         "highlights", "video", "signing", "contract", "team list", "preview", "wrap")


def extract_injuries(html):
    """Zero Tackle's injuries page lists each club as a heading followed by a
    table of Player | Reason | Expected Return rows. Track the 'current club'
    from headings and parse the following table's data rows into clean
    'Player (reason) — back Return' entries (header rows / stray fragments
    skipped). First few per club."""
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
        if not current:
            continue
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
def norm_name(s):
    """Match the front-end normName(): lowercase, strip accents/punct, collapse
    spaces. Keeps apostrophes and hyphens so 'Cherry-Evans' / \"Olakau'atu\" match."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z\s'-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


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


def extract_ratings(html):
    """Parse the overall player-ratings page into {norm_name: {name,pos,pct}}.
    Primary path: real table rows (player-profile anchor + a position cell + a
    NN.NN% cell). Fallback: regex over the flattened page text. Either way we
    only keep entries with a recognised position and a percentage."""
    soup = BeautifulSoup(html, "html.parser")
    players = {}

    # ---- primary: structured rows ----
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        a = tr.find("a", href=re.compile(r"/rugby-league/players/"))
        name = a.get_text(" ", strip=True) if a else None
        pos = next((_POS_CANON[c.lower()] for c in cells if c.lower() in _POS_CANON), None)
        pct = None
        for c in cells:
            m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", c)
            if m:
                pct = float(m.group(1))
                break
        if not name and pos and pct is not None:          # no anchor: derive from cells
            blob = " ".join(cells)
            blob = _POS_RE.split(blob)[0]
            name = _clean_name(blob)
        if not name or not pos or pct is None:
            continue
        key = norm_name(name)
        if key and key not in players:
            players[key] = {"name": name, "pos": pos, "pct": round(pct, 1)}

    # ---- fallback: flattened text ----
    if len(players) < 50:
        text = soup.get_text(" ", strip=True)
        pat = re.compile(r"([A-Za-zÀ-ÿ'’.\- ]{3,60}?)\s+(" + "|".join(RATING_POSITIONS) +
                         r")\s+(\d{1,3}(?:\.\d+)?)\s*%", re.IGNORECASE)
        for m in pat.finditer(text):
            name = _clean_name(re.sub(r"^\d+\s+", "", m.group(1)).strip())
            pos = _POS_CANON[m.group(2).lower()]
            pct = float(m.group(3))
            key = norm_name(name)
            if key and key not in players:
                players[key] = {"name": name, "pos": pos, "pct": round(pct, 1)}
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


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


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

    # ----- draw (best-effort) -----
    round_fixtures = []
    try:
        rnd, round_fixtures = extract_draw(fetch(FIXTURES_URL))
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: fixtures fetch/parse failed ({exc}); keeping draw_dump.html", file=sys.stderr)
        rnd = None
    if rnd and 6 <= len(round_fixtures) <= 9:
        write("draw_dump.html", emit_draw(rnd, round_fixtures))
        print(f"[cloud_fetch] wrote draw_dump.html: Round {rnd}, {len(round_fixtures)} fixtures "
              f"({', '.join(h + 'v' + a for h, a in round_fixtures)})")
    else:
        print(f"[cloud_fetch] draw looked off (round={rnd}, {len(round_fixtures)} fixtures) — "
              f"keeping committed draw_dump.html.", file=sys.stderr)

    # ----- weather (best-effort; always leaves a valid file) -----
    home_shorts = {h for h, _a in round_fixtures} or set(TEAMS)
    cities = {TEAM_HOME_CITY.get(s) for s in home_shorts if TEAM_HOME_CITY.get(s)}
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
        players = extract_ratings(fetch(RATINGS_URL))
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: ratings fetch/parse failed ({exc}); keeping nrl_players.js", file=sys.stderr)
        players = {}
    print(f"[cloud_fetch] ratings: parsed {len(players)} players")
    for k, v in list(players.items())[:8]:
        print(f"    {v['name']} — {v['pos']} {v['pct']}%")
    if len(players) >= 100:
        write("nrl_players.js", emit_players(players))
        print("[cloud_fetch] wrote nrl_players.js")
    else:
        print("[cloud_fetch] ratings parse thin (<100 players) — keeping committed nrl_players.js.", file=sys.stderr)


if __name__ == "__main__":
    main()
