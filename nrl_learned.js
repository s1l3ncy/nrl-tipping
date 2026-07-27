// Auto-generated / appended by parse_nrl.py + learn_model.py — DO NOT hand-edit
// (edits will be overwritten next run). This is the LEARNING LOOP's permanent
// memory: `results` is an append-only match log (never deleted, deduped on
// round+home+away) that parse_nrl.py appends newly-finished games to on every
// run; learn_model.py re-fits homeAdv/Elo/eloK/eloHGA/logisticScale/oddsWeight
// from it and rewrites this file, appending one {date,games,brier} history
// entry per run. See sources.md ('Learning loop') for details.
// lowConfidence: only 7 game(s) in memory (<30) — eloK/eloHGA/logisticScale held at conservative defaults, not grid-searched; front-end ignores these learned params entirely while lowConfidence=true. oddsWeight defaulted to 0.5 — no --odds-history supplied/matched, not yet learned.
window.NRL_LEARNED = {
  "updated": "2026-07-27",
  "gamesLearned": 7,
  "lowConfidence": true,
  "params": {
    "homeAdv": 5.86,
    "logisticScale": 7.0,
    "oddsWeight": 0.5,
    "eloK": 20,
    "eloHGA": 50
  },
  "elo": {
    "PEN": 1532.9,
    "SYD": 1518.9,
    "NZW": 1470.1,
    "CRO": 1500.0,
    "DOL": 1500.0,
    "SOU": 1517.6,
    "NEW": 1481.1,
    "NQL": 1526.8,
    "MAN": 1500.0,
    "CAN": 1529.9,
    "CBR": 1540.6,
    "MEL": 1482.4,
    "BRI": 1473.2,
    "PAR": 1467.1,
    "WST": 1459.4,
    "GLD": 1545.2,
    "STI": 1454.8
  },
  "backtest": {
    "games": 7,
    "brier": 0.2609,
    "logloss": 0.7185,
    "hit": 0.5714,
    "marketBrier": null
  },
  "history": [
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    }
  ],
  "results": [
    {
      "round": 21,
      "home": "PAR",
      "away": "PEN",
      "hs": 18,
      "as": 24
    },
    {
      "round": 21,
      "home": "NEW",
      "away": "SYD",
      "hs": 22,
      "as": 23
    },
    {
      "round": 21,
      "home": "SOU",
      "away": "MEL",
      "hs": 28,
      "as": 26
    },
    {
      "round": 21,
      "home": "CBR",
      "away": "WST",
      "hs": 56,
      "as": 10
    },
    {
      "round": 21,
      "home": "CAN",
      "away": "NZW",
      "hs": 18,
      "as": 6
    },
    {
      "round": 21,
      "home": "NQL",
      "away": "BRI",
      "hs": 18,
      "as": 10
    },
    {
      "round": 21,
      "home": "STI",
      "away": "GLD",
      "hs": 18,
      "as": 38
    }
  ]
};
