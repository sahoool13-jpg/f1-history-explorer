"""Phase B — catalogue of F1 championship points systems and dropped-score rules.

Everything here is FACTUAL and SOURCED. Two orthogonal things are catalogued:

  1. POINTS TABLES (position -> points), plus the fastest-lap rule of each era.
  2. DROPPED-SCORES (best-N / split-season) rules, which are a SEASON property,
     not a points-table property.

Sources: Wikipedia "List of Formula One World Championship points scoring systems"
and the FIA sporting regulations of each era; cross-checked in this repo by
reconciling recomputed championship totals against the dataset's own
driver_standings (the master gate). Where the dataset cannot reproduce the
official total exactly, the season is FLAGGED below rather than guessed.

Conventions
-----------
* A points TABLE is the list of points awarded to finishing positions 1,2,3,...
* FL rule codes: 'fl_top5' = +1 to the fastest-lap setter if classified in the
  top 5 (1950-1959); 'fl_top10' = +1 if classified in the top 10 (2019-2024);
  'none' otherwise.
* Dropped-scores rule:
    ('all',)                  every result counts
    ('best', N)               best N race scores count
    ('split', H, A, B)        best A of the first H rounds + best B of the rest
"""

# ---------------------------------------------------------------------------
# 1. POINTS TABLES  (named system -> spec)
# ---------------------------------------------------------------------------
# Each entry: positions vector, fastest-lap rule, the seasons it was the OFFICIAL
# table, and a source note. `verified` is set by validate() against the data.
POINTS_TABLES = {
    "T1950_8642_FL": {
        "points": [8, 6, 4, 3, 2],
        "fl_rule": "fl_top5",
        "seasons": list(range(1950, 1960)),
        "source": "1950-59 FIA: 8-6-4-3-2 to top 5 + 1 pt for fastest lap. "
                  "(Indianapolis 500 counted toward the championship 1950-1960.)",
    },
    "T1960_864321": {
        "points": [8, 6, 4, 3, 2, 1],
        "fl_rule": "none",
        "seasons": [1960],
        "source": "1960 only: 8-6-4-3-2-1 to top 6; fastest-lap point dropped.",
    },
    "T1961_964321": {
        "points": [9, 6, 4, 3, 2, 1],
        "fl_rule": "none",
        "seasons": list(range(1961, 1991)),
        "source": "1961-1990: 9-6-4-3-2-1 to top 6.",
    },
    "T1991_1064321": {
        "points": [10, 6, 4, 3, 2, 1],
        "fl_rule": "none",
        "seasons": list(range(1991, 2003)),
        "source": "1991-2002: 10-6-4-3-2-1 to top 6 (winner raised 9->10).",
    },
    "T2003_10to1": {
        "points": [10, 8, 6, 5, 4, 3, 2, 1],
        "fl_rule": "none",
        "seasons": list(range(2003, 2010)),
        "source": "2003-2009: 10-8-6-5-4-3-2-1 to top 8.",
    },
    "T2010_25to1": {
        "points": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
        "fl_rule": "none",
        "seasons": list(range(2010, 2019)),
        "source": "2010-2018: 25-18-15-12-10-8-6-4-2-1 to top 10.",
    },
    "T2019_25to1_FL": {
        "points": [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
        "fl_rule": "fl_top10",
        "seasons": list(range(2019, 2025)),
        "source": "2019-2024: 25-...-1 to top 10 + 1 pt fastest lap if classified "
                  "in the top 10. (Sprint points added on sprint weekends: 3-2-1 "
                  "in 2021, 8-7-6-5-4-3-2-1 from 2022.)",
    },
}

# season -> the OFFICIAL points-table key in force that year
SEASON_TABLE = {yr: key for key, spec in POINTS_TABLES.items() for yr in spec["seasons"]}

# ---------------------------------------------------------------------------
# 2. DROPPED-SCORES RULES  (season -> rule)
# ---------------------------------------------------------------------------
# Validated against driver_standings totals (see validate_dropped_scores in
# feature1). 1956 is FLAGGED: a shared-drive / dropped-score accounting quirk
# leaves Fangio's official total 1.5 pts below the naive best-5 (champion
# unaffected). 1975's rule (best 6 of first 7 + best 6 of last 7) was confirmed
# empirically against the data.
DROPPED_SCORES = {
    1950: ("best", 4), 1951: ("best", 4), 1952: ("best", 4), 1953: ("best", 4),
    1954: ("best", 5), 1955: ("best", 5), 1956: ("best", 5), 1957: ("best", 5),
    1958: ("best", 6), 1959: ("best", 5), 1960: ("best", 6), 1961: ("best", 5),
    1962: ("best", 5), 1963: ("best", 6), 1964: ("best", 6), 1965: ("best", 6),
    1966: ("best", 5),
    1967: ("split", 6, 5, 4), 1968: ("split", 6, 5, 5), 1969: ("split", 6, 5, 4),
    1970: ("split", 7, 6, 5), 1971: ("split", 6, 5, 4), 1972: ("split", 6, 5, 5),
    1973: ("split", 8, 7, 6), 1974: ("split", 8, 7, 6), 1975: ("split", 7, 6, 6),
    1976: ("split", 8, 7, 7), 1977: ("split", 9, 8, 7), 1978: ("split", 8, 7, 7),
    1979: ("split", 7, 4, 4), 1980: ("split", 7, 5, 5),
    1981: ("best", 11), 1982: ("best", 11), 1983: ("best", 11), 1984: ("best", 11),
    1985: ("best", 11), 1986: ("best", 11), 1987: ("best", 11), 1988: ("best", 11),
    1989: ("best", 11), 1990: ("best", 11),
    # 1991+ : all results count
}

# seasons whose totals do NOT reconcile to the dataset exactly (champion still correct)
FLAGGED_SEASONS = {
    1956: "Shared-drive points interacting with the best-5 rule leave Fangio's "
          "official total 1.5 pts below the naive best-5 (30.0 vs 31.5). Champion "
          "unaffected (Fangio >> Moss 27). Flagged, not guessed.",
}


def dropped_rule(season):
    """Return the dropped-scores rule for a season ('all',) if none."""
    return DROPPED_SCORES.get(season, ("all",))


def apply_dropped(rule, points_by_round):
    """Apply a dropped-scores rule to {round: points} -> championship points."""
    if not points_by_round:
        return 0.0
    if rule[0] == "all":
        return sum(points_by_round.values())
    if rule[0] == "best":
        return sum(sorted(points_by_round.values(), reverse=True)[: rule[1]])
    if rule[0] == "split":
        h, a, b = rule[1], rule[2], rule[3]
        first = sorted((v for r, v in points_by_round.items() if r <= h), reverse=True)
        second = sorted((v for r, v in points_by_round.items() if r > h), reverse=True)
        return sum(first[:a]) + sum(second[:b])
    raise ValueError(rule)


def points_for_position(table_key, position, fl=False):
    """Points a finishing `position` earns under a points TABLE (1-indexed).

    `fl=True` adds the fastest-lap point where the table's FL rule grants it
    (caller is responsible for the top-5/top-10 eligibility)."""
    spec = POINTS_TABLES[table_key]
    pts = spec["points"][position - 1] if (position and position <= len(spec["points"])) else 0.0
    if fl and spec["fl_rule"] != "none":
        pts += 1.0
    return float(pts)
