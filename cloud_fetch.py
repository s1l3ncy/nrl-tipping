#!/usr/bin/env python3
"""
cloud_fetch.py — runs on GitHub Actions (NOT on the Mac).

Fetches the LIVE Zero Tackle NRL pages and rebuilds the clean dump files that
parse_nrl.py expects (parse_nrl does its own <td>->pipe / tag handling, so it
needs real tags, not flattened text — that was the original bug).

  * ladder_dump.html — the current standings (P/W/L, points for/against),
    rebuilt from the live ladder table.
  * draw_dump.html   — the NEXT round's fixtures, derived from the fixtures /
    results page. The upcoming round = the lowest round number whose games are
    not yet marked "fulltime". This auto-advances every week (incl. finals as
    soon as Zero Tackle publishes the matchups) — nothing is hard-coded.

If a page can't be parsed confidently it leaves the previous dump in place
(never wipes good data) so the pipeline degrades gracefully.

Network access is fine here because this runs on GitHub's servers.
"""
import re
import sys

import requests
from bs4 import BeautifulSoup

from parse_nrl import find_short, TEAMS  # side-effect free import (has __main__ guard)

HEADERS = {"User-Agent": "footy-tipping-personal/1.0 (non-commercial; polite; low-frequency)"}
LADDER_URL = "https://www.zerotackle.com/nrl/nrl-ladder/"
FIXTURES_URL = "https://www.zerotackle.com/nrl/fixtures-results/"

# Zero Tackle URL-slug nickname for each club short code.
ZT_SLUG = {
    "PEN": "panthers", "SYD": "roosters", "NZW": "warriors", "CRO": "sharks",
    "DOL": "dolphins", "SOU": "rabbitohs", "NEW": "knights", "NQL": "cowboys",
    "MAN": "sea-eagles", "CAN": "bulldogs", "CBR": "raiders", "MEL": "storm",
    "BRI": "broncos", "PAR": "eels", "WST": "wests-tigers", "GLD": "titans",
    "STI": "dragons",
}
SLUG_TO_SHORT = {v: k for k, v in ZT_SLUG.items()}
# Longest slugs first so a shorter slug can't mis-split a compound one.
SLUGS_BY_LEN = sorted(SLUG_TO_SHORT, key=len, reverse=True)

MATCH_SLUG_RE = re.compile(r"/(fulltime-)?([a-z0-9-]+)-round-(\d+)-20\d\d", re.IGNORECASE)


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
        big = [n for n in nums if n >= 100]        # PF, PA
        if len(big) < 2:
            continue
        pf, pa = big[0], big[1]
        smalls = [n for n in nums if 0 <= n < 100]  # rank, P, W, L, D, (B), PTS
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
    """Split 'raiders-wests-tigers' -> ('CBR','WST') using the known slug set."""
    for home_slug in SLUGS_BY_LEN:
        prefix = home_slug + "-"
        if teams_part.startswith(prefix):
            away_slug = teams_part[len(prefix):]
            if away_slug in SLUG_TO_SHORT:
                return SLUG_TO_SHORT[home_slug], SLUG_TO_SHORT[away_slug]
    return None, None


def extract_draw(html):
    """Return (round_number, [(home_short, away_short), ...]) for the next
    unplayed round, or (None, []) if it can't be determined."""
    soup = BeautifulSoup(html, "html.parser")
    by_round = {}          # round -> {frozenset(pair): (home, away, played)}
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
        # keep a "played" sighting over an unplayed one if both appear
        if key not in slot or played:
            slot[key] = (home, away, played)

    if not by_round:
        return None, []
    # Next round = lowest round with at least one game NOT yet played.
    unplayed_rounds = sorted(r for r, games in by_round.items() if any(not p for (_, _, p) in games.values()))
    if not unplayed_rounds:
        return None, []
    rnd = unplayed_rounds[0]
    fixtures = [(h, a) for (h, a, _played) in by_round[rnd].values()]
    return rnd, fixtures


def emit_draw(rnd, fixtures):
    out = [f"<!-- rebuilt by cloud_fetch.py from the live Zero Tackle fixtures page -->",
           f"<h2>Round {rnd}</h2>"]
    for home, away in fixtures:
        out.append(f"<p>{TEAMS[home]['name']} v {TEAMS[away]['name']}</p>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- main
def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def main():
    # ----- ladder (critical) -----
    try:
        ladder_html = fetch(LADDER_URL)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not fetch ladder: {exc}", file=sys.stderr)
        sys.exit(1)
    teams, debug = extract_ladder(ladder_html)
    print(f"[cloud_fetch] ladder: extracted {len(teams)} teams")
    for line in debug[:20]:
        print("    " + line)
    if len(teams) < 17:
        print("[cloud_fetch] WARNING: <17 teams — leaving ladder_dump.html untouched.", file=sys.stderr)
        sys.exit(1)
    with open("ladder_dump.html", "w", encoding="utf-8") as fh:
        fh.write(emit_ladder(teams))
    print("[cloud_fetch] wrote ladder_dump.html")

    # ----- draw (best-effort; keep the committed file if it looks wrong) -----
    try:
        fixtures_html = fetch(FIXTURES_URL)
        rnd, fixtures = extract_draw(fixtures_html)
    except Exception as exc:  # noqa: BLE001
        print(f"[cloud_fetch] WARNING: could not fetch/parse fixtures ({exc}); keeping existing draw_dump.html", file=sys.stderr)
        rnd, fixtures = None, []
    if rnd and 6 <= len(fixtures) <= 9:   # a sane full round (8 games, ±byes)
        with open("draw_dump.html", "w", encoding="utf-8") as fh:
            fh.write(emit_draw(rnd, fixtures))
        print(f"[cloud_fetch] wrote draw_dump.html: Round {rnd}, {len(fixtures)} fixtures "
              f"({', '.join(h + 'v' + a for h, a in fixtures)})")
    else:
        print(f"[cloud_fetch] draw looked off (round={rnd}, {len(fixtures)} fixtures) — "
              f"keeping the committed draw_dump.html so nothing breaks.", file=sys.stderr)


if __name__ == "__main__":
    main()
