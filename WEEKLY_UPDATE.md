# Weekly Update Runbook

This is the exact, copy-pasteable procedure the scheduled weekly job (or a
human doing it manually) follows to refresh the NRL Tipping Guide. It must
be run from inside this project folder.

Goal each week: produce a fresh, validated `nrl_data.js` for the next
unplayed round, so `nrl-tipping-guide.html` auto-loads it with no other
action needed. Since schema v3, that includes best-effort per-game detail
(odds, injuries/team news, weather) alongside the core ladder + draw. Since
the learning loop (v4), it also means a freshly re-fitted and validated
`nrl_learned.js` — see step 4 below.

---

## 0. Prerequisites

- Python 3 available as `python3`.
- `parse_nrl.py` present in this folder (Dev A owns it — do not edit it here).
- `learn_model.py` present in this folder (regenerates `nrl_learned.js` —
  do not edit it here).
- `validate_data.py` and `validate_learned.py` present in this folder (this
  file's siblings — owned by Dev C).
- Network access to fetch the source pages below (the orchestrator /
  scheduler does the actual fetching — `parse_nrl.py` itself makes no
  network calls, per SPEC.md).

## 1. Fetch the raw source pages

**Required every week** (ladder + draw — fetch BOTH for resilience; if one
is down or has changed layout, the other can still produce a usable
update):

**Source A — Zero Tackle NRL ladder** (team stats / ladder, incl. Home/Away
split tables further down the same page)
```
URL: https://www.zerotackle.com/nrl/ladder/
Save raw output to: raw_ladder.html
```

**Source B — NRL.com draw** (next round's fixtures)
```
URL: https://www.nrl.com/draw/
Save raw output to: raw_draw.html
```

**Optional, best-effort** (fetch if available — the app degrades gracefully
if any/all of these are skipped, leaving the corresponding fields `null`):

**Source C — match odds** (bookmaker / odds-aggregator page)
```
e.g. https://www.sportsbet.com.au/betting/rugby-league/nrl
Reformat to "Team A v Team B: <odds A> / <odds B>" per line,
save to: raw_odds.txt
Publishes ~Tuesday for the upcoming round.
```

**Source D — injuries / team news** (NRL.com late mail / team lists)
```
e.g. https://www.nrl.com/news/  (search "team lists" / "late mail")
Reformat to "TeamName: short news text" per line,
save to: raw_injuries.txt
Official team lists from ~Tuesday; late mail trickles in until game day.
```

**Source E — weather** (any forecast source, keyed by host city + kickoff date)
```
e.g. https://www.bom.gov.au/  or an equivalent forecast site, looked up
per fixture's host city (see fixture.city in nrl_data.js).
Reformat to "City: short weather text" per line,
save to: raw_weather.txt
```

See `sources.md` (maintained by Dev A) for exact URL patterns, the precise
format expected in each dump, and fallback URLs if a site restructures.

Example using the web-fetch tool available to the orchestrator:
```
fetch("https://www.zerotackle.com/nrl/ladder/")  -> save as raw_ladder.html
fetch("https://www.nrl.com/draw/")                -> save as raw_draw.html
# optional, if fetched this week:
fetch(<odds source>)                              -> reformat, save as raw_odds.txt
fetch(<injuries source>)                          -> reformat, save as raw_injuries.txt
fetch(<weather source>)                           -> reformat, save as raw_weather.txt
```
All files should end up in this project folder, next to `parse_nrl.py`.

## 2. Run the parser

```bash
cd "/Users/joshrandall/Desktop/Footy tipping project"
python3 parse_nrl.py --ladder raw_ladder.html --draw raw_draw.html --out nrl_data.js \
  --odds raw_odds.txt --injuries raw_injuries.txt --weather raw_weather.txt
```

Drop any of `--odds` / `--injuries` / `--weather` that weren't fetched this
week — the parser still runs fine and just leaves those fields `null`.

(Exact flags may differ slightly if Dev A changes the CLI — check
`python3 parse_nrl.py --help` if this fails.)

This should overwrite `nrl_data.js` with:
- `updated` set to today's date,
- the full 17-team ladder, each team's colour and Home/Away split stats,
- `round` set to the next unplayed round,
- that round's `fixtures`, each with a host `city`,
- `byeTeams` for that round,
- `odds` / `weather` per fixture and `news` per team, where a dump was
  supplied and matched (otherwise `null`),
- `results[]` for the season so far, if the parser supports it.

`updated` is set automatically to the run date each time this step runs —
you don't need to touch it by hand. The front-end reads that date to power
its data-freshness warning (it flags the page if `updated` is roughly 8 or
more days old), so running this step on schedule keeps that warning quiet.

## 3. Validate before anything else touches the new file

```bash
python3 validate_data.py nrl_data.js
```

- If it prints **PASS** and exits `0` → continue to step 4.
- If it prints **FAIL** and exits non-zero → **STOP**. Do not let the app
  pick up this file. Options:
  - Re-run step 1/2 (source page may have been temporarily malformed).
  - Check whether one source failed and `parse_nrl.py` needs to fall back to
    the other source only.
  - If neither source is usable, leave the previous good `nrl_data.js` in
    place untouched — the app will keep using it (or its own embedded seed)
    and simply won't show this week's update yet. Never ship a file that
    fails validation.

Note: a missing/failed odds, injuries, or weather dump is **not** a
validation failure by itself — those are optional, best-effort fields
(`fixture.odds`, `team.news`, `fixture.weather`) that are allowed to be
`null`. Only the ladder + draw are required for a passing file. The rule
stays the same either way: don't ship on validate FAIL.

## 4. Run the learning loop (update the learned model)

Once `nrl_data.js` has validated, re-fit the learned model from the
season's match log now that this round's results have been parsed:

```bash
python3 learn_model.py --in nrl_data.js --out nrl_learned.js
```

(Exact flags may differ slightly if the pipeline owner changes the CLI —
check `python3 learn_model.py --help` if this fails.)

This reads `nrl_data.js`'s `results[]` match log, re-fits `homeAdv`,
`logisticScale`, and `oddsWeight`, replays the season's Elo ratings, and
backtests the result into a fresh `nrl_learned.js` (see SPEC.md's
"Learning loop (v4)" section and README.md's "How it learns").

Then validate it, the same way as `nrl_data.js`:

```bash
python3 validate_learned.py nrl_learned.js
```

- If it prints **PASS** and exits `0` → continue to step 5.
- If it prints **FAIL** and exits non-zero → **STOP**. Do not let the app
  pick up this file. Leave the previous good `nrl_learned.js` in place
  untouched (the app falls back to the hand-tuned formula and/or last-known
  learned state). **Never ship learned data that fails validation** — the
  same rule as `nrl_data.js` in step 3.

## 5. Confirm the app picks it up

No action needed — `nrl-tipping-guide.html` loads `nrl_data.js` automatically
as a sibling `<script src="nrl_data.js">` on every open. Optionally, sanity
check by opening the HTML file and confirming:
- the header's "updated" date matches today,
- the round number matches what you expect,
- the Roosters still show the locked pick badge in their game (or the bye
  banner if they have the bye).

## 6. (Optional but recommended) Run the smoke test

This doesn't test the new data directly, but confirms the tipping math
itself hasn't broken (useful after any code changes, and cheap to run every
week as a sanity check):

```bash
node smoke_test.mjs
```

Expect `PASS: N/N checks passed.` and exit code `0`.

## Daily reactive refresh

Between full weekly rebuilds, a lightweight DAILY job keeps the fast-moving
fields fresh — match odds, injury/team news, and weather — without touching
the ladder, home/away splits, round number, or fixtures list built by the
weekly job above. This is cheap enough to run every day (and worth running
more often on game days, when late mail and weather can change within
hours).

**1. Fetch whatever's available today** (any/all of these — see `sources.md`
for exact URLs and formats):
```
raw_odds.txt      — bookmaker odds for the upcoming round's games
raw_injuries.txt  — NRL.com late mail / team lists
raw_weather.txt   — forecast for each fixture's host city
```

**2. Run the parser in `--merge` mode** (note: no `--ladder`/`--draw` here —
merge mode does not rebuild the ladder or fixtures at all, it only loads the
existing `nrl_data.js` and patches reactive fields onto it):
```bash
cd "/Users/joshrandall/Desktop/Footy tipping project"
python3 parse_nrl.py --merge --in nrl_data.js \
  --injuries raw_injuries.txt --odds raw_odds.txt --weather raw_weather.txt
```
Drop any of `--injuries` / `--odds` / `--weather` that weren't fetched today
— the merge still runs and just leaves those fields as they were.

This updates `fixture.odds`, `team.news`, `fixture.weather`, and stamps the
top-level `newsUpdated` field with today's date. It does NOT change
`updated`, `round`, ladder numbers, home/away splits, or the fixtures list —
those stay exactly as the last weekly rebuild left them.

**Odds now record both an opening and a closing price** (for closing-line
value / CLV tracking): the FIRST time odds are seen for a fixture this
season, they're stamped as `odds.open` (never touched again after that);
every merge after that keeps advancing `odds.close` to the newest price.
No new flags or steps are needed — just keep running `--merge --odds
raw_odds.txt` as usual and both fields populate themselves automatically.

If the existing `nrl_data.js` can't be read or parsed, `--merge` exits
non-zero and writes nothing — it will never overwrite a good file with a
broken one.

After a successful merge, the script prints a one-line machine-readable
summary, e.g.:
```
MERGED: odds=6 injuries=9 weather=4 newsUpdated=2026-07-27
```
A scheduled daily job can parse this line to decide whether anything
actually changed today (worth alerting on) or nothing new came in.

**3. Run the learning loop again**, same as the weekly job (step 4 above) —
any newly-parsed results in `nrl_data.js`'s `results[]` since the last run
(e.g. gameday scores logged during the merge) should feed back into the
learned model too:
```bash
python3 learn_model.py --in nrl_data.js --out nrl_learned.js
python3 validate_learned.py nrl_learned.js
```
If `validate_learned.py` prints **FAIL**, do not let the app pick up this
file — leave the previous good `nrl_learned.js` in place untouched. Same
rule as always: **never ship learned data that fails validation.**

**4. Validate `nrl_data.js` before shipping — same rule as the weekly job:**
```bash
python3 validate_data.py nrl_data.js
```
If it prints **FAIL**, do not let the app pick up this file — leave the
previous good `nrl_data.js` in place untouched.

## Failure escalation

If validation keeps failing for more than one week in a row, that means one
or both source pages likely changed their HTML structure and `parse_nrl.py`
needs updating (Dev A) — flag it rather than repeatedly retrying.

## Quick reference (copy-paste block)

```bash
cd "/Users/joshrandall/Desktop/Footy tipping project"
# Required: raw_ladder.html and raw_draw.html fetched by orchestrator from:
#    https://www.zerotackle.com/nrl/ladder/
#    https://www.nrl.com/draw/
# Optional, best-effort (drop the flags below if not fetched this week):
#    raw_odds.txt      — bookmaker/odds-aggregator page, ~Tuesday
#    raw_injuries.txt  — NRL.com late mail / team lists, ~Tuesday onward
#    raw_weather.txt   — forecast source keyed by fixture city
python3 parse_nrl.py --ladder raw_ladder.html --draw raw_draw.html --out nrl_data.js \
  --odds raw_odds.txt --injuries raw_injuries.txt --weather raw_weather.txt
python3 validate_data.py nrl_data.js && echo "OK to ship" || echo "DO NOT SHIP — see errors above"
# Learning loop: re-fit params + Elo from the (now-updated) match log, then validate it too.
python3 learn_model.py --in nrl_data.js --out nrl_learned.js
python3 validate_learned.py nrl_learned.js && echo "OK to ship" || echo "DO NOT SHIP — see errors above"
node smoke_test.mjs
```
