# Data sources — NRL Tipping App

Dev A's weekly job needs raw page dumps, saved to disk by the orchestrator
(the web-fetch tools), which `parse_nrl.py` then parses offline. It makes no
network calls itself. Two sources (ladder + draw) are REQUIRED every week;
three more (odds, injuries, weather) are OPTIONAL — the schema-v3 fields
they feed (`fixture.odds`, `team.news`, `fixture.weather`) simply stay
`null` if a dump isn't provided or can't be parsed that week.

**Timing note:** odds and team-lists/injury news for the upcoming round
typically aren't published until around **Tuesday** each week (bookmakers
release match odds early in the week; NRL clubs release official team
lists / "late mail" progressively from Tuesday through to game day). The
ladder and draw can be fetched any day; if you're doing the full refresh
earlier in the week, expect `--odds`/`--injuries` to have thinner coverage
and re-run later in the week to backfill them.

## 1. Ladder (+ Home/Away splits) — Zero Tackle

- URL: `https://www.zerotackle.com/nrl/ladder/`
  (alt: `https://www.zerotackle.com/nrl/nrl-ladder/` if the site restructures —
  search "zero tackle nrl ladder" if the URL 404s)
- Save the fetched page text/HTML to: `ladder_dump.html` (default expected by
  `parse_nrl.py --ladder`)
- What we need from it: one row per team with, in order, Played / Wins /
  Draws / Losses / Points For / Points Against, plus (ideally) a trailing
  "form" string of W/L letters for the last 5 games (e.g. `W L W W L`).
- The SAME page also carries separate **"Home"** and **"Away"** ladder
  tables further down (each team's split P/W/L/PF/PA for games played at
  home vs away) — fetch/save the full page so both split tables are
  included in the dump, not just the combined ladder at the top.
- Parsing approach (`parse_ladder()` / `parse_home_away_splits()` in
  `parse_nrl.py`):
  1. Strip HTML tags, turning `<tr>`/`<td>`/`<br>` boundaries into
     newline/pipe separators so each team ends up on roughly one line.
  2. Regex-match each line against a P/W/D/L/PF/PA/Diff/Pts pattern
     (`LADDER_ROW_RE`), tolerant of extra `|` separators from stripped `<td>`
     cells.
  3. Resolve the team name against `TEAMS` aliases (full name, city name,
     nickname — see the `TEAMS` dict at the top of the script) to get the
     3-letter short code used throughout `nrl_data.js`.
  4. Count `W` occurrences in the trailing form letters for `last5`
     (0 if no form string is present — degrades gracefully, just less
     accurate).
  5. Sanity check: `W + D + L` must be within 2 of `P` or the row is
     discarded (guards against parsing a non-ladder row).
  6. Separately, locate the `<h2>Home</h2>` / `<h2>Away</h2>` (or similar)
     headings and parse the lighter-weight P/W/L/PF/PA rows beneath each
     into `team.home` / `team.away`. If a heading/table can't be found,
     that team's split is emitted as `null` rather than guessed.
- Club colours (`team.colour`) and each fixture's host city fallback are
  NOT scraped — they're a small static lookup (`CLUB_COLOUR` /
  `TEAM_HOME_CITY` / `VENUE_CITY`) baked into `parse_nrl.py`, copied from
  the values already shipped in `nrl_data.js`. Only update these dicts if a
  club rebrands or a new venue needs mapping.

## 2. Draw / fixtures — NRL.com

- URL: `https://www.nrl.com/draw/` (the site auto-shows the current/next
  round; if it doesn't, append `?competition=111&round=<N>&season=<YYYY>`
  with the next round number)
- Save the fetched page text/HTML to: `draw_dump.html` (default expected by
  `parse_nrl.py --draw`)
- What we need from it: the round heading (`Round 22`), then for each game
  the two team names, and ideally the venue and kickoff time/date printed
  near the matchup.
- Parsing approach (`parse_draw()` in `parse_nrl.py`):
  1. Strip HTML the same way as the ladder.
  2. Find the round number via `Round (\d+)` regex anywhere on the page.
  3. Scan lines for a `Team A v Team B` / `Team A vs Team B` pattern
     (`MATCHUP_RE`), resolve both sides to short codes via the same
     `TEAMS` alias table.
  4. Look at the next 1-3 lines after each matchup for a venue (matched via
     stadium/park/oval/arena keywords) and a kickoff date/time (matched via
     an ISO datetime pattern first, else a "Day D Month, HH:MMam/pm" style
     pattern). Both are optional — if not found they're emitted as `""`.
  5. Stop counting a team once it has appeared in a matchup this round, so
     a stray repeated mention (e.g. in a promo blurb) doesn't create a
     duplicate fixture.
- Bye team = whichever of the 17 short codes from the ladder does not
  appear in any parsed fixture for the round.
- Each fixture's `city` is derived automatically from its venue name (a
  built-in `VENUE_CITY` table in `parse_nrl.py`), falling back to the home
  team's usual city if the venue isn't one we've mapped yet — no separate
  source needed for this field.

## 3. Match odds — a bookmaker / odds-aggregator page

- Any odds-aggregator page works, e.g. `https://www.oddschecker.com/au/rugby-league/nrl`
  or a single bookmaker's NRL page (e.g. `https://www.sportsbet.com.au/betting/rugby-league/nrl`).
  Pick whichever is reachable that week; the exact source isn't tracked in
  `nrl_data.js`, only the odds numbers themselves.
- Save the fetched page as plain text to a local file, e.g. `odds_dump.txt`,
  reformatted (by hand or by a small pre-pass) into one line per match:
  ```
  Cowboys v Roosters: 1.85 / 1.95
  Panthers v Raiders: 1.20 / 4.50
  ```
  (decimal odds, first-named team's price first — order doesn't need to
  match home/away, `parse_nrl.py` matches by team not by position).
- Pass it to the parser with `--odds odds_dump.txt`. On a full rebuild this
  populates `fixture.odds = {open:{home,away}, close:{home,away}}`, both set
  to the same freshly-parsed price (it's the only sighting so far). Omit the
  flag (or leave the file absent) and `odds` stays `null` for every fixture
  — the app handles that.
- **In daily/gameday `--merge` runs** (see "Polling cadence" below and
  `WEEKLY_UPDATE.md`), the SAME `--odds` flag now records opening AND
  closing prices for closing-line-value (CLV) tracking: `open` is set only
  the first time odds are seen for a fixture and is never overwritten again;
  `close` is updated to the newest parsed price on every merge. No new flags
  are needed — just keep passing `--odds` to the merge as before.
- **Publishes ~Tuesday** each week for the upcoming round; earlier in the
  week odds may not be posted yet.

## 4. Injuries / team news — NRL.com late mail & team lists

- URL: `https://www.nrl.com/news/` (search/filter for "team lists" or
  "late mail") or a specific club's team-list page, e.g.
  `https://www.nrl.com/teams/<club>/team-list/`.
- Save a short plain-text summary per team to a local file, e.g.
  `injuries_dump.txt`, one team per line:
  ```
  Panthers: Nathan Cleary (calf) - test, expected to play.
  Cowboys: Valentine Holmes OUT (hamstring).
  ```
- Pass it to the parser with `--injuries injuries_dump.txt`. Populates
  `team.news` (a short string) for any team with a matching line; teams
  without a line keep `news: null`.
- **Publishes progressively from ~Tuesday** (official team lists) through
  to game day (late mail / omissions) — a Tuesday fetch will have official
  lists but may miss late withdrawals; re-fetch closer to kickoff for the
  freshest picture if needed.

## 5. Weather — any venue-keyed weather source

- Any forecast source keyed by city + date works, e.g.
  `https://www.bom.gov.au/nsw/forecasts/` (Bureau of Meteorology, per state)
  or `https://www.accuweather.com/` search for the host city. Look up each
  fixture's host city (`fixture.city`, e.g. "Townsville", "Sydney") for the
  fixture's kickoff date.
- Save a short plain-text summary to a local file, e.g. `weather_dump.txt`,
  one city per line:
  ```
  Townsville: Fine, 26C, light breeze.
  Mudgee: Cool evening, 12C, clear skies.
  ```
- Pass it to the parser with `--weather weather_dump.txt`. Populates
  `fixture.weather` (a short string) for any fixture whose `city` matches a
  line; unmatched fixtures keep `weather: null`.
- Best fetched close to the round (a few days out) since forecasts that far
  ahead are the most reliable; re-fetch closer to kickoff if precision
  matters.

## Cross-checking / degradation

- `parse_nrl.py` requires the ladder to produce all 17 teams; if it can't,
  it aborts (non-zero exit, existing `nrl_data.js` left untouched) rather
  than emit a broken data file.
- If the draw dump is missing or unparsable, the script falls back to
  reusing whatever `fixtures`/`round`/`byeTeams` are already in the
  existing `nrl_data.js` on disk, so the site still has *something*
  sensible rather than an empty round. A warning is printed either way.
- Before writing, `validate()` re-checks: exactly 17 teams, no duplicate
  short codes, plausible P/PF/PA/last5 ranges, every fixture references a
  known short code, and no team appears twice in the round's fixture list.

## Weekly refresh command

```
python3 parse_nrl.py \
  --ladder ladder_dump.html \
  --draw draw_dump.html \
  --out nrl_data.js \
  --season 2026 \
  --source zerotackle.com \
  --odds odds_dump.txt \
  --injuries injuries_dump.txt \
  --weather weather_dump.txt
```

`--odds`, `--injuries` and `--weather` are optional — drop any (or all) of
them if that dump wasn't fetched this week; the script still produces a
valid, passing `nrl_data.js` with those fields left `null`.

(`--updated` can override the ISO date if not running same-day as the fetch.)

Note: `updated` is stamped with the real run date (`datetime.date.today()`)
by default, not a hardcoded string — the front-end uses `NRL_DATA.updated`
for its freshness check and to key its local-storage cache, so this must
track the actual day the data was generated.

## Polling cadence: daily vs weekly

- **Weekly** (full rebuild, `parse_nrl.py --ladder ... --draw ...`): Source 1
  (ladder + home/away splits) and Source 2 (draw/fixtures) — these define
  the round, the fixture list, and the ladder numbers, so they only need
  refreshing once a week.
- **Daily** (light refresh, `parse_nrl.py --merge`): Source 3 (odds), Source
  4 (injuries/late mail), and Source 5 (weather) — these change fast enough
  (odds move, late mail trickles in, forecasts update) that they're worth
  polling every day, and more often still on game days, without re-running
  the ladder/draw rebuild. See `WEEKLY_UPDATE.md`'s "Daily reactive
  refresh" section for the exact `--merge` invocation.

## Sample/test fixtures committed in this repo

`ladder_dump.html` and `draw_dump.html` in this folder are a small hand-built
sample (matching the real end-of-Round-21 2026 numbers) used to exercise
`parse_nrl.py` — run the command above against them to confirm the parser
still emits valid output after any changes.
