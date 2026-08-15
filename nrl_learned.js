// Auto-generated / appended by parse_nrl.py + learn_model.py — DO NOT hand-edit
// (edits will be overwritten next run). This is the LEARNING LOOP's permanent
// memory: `results` is an append-only match log (never deleted, deduped on
// round+home+away) that parse_nrl.py appends newly-finished games to on every
// run; learn_model.py re-fits homeAdv/Elo/eloK/eloHGA/logisticScale/oddsWeight
// from it and rewrites this file, appending one {date,games,brier} history
// entry per run. See sources.md ('Learning loop') for details.
// fitted via grid search: walk-forward logloss=0.6659 over eloK[10, 16, 24, 32, 40] x eloHGA[0, 20, 40, 60, 80, 100]; logisticScale pinned at 7 (unidentifiable from win/loss outcomes — audit A2, 2026-08-04). oddsWeight defaulted to 0.75 (market-heavy prior per the 2026-08-10 audit) — no --odds-history supplied/matched, not yet learned. freeze_tips now logs per-tip market probs (tiplog .mkt) as the future fitting corpus.
window.NRL_LEARNED = {
  "updated": "2026-08-16",
  "gamesLearned": 178,
  "lowConfidence": false,
  "params": {
    "homeAdv": 0.11,
    "logisticScale": 7.0,
    "oddsWeight": 0.75,
    "oddsWeightLearned": false,
    "eloK": 10,
    "eloHGA": 20
  },
  "elo": {
    "PEN": 1589.1,
    "SYD": 1635.2,
    "NZW": 1619.2,
    "CRO": 1566.4,
    "DOL": 1605.2,
    "SOU": 1531.7,
    "NEW": 1557.6,
    "NQL": 1505.1,
    "MAN": 1463.4,
    "CAN": 1482.2,
    "CBR": 1493.0,
    "MEL": 1482.9,
    "BRI": 1378.3,
    "PAR": 1436.2,
    "WST": 1379.5,
    "GLD": 1407.0,
    "STI": 1367.8
  },
  "backtest": {
    "games": 178,
    "brier": 0.2361,
    "logloss": 0.6659,
    "hit": 0.6461,
    "marketBrier": null,
    "lockTax": {
      "games": 21,
      "modelRight": 15,
      "rkWins": 16
    }
  },
  "history": [
    {
      "date": "2026-07-27",
      "games": 7,
      "brier": 0.2609
    },
    {
      "date": "2026-07-28",
      "games": 156,
      "brier": 0.2337
    },
    {
      "date": "2026-07-31",
      "games": 157,
      "brier": 0.2353
    },
    {
      "date": "2026-08-01",
      "games": 159,
      "brier": 0.2351
    },
    {
      "date": "2026-08-01",
      "games": 160,
      "brier": 0.2355
    },
    {
      "date": "2026-08-02",
      "games": 162,
      "brier": 0.2339
    },
    {
      "date": "2026-08-02",
      "games": 164,
      "brier": 0.233
    },
    {
      "date": "2026-08-05",
      "games": 164,
      "brier": 0.2338
    },
    {
      "date": "2026-08-07",
      "games": 165,
      "brier": 0.234
    },
    {
      "date": "2026-08-07",
      "games": 166,
      "brier": 0.2339
    },
    {
      "date": "2026-08-08",
      "games": 167,
      "brier": 0.2331
    },
    {
      "date": "2026-08-08",
      "games": 169,
      "brier": 0.2317
    },
    {
      "date": "2026-08-08",
      "games": 170,
      "brier": 0.231
    },
    {
      "date": "2026-08-09",
      "games": 172,
      "brier": 0.2334
    },
    {
      "date": "2026-08-14",
      "games": 173,
      "brier": 0.2337
    },
    {
      "date": "2026-08-14",
      "games": 174,
      "brier": 0.2336
    },
    {
      "date": "2026-08-15",
      "games": 175,
      "brier": 0.2341
    },
    {
      "date": "2026-08-15",
      "games": 176,
      "brier": 0.2354
    },
    {
      "date": "2026-08-15",
      "games": 178,
      "brier": 0.2361
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
    },
    {
      "round": 1,
      "home": "NEW",
      "away": "NQL",
      "hs": 28,
      "as": 18
    },
    {
      "round": 1,
      "home": "CAN",
      "away": "STI",
      "hs": 15,
      "as": 14
    },
    {
      "round": 1,
      "home": "MEL",
      "away": "PAR",
      "hs": 52,
      "as": 4
    },
    {
      "round": 1,
      "home": "NZW",
      "away": "SYD",
      "hs": 42,
      "as": 18
    },
    {
      "round": 1,
      "home": "BRI",
      "away": "PEN",
      "hs": 0,
      "as": 26
    },
    {
      "round": 1,
      "home": "CRO",
      "away": "GLD",
      "hs": 50,
      "as": 10
    },
    {
      "round": 1,
      "home": "MAN",
      "away": "CBR",
      "hs": 28,
      "as": 29
    },
    {
      "round": 1,
      "home": "DOL",
      "away": "SOU",
      "hs": 30,
      "as": 40
    },
    {
      "round": 2,
      "home": "BRI",
      "away": "PAR",
      "hs": 32,
      "as": 40
    },
    {
      "round": 2,
      "home": "NZW",
      "away": "CBR",
      "hs": 40,
      "as": 6
    },
    {
      "round": 2,
      "home": "SYD",
      "away": "SOU",
      "hs": 26,
      "as": 18
    },
    {
      "round": 2,
      "home": "WST",
      "away": "NQL",
      "hs": 44,
      "as": 16
    },
    {
      "round": 2,
      "home": "STI",
      "away": "MEL",
      "hs": 20,
      "as": 46
    },
    {
      "round": 2,
      "home": "PEN",
      "away": "CRO",
      "hs": 26,
      "as": 6
    },
    {
      "round": 2,
      "home": "MAN",
      "away": "NEW",
      "hs": 16,
      "as": 36
    },
    {
      "round": 2,
      "home": "DOL",
      "away": "GLD",
      "hs": 18,
      "as": 14
    },
    {
      "round": 3,
      "home": "CBR",
      "away": "CAN",
      "hs": 10,
      "as": 14
    },
    {
      "round": 3,
      "home": "SYD",
      "away": "PEN",
      "hs": 4,
      "as": 40
    },
    {
      "round": 3,
      "home": "MEL",
      "away": "BRI",
      "hs": 14,
      "as": 18
    },
    {
      "round": 3,
      "home": "NEW",
      "away": "NZW",
      "hs": 12,
      "as": 38
    },
    {
      "round": 3,
      "home": "CRO",
      "away": "DOL",
      "hs": 10,
      "as": 38
    },
    {
      "round": 3,
      "home": "SOU",
      "away": "WST",
      "hs": 20,
      "as": 16
    },
    {
      "round": 3,
      "home": "PAR",
      "away": "STI",
      "hs": 30,
      "as": 20
    },
    {
      "round": 3,
      "home": "NQL",
      "away": "GLD",
      "hs": 30,
      "as": 16
    },
    {
      "round": 4,
      "home": "MAN",
      "away": "SYD",
      "hs": 16,
      "as": 33
    },
    {
      "round": 4,
      "home": "NZW",
      "away": "WST",
      "hs": 14,
      "as": 32
    },
    {
      "round": 4,
      "home": "BRI",
      "away": "DOL",
      "hs": 26,
      "as": 12
    },
    {
      "round": 4,
      "home": "CAN",
      "away": "NEW",
      "hs": 16,
      "as": 24
    },
    {
      "round": 4,
      "home": "PEN",
      "away": "PAR",
      "hs": 48,
      "as": 20
    },
    {
      "round": 4,
      "home": "NQL",
      "away": "MEL",
      "hs": 28,
      "as": 24
    },
    {
      "round": 4,
      "home": "CBR",
      "away": "CRO",
      "hs": 22,
      "as": 34
    },
    {
      "round": 4,
      "home": "GLD",
      "away": "STI",
      "hs": 22,
      "as": 14
    },
    {
      "round": 5,
      "home": "DOL",
      "away": "MAN",
      "hs": 18,
      "as": 52
    },
    {
      "round": 5,
      "home": "SOU",
      "away": "CAN",
      "hs": 32,
      "as": 24
    },
    {
      "round": 5,
      "home": "PEN",
      "away": "MEL",
      "hs": 50,
      "as": 10
    },
    {
      "round": 5,
      "home": "STI",
      "away": "NQL",
      "hs": 0,
      "as": 32
    },
    {
      "round": 5,
      "home": "GLD",
      "away": "BRI",
      "hs": 12,
      "as": 26
    },
    {
      "round": 5,
      "home": "CRO",
      "away": "NZW",
      "hs": 36,
      "as": 22
    },
    {
      "round": 5,
      "home": "NEW",
      "away": "CBR",
      "hs": 32,
      "as": 12
    },
    {
      "round": 5,
      "home": "PAR",
      "away": "WST",
      "hs": 20,
      "as": 22
    },
    {
      "round": 6,
      "home": "CAN",
      "away": "PEN",
      "hs": 32,
      "as": 16
    },
    {
      "round": 6,
      "home": "STI",
      "away": "MAN",
      "hs": 18,
      "as": 28
    },
    {
      "round": 6,
      "home": "BRI",
      "away": "NQL",
      "hs": 31,
      "as": 35
    },
    {
      "round": 6,
      "home": "SOU",
      "away": "CBR",
      "hs": 34,
      "as": 36
    },
    {
      "round": 6,
      "home": "CRO",
      "away": "SYD",
      "hs": 22,
      "as": 34
    },
    {
      "round": 6,
      "home": "MEL",
      "away": "NZW",
      "hs": 14,
      "as": 38
    },
    {
      "round": 6,
      "home": "PAR",
      "away": "GLD",
      "hs": 10,
      "as": 52
    },
    {
      "round": 6,
      "home": "WST",
      "away": "NEW",
      "hs": 42,
      "as": 22
    },
    {
      "round": 7,
      "home": "NQL",
      "away": "MAN",
      "hs": 6,
      "as": 38
    },
    {
      "round": 7,
      "home": "CBR",
      "away": "MEL",
      "hs": 26,
      "as": 22
    },
    {
      "round": 7,
      "home": "DOL",
      "away": "PEN",
      "hs": 22,
      "as": 23
    },
    {
      "round": 7,
      "home": "NZW",
      "away": "GLD",
      "hs": 28,
      "as": 20
    },
    {
      "round": 7,
      "home": "SOU",
      "away": "STI",
      "hs": 30,
      "as": 12
    },
    {
      "round": 7,
      "home": "WST",
      "away": "BRI",
      "hs": 20,
      "as": 21
    },
    {
      "round": 7,
      "home": "SYD",
      "away": "NEW",
      "hs": 38,
      "as": 24
    },
    {
      "round": 7,
      "home": "PAR",
      "away": "CAN",
      "hs": 38,
      "as": 20
    },
    {
      "round": 8,
      "home": "WST",
      "away": "CBR",
      "hs": 33,
      "as": 14
    },
    {
      "round": 8,
      "home": "NQL",
      "away": "CRO",
      "hs": 46,
      "as": 34
    },
    {
      "round": 8,
      "home": "BRI",
      "away": "CAN",
      "hs": 32,
      "as": 12
    },
    {
      "round": 8,
      "home": "STI",
      "away": "SYD",
      "hs": 16,
      "as": 62
    },
    {
      "round": 8,
      "home": "NZW",
      "away": "DOL",
      "hs": 20,
      "as": 18
    },
    {
      "round": 8,
      "home": "MEL",
      "away": "SOU",
      "hs": 6,
      "as": 48
    },
    {
      "round": 8,
      "home": "NEW",
      "away": "PEN",
      "hs": 12,
      "as": 44
    },
    {
      "round": 8,
      "home": "MAN",
      "away": "PAR",
      "hs": 33,
      "as": 18
    },
    {
      "round": 9,
      "home": "CAN",
      "away": "NQL",
      "hs": 12,
      "as": 28
    },
    {
      "round": 9,
      "home": "DOL",
      "away": "MEL",
      "hs": 28,
      "as": 10
    },
    {
      "round": 9,
      "home": "GLD",
      "away": "CBR",
      "hs": 12,
      "as": 28
    },
    {
      "round": 9,
      "home": "PAR",
      "away": "NZW",
      "hs": 14,
      "as": 36
    },
    {
      "round": 9,
      "home": "SYD",
      "away": "BRI",
      "hs": 38,
      "as": 24
    },
    {
      "round": 9,
      "home": "NEW",
      "away": "SOU",
      "hs": 42,
      "as": 38
    },
    {
      "round": 9,
      "home": "CRO",
      "away": "WST",
      "hs": 52,
      "as": 10
    },
    {
      "round": 9,
      "home": "PEN",
      "away": "MAN",
      "hs": 18,
      "as": 16
    },
    {
      "round": 10,
      "home": "DOL",
      "away": "CAN",
      "hs": 44,
      "as": 12
    },
    {
      "round": 10,
      "home": "SYD",
      "away": "GLD",
      "hs": 28,
      "as": 12
    },
    {
      "round": 10,
      "home": "NQL",
      "away": "PAR",
      "hs": 30,
      "as": 33
    },
    {
      "round": 10,
      "home": "STI",
      "away": "NEW",
      "hs": 10,
      "as": 44
    },
    {
      "round": 10,
      "home": "SOU",
      "away": "CRO",
      "hs": 36,
      "as": 12
    },
    {
      "round": 10,
      "home": "MAN",
      "away": "BRI",
      "hs": 32,
      "as": 4
    },
    {
      "round": 10,
      "home": "MEL",
      "away": "WST",
      "hs": 44,
      "as": 16
    },
    {
      "round": 10,
      "home": "CBR",
      "away": "PEN",
      "hs": 18,
      "as": 30
    },
    {
      "round": 11,
      "home": "CRO",
      "away": "CAN",
      "hs": 38,
      "as": 16
    },
    {
      "round": 11,
      "home": "SOU",
      "away": "DOL",
      "hs": 10,
      "as": 32
    },
    {
      "round": 11,
      "home": "WST",
      "away": "MAN",
      "hs": 18,
      "as": 46
    },
    {
      "round": 11,
      "home": "SYD",
      "away": "NQL",
      "hs": 12,
      "as": 18
    },
    {
      "round": 11,
      "home": "PAR",
      "away": "MEL",
      "hs": 8,
      "as": 34
    },
    {
      "round": 11,
      "home": "GLD",
      "away": "NEW",
      "hs": 12,
      "as": 36
    },
    {
      "round": 11,
      "home": "NZW",
      "away": "BRI",
      "hs": 42,
      "as": 12
    },
    {
      "round": 11,
      "home": "PEN",
      "away": "STI",
      "hs": 28,
      "as": 6
    },
    {
      "round": 12,
      "home": "CBR",
      "away": "DOL",
      "hs": 22,
      "as": 30
    },
    {
      "round": 12,
      "home": "CAN",
      "away": "MEL",
      "hs": 30,
      "as": 20
    },
    {
      "round": 12,
      "home": "STI",
      "away": "NZW",
      "hs": 12,
      "as": 30
    },
    {
      "round": 12,
      "home": "MAN",
      "away": "GLD",
      "hs": 12,
      "as": 10
    },
    {
      "round": 12,
      "home": "NQL",
      "away": "SOU",
      "hs": 30,
      "as": 18
    },
    {
      "round": 13,
      "home": "CRO",
      "away": "MAN",
      "hs": 28,
      "as": 22
    },
    {
      "round": 13,
      "home": "NEW",
      "away": "PAR",
      "hs": 28,
      "as": 22
    },
    {
      "round": 13,
      "home": "WST",
      "away": "CAN",
      "hs": 22,
      "as": 16
    },
    {
      "round": 13,
      "home": "MEL",
      "away": "SYD",
      "hs": 18,
      "as": 4
    },
    {
      "round": 13,
      "home": "BRI",
      "away": "STI",
      "hs": 26,
      "as": 30
    },
    {
      "round": 13,
      "home": "CBR",
      "away": "NQL",
      "hs": 26,
      "as": 12
    },
    {
      "round": 13,
      "home": "PEN",
      "away": "NZW",
      "hs": 20,
      "as": 18
    },
    {
      "round": 14,
      "home": "MAN",
      "away": "SOU",
      "hs": 28,
      "as": 14
    },
    {
      "round": 14,
      "home": "MEL",
      "away": "NEW",
      "hs": 32,
      "as": 30
    },
    {
      "round": 14,
      "home": "CBR",
      "away": "SYD",
      "hs": 0,
      "as": 26
    },
    {
      "round": 14,
      "home": "NQL",
      "away": "DOL",
      "hs": 14,
      "as": 40
    },
    {
      "round": 14,
      "home": "BRI",
      "away": "GLD",
      "hs": 23,
      "as": 28
    },
    {
      "round": 14,
      "home": "WST",
      "away": "PEN",
      "hs": 0,
      "as": 68
    },
    {
      "round": 14,
      "home": "CRO",
      "away": "STI",
      "hs": 34,
      "as": 12
    },
    {
      "round": 14,
      "home": "CAN",
      "away": "PAR",
      "hs": 14,
      "as": 12
    },
    {
      "round": 15,
      "home": "SOU",
      "away": "BRI",
      "hs": 48,
      "as": 6
    },
    {
      "round": 15,
      "home": "DOL",
      "away": "SYD",
      "hs": 48,
      "as": 10
    },
    {
      "round": 15,
      "home": "NZW",
      "away": "CRO",
      "hs": 8,
      "as": 10
    },
    {
      "round": 15,
      "home": "PAR",
      "away": "CBR",
      "hs": 15,
      "as": 12
    },
    {
      "round": 15,
      "home": "WST",
      "away": "GLD",
      "hs": 36,
      "as": 28
    },
    {
      "round": 16,
      "home": "NEW",
      "away": "STI",
      "hs": 22,
      "as": 20
    },
    {
      "round": 16,
      "home": "WST",
      "away": "DOL",
      "hs": 22,
      "as": 36
    },
    {
      "round": 16,
      "home": "GLD",
      "away": "PEN",
      "hs": 19,
      "as": 18
    },
    {
      "round": 16,
      "home": "CAN",
      "away": "MAN",
      "hs": 13,
      "as": 12
    },
    {
      "round": 16,
      "home": "NZW",
      "away": "NQL",
      "hs": 38,
      "as": 20
    },
    {
      "round": 16,
      "home": "MEL",
      "away": "CBR",
      "hs": 42,
      "as": 20
    },
    {
      "round": 16,
      "home": "SYD",
      "away": "CRO",
      "hs": 27,
      "as": 8
    },
    {
      "round": 17,
      "home": "PAR",
      "away": "SOU",
      "hs": 12,
      "as": 32
    },
    {
      "round": 17,
      "home": "GLD",
      "away": "CAN",
      "hs": 12,
      "as": 30
    },
    {
      "round": 17,
      "home": "BRI",
      "away": "SYD",
      "hs": 18,
      "as": 24
    },
    {
      "round": 17,
      "home": "DOL",
      "away": "NZW",
      "hs": 26,
      "as": 24
    },
    {
      "round": 17,
      "home": "NQL",
      "away": "PEN",
      "hs": 26,
      "as": 12
    },
    {
      "round": 17,
      "home": "MAN",
      "away": "MEL",
      "hs": 30,
      "as": 4
    },
    {
      "round": 17,
      "home": "CBR",
      "away": "STI",
      "hs": 24,
      "as": 16
    },
    {
      "round": 17,
      "home": "NEW",
      "away": "WST",
      "hs": 12,
      "as": 6
    },
    {
      "round": 18,
      "home": "PEN",
      "away": "SOU",
      "hs": 36,
      "as": 14
    },
    {
      "round": 18,
      "home": "STI",
      "away": "WST",
      "hs": 24,
      "as": 10
    },
    {
      "round": 18,
      "home": "BRI",
      "away": "CRO",
      "hs": 16,
      "as": 28
    },
    {
      "round": 18,
      "home": "PAR",
      "away": "MAN",
      "hs": 23,
      "as": 14
    },
    {
      "round": 18,
      "home": "NEW",
      "away": "DOL",
      "hs": 13,
      "as": 12
    },
    {
      "round": 19,
      "home": "WST",
      "away": "NZW",
      "hs": 6,
      "as": 32
    },
    {
      "round": 19,
      "home": "DOL",
      "away": "CRO",
      "hs": 0,
      "as": 66
    },
    {
      "round": 19,
      "home": "CAN",
      "away": "CBR",
      "hs": 16,
      "as": 40
    },
    {
      "round": 19,
      "home": "SYD",
      "away": "PAR",
      "hs": 28,
      "as": 12
    },
    {
      "round": 19,
      "home": "SOU",
      "away": "NEW",
      "hs": 26,
      "as": 24
    },
    {
      "round": 19,
      "home": "MAN",
      "away": "NQL",
      "hs": 18,
      "as": 19
    },
    {
      "round": 19,
      "home": "MEL",
      "away": "GLD",
      "hs": 22,
      "as": 18
    },
    {
      "round": 20,
      "home": "PEN",
      "away": "BRI",
      "hs": 12,
      "as": 14
    },
    {
      "round": 20,
      "home": "CRO",
      "away": "NEW",
      "hs": 20,
      "as": 18
    },
    {
      "round": 20,
      "home": "SYD",
      "away": "MEL",
      "hs": 14,
      "as": 6
    },
    {
      "round": 20,
      "home": "CBR",
      "away": "SOU",
      "hs": 34,
      "as": 24
    },
    {
      "round": 20,
      "home": "NZW",
      "away": "STI",
      "hs": 20,
      "as": 12
    },
    {
      "round": 20,
      "home": "CAN",
      "away": "WST",
      "hs": 32,
      "as": 0
    },
    {
      "round": 20,
      "home": "GLD",
      "away": "MAN",
      "hs": 38,
      "as": 32
    },
    {
      "round": 20,
      "home": "DOL",
      "away": "NQL",
      "hs": 36,
      "as": 16
    },
    {
      "round": 21,
      "home": "MAN",
      "away": "CRO",
      "hs": 12,
      "as": 48
    },
    {
      "round": 22,
      "home": "NQL",
      "away": "SYD",
      "hs": 12,
      "as": 82
    },
    {
      "round": 22,
      "home": "STI",
      "away": "DOL",
      "hs": 22,
      "as": 28
    },
    {
      "round": 22,
      "home": "MEL",
      "away": "CAN",
      "hs": 22,
      "as": 36
    },
    {
      "round": 22,
      "home": "GLD",
      "away": "NZW",
      "hs": 6,
      "as": 42
    },
    {
      "round": 22,
      "home": "PEN",
      "away": "CBR",
      "hs": 42,
      "as": 18
    },
    {
      "round": 22,
      "home": "BRI",
      "away": "NEW",
      "hs": 6,
      "as": 30
    },
    {
      "round": 22,
      "home": "CRO",
      "away": "SOU",
      "hs": 32,
      "as": 16
    },
    {
      "round": 22,
      "home": "WST",
      "away": "PAR",
      "hs": 13,
      "as": 16
    },
    {
      "season": 2026,
      "round": 23,
      "home": "GLD",
      "away": "NQL",
      "hs": 8,
      "as": 30
    },
    {
      "season": 2026,
      "round": 23,
      "home": "NZW",
      "away": "PEN",
      "hs": 28,
      "as": 12
    },
    {
      "season": 2026,
      "round": 23,
      "home": "SYD",
      "away": "CAN",
      "hs": 20,
      "as": 18
    },
    {
      "season": 2026,
      "round": 23,
      "home": "MEL",
      "away": "MAN",
      "hs": 42,
      "as": 20
    },
    {
      "season": 2026,
      "round": 23,
      "home": "DOL",
      "away": "BRI",
      "hs": 40,
      "as": 32
    },
    {
      "season": 2026,
      "round": 23,
      "home": "SOU",
      "away": "PAR",
      "hs": 28,
      "as": 24
    },
    {
      "season": 2026,
      "round": 23,
      "home": "CBR",
      "away": "NEW",
      "hs": 24,
      "as": 30
    },
    {
      "season": 2026,
      "round": 23,
      "home": "STI",
      "away": "CRO",
      "hs": 24,
      "as": 16
    },
    {
      "season": 2026,
      "round": 24,
      "home": "PEN",
      "away": "SYD",
      "hs": 6,
      "as": 12
    },
    {
      "season": 2026,
      "round": 24,
      "home": "MAN",
      "away": "DOL",
      "hs": 0,
      "as": 22
    },
    {
      "season": 2026,
      "round": 24,
      "home": "CAN",
      "away": "SOU",
      "hs": 6,
      "as": 22
    },
    {
      "season": 2026,
      "round": 24,
      "home": "CRO",
      "away": "CBR",
      "hs": 20,
      "as": 24
    },
    {
      "season": 2026,
      "round": 24,
      "home": "PAR",
      "away": "NQL",
      "hs": 32,
      "as": 30
    },
    {
      "season": 2026,
      "round": 24,
      "home": "BRI",
      "away": "NZW",
      "hs": 6,
      "as": 40
    }
  ]
};
