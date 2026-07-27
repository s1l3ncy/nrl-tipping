#!/usr/bin/env python3
"""
cloud_fetch.py — runs on GitHub Actions (NOT on the Mac).

Fetches the LIVE Zero Tackle NRL ladder and rebuilds `ladder_dump.html` in the
exact clean <table><tr><td> format that parse_nrl.py expects (parse_nrl does its
own <td>->pipe conversion, so it needs real table tags, not flattened text —
that was the bug in the first version).

It deliberately does NOT touch draw_dump.html / injuries_dump.html: the season
draw is fixed and the committed draw_dump.html already holds the correct
upcoming-round fixtures (the NRL.com draw is JS-rendered and unfetchable with
plain requests anyway). So each run refreshes the ladder (standings, W/L,
points for/against) and everything downstream re-rates off that.

Network access is fine here because this runs on GitHub's servers.
Diagnostics are printed so a single run reveals the live table layout if the
heuristics ever need adjusting.
"""
import re
import sys

import requests
from bs4 import BeautifulSoup

# find_short + TEAMS come from the existing parser module (import is side-effect
# free thanks to its __main__ guard).
from parse_nrl import find_short, TEAMS

HEADERS = {"User-Agent": "footy-tipping-personal/1.0 (non-commercial; polite; low-frequency)"}
LADDER_URL = "https://www.zerotackle.com/nrl/nrl-ladder/"


def ints_in(cells):
    out = []
    for c in cells:
        for tok in re.findall(r"[+-]?\d+", c.replace(",", "")):
            out.append(int(tok))
    return out


def team_from_cells(cells):
    """First cell that resolves to a known team short (the name cell comes
    before any 'next opponent' logo cell, and logo cells carry no text)."""
    for c in cells:
        s = find_short(c)
        if s:
            return s
    return None


def extract_ladder(html):
    soup = BeautifulSoup(html, "html.parser")
    teams = {}
    debug = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not cells:
            continue
        short = team_from_cells(cells)
        if not short or short in teams:
            continue
        nums = ints_in(cells)
        big = [n for n in nums if n >= 100]        # PF, PA (points for/against)
        if len(big) < 2:
            continue                                # not the stats row (e.g. a form/preview row)
        pf, pa = big[0], big[1]
        smalls = [n for n in nums if 0 <= n < 100]  # rank, P, W, L, D, (B), PTS
        # Zero Tackle order after the rank cell is P, W, L, D. Try dropping the
        # leading rank first; fall back to no-rank if the sanity check fails.
        cand = []
        if len(smalls) >= 5:
            cand.append((smalls[1], smalls[2], smalls[3], smalls[4]))   # skip rank
        if len(smalls) >= 4:
            cand.append((smalls[0], smalls[1], smalls[2], smalls[3]))   # no rank
        pick = None
        for P, W, L, D in cand:
            if abs((W + L + D) - P) <= 2 and 5 <= P <= 40:
                pick = (P, W, L, D)
                break
        if pick is None:
            debug.append((short, "UNMAPPED", cells[:14]))
            continue
        P, W, L, D = pick
        teams[short] = {"name": TEAMS[short]["name"], "P": P, "W": W, "L": L, "D": D, "PF": pf, "PA": pa}
        debug.append((short, f"P{P} W{W} L{L} D{D} PF{pf} PA{pa}", cells[:14]))
    return teams, debug


def emit_ladder(teams):
    out = ['<!-- rebuilt by cloud_fetch.py from the live Zero Tackle ladder -->',
           '<table class="ladder">']
    for t in teams.values():
        diff = t["PF"] - t["PA"]
        out.append(
            f'<tr><td>{t["name"]}</td><td>{t["P"]}</td><td>{t["W"]}</td>'
            f'<td>{t["D"]}</td><td>{t["L"]}</td><td>{t["PF"]}</td><td>{t["PA"]}</td>'
            f'<td>{diff:+d}</td><td>0</td><td></td></tr>'
        )
    out.append("</table>")
    return "\n".join(out) + "\n"


def main():
    try:
        resp = requests.get(LADDER_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not fetch ladder: {exc}", file=sys.stderr)
        sys.exit(1)

    teams, debug = extract_ladder(resp.text)
    print(f"[cloud_fetch] extracted {len(teams)} teams from the live ladder")
    for short, summary, _cells in debug[:20]:
        print(f"    {short}: {summary}")

    if len(teams) < 17:
        # Not enough teams — print raw table structure so the layout can be fixed,
        # and DON'T overwrite the known-good committed ladder_dump.html.
        print("[cloud_fetch] WARNING: <17 teams parsed — leaving ladder_dump.html untouched.", file=sys.stderr)
        soup = BeautifulSoup(resp.text, "html.parser")
        for ti, tb in enumerate(soup.find_all("table")[:5]):
            rows = tb.find_all("tr")
            print(f"  --- table #{ti}: {len(rows)} rows ---", file=sys.stderr)
            for rr in rows[:3]:
                print("    ROW:", [c.get_text(" ", strip=True) for c in rr.find_all(["td", "th"])], file=sys.stderr)
        sys.exit(1)

    with open("ladder_dump.html", "w", encoding="utf-8") as fh:
        fh.write(emit_ladder(teams))
    print("[cloud_fetch] wrote ladder_dump.html (draw_dump.html left as-is)")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
cloud_fetch.py — runs on GitHub Actions (NOT on Josh's Mac).

Downloads the NRL source pages and saves them as the local *_dump.html files that
parse_nrl.py already knows how to read, so the rest of the pipeline is unchanged.
Uses only requests + BeautifulSoup. Network access is fine here because this runs
on GitHub's servers, not inside Claude.

If a source can't be fetched, it leaves the previous dump in place (never wipes
good data) and the pipeline degrades gracefully.
"""
import sys
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "footy-tipping-personal-project/1.0 (non-commercial; polite; low frequency)"
}

# out filename -> source URL
SOURCES = {
    "ladder_dump.html": "https://www.zerotackle.com/nrl/nrl-ladder/",
    "draw_dump.html": "https://www.zerotackle.com/nrl/fixtures-results/",
    # Best-effort extras (parser treats them as optional):
    "injuries_dump.html": "https://www.zerotackle.com/nrl/injuries-suspensions/",
}


def to_text(html):
    """Flatten HTML to newline-separated visible text — roughly the shape
    parse_nrl.py's regexes expect. Kept simple on purpose."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def main():
    ok = 0
    for out, url in SOURCES.items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            text = to_text(resp.text)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"fetched {url} -> {out} ({len(text)} chars)")
            ok += 1
            time.sleep(2)  # be polite between requests
        except Exception as exc:  # noqa: BLE001 - log and continue, keep old dump
            print(f"WARN: could not fetch {url}: {exc}", file=sys.stderr)
    if ok == 0:
        print("ERROR: fetched nothing — leaving existing data untouched", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
