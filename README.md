# f1-history-explorer

An F1 history explorer (Hysplex umbrella), built on the CC0 **"Formula 1 World
Championship 1950–2024"** dataset (compiled from Ergast).

## Status: Phase A ✅ + Phase B (championship analysis) ✅

Phase A is **ingest + a validated relational base + the factual teammate
head-to-head spine** only. No rankings, no Elo, no car-normalisation, no UI —
those are later phases. Strict phase-gate discipline applies: every number
reconciles to a known-true value before we proceed (see the gate below).

## Quick start

```bash
pip install duckdb pyarrow
python3 pipeline/run_phase_a.py     # ingest -> teammate H2H -> gate (exits non-zero on any FAIL)
python3 pipeline/run_phase_b.py     # Phase A + championship features + Phase B gate
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

---

# Phase B — championship analysis ✅

Three **new, fully-factual** championship views — pure recomputation of real
results (no modelling, no estimates, no car-normalisation; that's a later phase).
Each feature has its own gate. The **master gate** (Feature 1a) is the most
important: recomputing every season under its *own* historical system must
reproduce the real champion.

Run: `python3 pipeline/run_phase_b.py` → **Phase B gate: 11 PASS / 0 FAIL**.

| Script | Feature |
|--------|---------|
| `pipeline/points_systems.py` | Catalogue of points tables + dropped-scores rules (sourced). |
| `pipeline/feature1_points_invariance.py` | "Would the champion change under different scoring?" |
| `pipeline/feature2_clinch.py` | "When was the title clinched, and how close did it get?" |
| `pipeline/feature3_teammate_champions.py` | "How did each champion fare vs their teammate?" |
| `pipeline/gate_phase_b.py` | All three gates; exits non-zero on any FAIL. |

## Points-system catalogue (`points_systems.py`)

Distinct **points tables** (position → points) + fastest-lap rule + the seasons
each applied (sources in code):

| Table | Points | FL | Seasons |
|-------|--------|----|---------|
| 8-6-4-3-2 | top 5 | +1 fastest lap (top-5 finisher) | 1950–1959 |
| 8-6-4-3-2-1 | top 6 | — | 1960 |
| 9-6-4-3-2-1 | top 6 | — | 1961–1990 |
| 10-6-4-3-2-1 | top 6 | — | 1991–2002 |
| 10-8-6-5-4-3-2-1 | top 8 | — | 2003–2009 |
| 25-18-15-12-10-8-6-4-2-1 | top 10 | — | 2010–2018 |
| 25-…-1 | top 10 | +1 fastest lap (if top-10) | 2019–2024 (+sprint pts) |

**Dropped-scores** (a *season* property, not a table property) is catalogued per
season: `best N` (1950–1966, 1981–1990), split-season `best A of first H + best B
of rest` (1967–1980), or all-count (1991+). Validated by reproducing official
`driver_standings` totals: **74/75 seasons reconcile exactly**. **1956 is flagged**
(shared-drive points interacting with the best-5 rule leave Fangio's official
total 1.5 below the naive best-5; champion unaffected) — flagged, not guessed.

### Feature 1 — points-system invariance

Stated assumptions (in code): the **actual champion** is real history; the
**faithful recomputation** (real per-race points + the season's real dropped
rule) is what reconciles to history; the **cross-table comparison** applies each
table's position vector to real finishing positions with **all results counting
and no fastest-lap points held constant**, to isolate the table shape. The
dropped-scores effect is shown explicitly for each season's own table.

Output (`f1_points_invariance.parquet`): per season × points table → champion
under that table and whether it differs from the actual champion. **16/75 seasons
would have a different champion under some table.** Highlights (all factual
recomputations): **2008** → Massa under the old 6-pt-gap systems; **1958** → Moss
under 10-6-4; **1988** the dropped-scores story — best-11 (real) **Senna 90 >
Prost 87**, total points **Prost 105 > Senna 94**.

### Feature 2 — clinch geometry

Remaining-points math against the official running standings. **Weekend max** =
race-win + fastest-lap (where the era awards it) + sprint-win (sprint weekends).
**Clinch** = first round where `champion > best_rival + remaining_max` (strict;
ties are *not* recomputed). Sound (never early); possibly one race conservative
pre-1991 due to dropped-scores (flagged).

Output (`f1_clinch.parquet`): `clinch_round`, `clinch_race`,
`races_remaining_at_clinch`, `went_to_finale`, `closest_margin`. **36/75 titles
went to the final race.** Validated: 2008 (Brazil, finale), 2021 (Abu Dhabi,
finale), 2002 (France, round 11, 6 to spare — the famous early clinch).

### Feature 3 — teammate-adjusted champions

Joins each season's champion to Phase A's teammate-H2H spine (sums across all
teammates that season; ties back to Phase A exactly). Respects the 1994+
qualifying boundary (pre-1994 = race H2H only).

Output (`f1_champion_teammate.parquet`). Anomalies surfaced: champions
**out-qualified by a teammate** — 2007 Räikkönen (8-9), 2009 Button (7-10), 2014
Hamilton (7-11), **2016 Rosberg (8-12 vs Hamilton)**; champions **out-raced** —
e.g. 1989 Prost (1-7 vs Senna), 2016 Rosberg (9-10). Dominant: 2024 Verstappen
(23-1 vs Pérez), 2013 Vettel (17-2 vs Webber).

## Phase B gate (11 PASS / 0 FAIL)

| Check | Result |
|-------|--------|
| **MASTER**: own-system recomputation reproduces the real champion, ALL 75 seasons | PASS (75/75) |
| Own-system reproduces official totals (unflagged seasons) | PASS (74/75 exact; 1956 flagged) |
| Points-table catalogue matches observed per-position points | PASS |
| 1988 best-11 → Senna; total points → Prost | PASS |
| 2008 & 2021 titles decided at the final race | PASS |
| 2002 Schumacher clinched round 11, 6 races to spare | PASS |
| 2016 Rosberg out-qualified by teammate Hamilton (8-12) | PASS |
| Feature 3 ties back to Phase A teammate spine (no divergence) | PASS |
| 2013 Vettel dominated teammate in qualifying (17-2) | PASS |

New Parquet artifacts: `f1_points_invariance`, `f1_clinch`, `f1_champion_teammate`.
