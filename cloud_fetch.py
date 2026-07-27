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
