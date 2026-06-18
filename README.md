# f1-history-explorer

An F1 history explorer (Hysplex umbrella), built on the CC0 **"Formula 1 World
Championship 1950–2024"** dataset (compiled from Ergast).

## Status: Phase A — validated relational base + teammate head-to-head spine ✅

Phase A is **ingest + a validated relational base + the factual teammate
head-to-head spine** only. No rankings, no Elo, no car-normalisation, no UI —
those are later phases. Strict phase-gate discipline applies: every number
reconciles to a known-true value before we proceed (see the gate below).

## Quick start

```bash
pip install duckdb pyarrow
python3 pipeline/run_phase_a.py     # ingest -> teammate H2H -> gate (exits non-zero on any FAIL)
```

Outputs land in `build/f1.duckdb` and `data/parquet/` (both git-ignored — they
are regenerated from the committed raw CSVs).

## Pipeline

| Script | Does |
|--------|------|
| `pipeline/ingest.py` | Loads every raw CSV (prints a manifest: row counts + columns), builds the validated relational artifacts. |
| `pipeline/teammate_h2h.py` | Builds the teammate head-to-head spine (per-race, per-season, career). |
| `pipeline/gate.py` | Reconciles artifacts to known F1 truths; prints PASS/FAIL; exits non-zero on any FAIL. |
| `pipeline/run_phase_a.py` | Runs all three in order. |

## Raw inputs (`data/raw/`, CC0 / Ergast-compiled)

| CSV | Rows | CSV | Rows |
|-----|-----:|-----|-----:|
| circuits | 77 | races | 1,125 |
| constructors | 212 | results | 26,759 |
| drivers | 861 | sprint_results | 360 |
| seasons | 75 | qualifying | 10,494 |
| status | 139 | driver_standings | 34,863 |
| constructor_standings | 13,391 | constructor_results | 12,625 |
| pit_stops | 11,371 | lap_times | 589,081 |

## Validated artifacts (`data/parquet/`)

| Artifact | Rows | Grain / contents |
|----------|-----:|------------------|
| `dim_drivers` | 861 | driver reference (id, ref, code, name, dob, nationality) |
| `dim_constructors` | 212 | constructor reference |
| `dim_circuits` | 77 | circuit reference |
| `fact_races` | 1,125 | one row per race: season, round, circuit, date |
| `fact_results` | 26,759 | one row per driver per race: grid, finish_position, status, points, constructor, `classified` flag |
| `fact_qualifying` | 10,494 | one row per driver per race with qualifying data (1994+); quali_position, Q1/Q2/Q3, `has_time` |
| `teammate_pair_race` | 20,423 | one row per (teammate pair, race): the granular comparison |
| `teammate_pair_season` | 6,737 | one row per (season, constructor, driverA<driverB) |
| `teammate_career` | 815 | one row per driver: career teammate record |

### Classification rule (the DNF rule, stated)

A driver is **classified** in a race iff Ergast `position` is non-NULL
(equivalently `positionText` is numeric). This mirrors official F1 classification
(completed ≥90% of race distance). Non-numeric `positionText` codes —
`R` retired / not classified, `D` disqualified, `E` excluded, `W` withdrawn,
`F` failed to qualify, `N` not classified — are **not classified**.

## Teammate head-to-head spine

Same car, same season is the only car-controlled comparison available without
modelling car pace, so it is the factual spine later phases build on.

### `teammate_pair_season` schema

`season, constructorId, driverA, driverB` (driverA < driverB), then:

- `common_races` — races where **both** drove for that constructor.
- `race_h2h_races`, `a_race_wins`, `b_race_wins`, `race_ties` — race head-to-head.
- `a_only_classified`, `b_only_classified`, `both_dnf` — the excluded asymmetric/DNF cases, kept visible.
- `quali_h2h_races`, `a_quali_wins`, `b_quali_wins`, `quali_ties` — qualifying head-to-head.
- `a_points`, `b_points` — points each scored across the pair's common races.

`teammate_career` rolls these up per driver (directed): `quali_wins/losses`,
`race_wins/losses/ties`, `points_for/against`, `distinct_teammates`, `pair_seasons`.

### Rules for the messy realities (stated, not papered over)

- **Pair identification.** Pairs are per `(season, constructorId)`. A constructor
  with N drivers in a season produces all C(N,2) pairs, so **3+ drivers in one
  seat** become multiple pairwise records.
- **Common races.** A race counts for a pair only if **both** drivers have a
  result row for that constructor that weekend. So **mid-season swaps** simply
  yield fewer (possibly zero) common races, and a driver who **changes team
  mid-season** is paired, per constructor, with the teammates at each team.
- **Race H2H.** Counted only over common races where **both are classified**;
  lower finishing position wins. Races where either retired/was unclassified
  (DNF/DNS/DNQ/DSQ) are **excluded** from win/loss and reported separately. Equal
  finishing position (historic shared drives) counts as a **tie**.
- **Qualifying H2H.** Counted only over races where **both set a timed lap**
  (Q1/Q2/Q3 present) and have a qualifying position; lower position wins. Source
  is the dedicated qualifying table (**1994+ only**); earlier seasons have zero
  qualifying-H2H races — grid position is deliberately **not** used as a
  substitute because grid penalties distort it.
- **Points within pairing.** Points each driver scored over the pair's common
  races (head-to-head points, not full-season points).

## Phase A gate (reconciliation to known F1 truths)

`python3 pipeline/gate.py` → **17 PASS / 0 FAIL**. Highlights:

- **1950 championship.** P1 Nino Farina (30 pts), P2 Juan Fangio (27 pts), both
  Alfa Romeo teammates. ✅
- **Race counts.** 1950 = 7 (incl. Indianapolis 500); 2010 = 19; 2019 = 21;
  2021 = 22; 2022 = 22. ✅
- **2016 Mercedes (Rosberg beat Hamilton for the title).** Season points Rosberg
  385 > Hamilton 380 ✅. Head-to-head is honestly the other way: Hamilton won
  qualifying **12–8** and the race H2H **10–9** — Rosberg took the title on more
  wins + Hamilton's reliability DNFs. Directionally correct.
- **Totals.** 861 drivers, 212 constructors, 1,125 races, 75 seasons. ✅
- **Lopsided teammate quali H2H.** 2019 Red Bull — Verstappen out-qualified
  Gasly **10–1** (a factor in Gasly's mid-season demotion). ✅

Any FAIL exits non-zero and blocks the phase.
