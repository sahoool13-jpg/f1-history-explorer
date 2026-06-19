# f1-history-explorer

An F1 history explorer (Hysplex umbrella), built on the CC0 **"Formula 1 World
Championship 1950–2024"** dataset (compiled from Ergast).

## Status: Phases A–K ✅ COMPLETE  ·  Phase L (axis-fairness) in progress

> **Phase L / FIX 1 (racecraft grid-opportunity).** The old racecraft used the raw teammate
> finishing-position margin, which **penalises dominant front-runners** (no positions to gain
> at the front) — `corr(CRAFT_z, mean grid) = −0.427`. We switch to **CONVERSION** =
> `(finish_gap − grid_gap)`: positions gained on the teammate *during the race*, beyond pace.
> A pole-sitter who holds station now reads ~0 (neutral), not penalised; the opportunity
> carvers (Sainz #7→#13, Leclerc #8→#15, Ocon, Gasly) compress. Bias **−0.427 → −0.193**.
>
> **Honest finding (decided by a z²/v signal-to-noise scan, not by preference):** in teammate
> data the **grid gap ≈ the pace gap** (the faster teammate qualifies ahead), so once *both*
> are removed the residual is statistically indistinguishable from noise — only **3 drivers**
> clear z²/v ≥ 4, **none** ≥ 9. Signal is **concentrated → Option C**: no τ² floor, racecraft
> sits **honestly near-dead** (τ²≈0.001, points ~0, wide intervals) — *we do not manufacture a
> signal*. It is **flagged "weakly identified"**, defaulted to a **low weight (12%)**, and the
> explainer states the confound. The penalised front-runners (Vettel #16→#12, Häkkinen #25→#20)
> recover from the **removed penalty**, not from a racecraft contribution. τ² re-estimated:
> pace 0.883 / racecraft 0.001 / longevity 0.975. Gate: `run_phase_l_fix1.py` →
> **FIX 1: 11 PASS / 0 FAIL** (+ J 13/13, K 10/10, Option-C-aware). *(FIX 2, longevity skew, is
> a separate PR.)*

## Status: Phases A–K ✅ COMPLETE (base · championship · pace · car-normalised model · time-varying · era-normalised · racecraft · longevity · user-weighted composite · interval-aware refinement + radar)

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

---

# Phase C — "Lift and Coast" front-end (identity, first pass) ✅

A static, deployable **timing-screen / telemetry** presentation layer over the
validated Phase A/B numbers. Pure recomputation only — the UI invents nothing.

```bash
python3 pipeline/run_phase_b.py     # rebuild + validate the data
python3 pipeline/export_web.py       # -> web/data.js (self-contained)
open web/index.html                  # or serve web/ as a static site
```

The site is **zero-dependency and serverless**: `export_web.py` inlines all
artifacts into `web/data.js` (`window.LAC_DATA`), so `web/index.html` works
straight from `file://` or any static host (e.g. GitHub Pages).

## Identity

- **Wordmark** "LIFT AND COAST" — the racing term for backing off the throttle to
  save fuel/tyres/brakes; a wry, insider name about tactical restraint and race
  management, not raw speed. Rendered in a technical display face (Chakra Petch)
  with a blinking telemetry cursor.
- **Aesthetic** — dark technical base, **monospace tabular numerals** (IBM Plex
  Mono) as the signature typography for every time, gap and points figure; faint
  CRT scanlines; broadcast-hardware feel.
- **Accent** — a single disciplined **sodium-amber** (`#ffb000`), the pit-lane /
  trackside-light tone, fitting the measured, cerebral mood. (First pass — easy to
  retune now that it's live.)
- **Timing-screen colour semantics** as an honest data-encoding system, distinct
  from the brand accent: **purple** = outright best, **green** = personal/season
  best (held), **yellow** = slower / tie, used for teammate H2H bars and the
  invariance table.

## What it shows (per season)

A four-panel dossier driven by a season selector (← / → / keyboard):

1. **Champion** — name, constructor, points, wins (tabular numerals).
2. **Clinch geometry** (Feature 2) — clinch round + race, a round-by-round bar
   with the clinch marker, went-to-the-wire vs races-to-spare, closest P1–P2
   margin.
3. **Points-system invariance** (Feature 1) — a mini timing table: champion under
   every historical scoring table, with the era's real table marked, **flips** in
   amber and **ties shown as ties** (no invented tie-break).
4. **Vs. teammate** (Feature 3) — qualifying & race H2H split bars (purple/yellow),
   head-to-head points, the pre-1994 no-quali note, and an **anomaly** callout when
   the champion was beaten by their own teammate.

A stat tower headlines the dataset (75 seasons, 1,125 GPs, 36 finale titles, 14
scoring-sensitive seasons, 10 with a tie under some system) and the footer carries
the **non-affiliation disclaimer** and the **CC0 data credit** (Ergast / Chris
Newell, rohanrao on Kaggle).

> No F1/FIA trademarks or logos are used. "Lift and Coast" is generic racing
> terminology.

## Cross-season discovery views (Phase C addendum)

The front-end started as a per-season dossier; it now also has **browsable,
cross-season leaderboards** so the Phase B findings are discoverable as lists,
not one season at a time. Hash-routed, same timing-screen identity, and every
figure traces to the validated Phase A/B artifacts (presentation only — nothing
recomputed; the exporter only *reads* `driver_standings` P2 to add the runner-up
name for the finals view).

| Route | View | Rows | Reconciles to |
|-------|------|-----:|---------------|
| `#/beaten` | Champions beaten by their teammate | 9 | `f1_champion_teammate.out_qualified/out_raced` |
| `#/scoring` | Scoring-sensitive titles — **flips (14)** and **ties (10)** kept distinct | 24 | `f1_points_invariance` (`scoringSensitive`=14, `tieSeasons`=10) |
| `#/finals` | Final-race deciders, closest-margin first | 36 | `f1_clinch.went_to_finale` |
| `#/clinch` | Earliest clinches (most races to spare) | 75 | `f1_clinch.races_remaining_at_clinch` |

- **Navigation:** a tab bar under the masthead (`SEASON DOSSIER · BEATEN BY
  TEAMMATE · SCORING-SENSITIVE · FINAL-RACE DECIDERS · EARLY CLINCHES`); the
  stat-tower cells for "to the final race" / "scoring-sensitive" / "tie under a
  system" are also click-throughs.
- **Discovery → detail:** every list row deep-links to that season's dossier
  (`#/s/<year>`); the legacy `#<year>` hash still resolves.
- **Integrity:** flips and ties stay distinct (the Phase C tie-detection fix). A
  season can appear in both scoring blocks when different tables give different
  outcomes (e.g. 2008 flips to Massa under the 6-pt systems but ties under
  8-6-4-3-2) — shown honestly, not conflated.
- Timing-colour semantics carry through: purple/yellow for H2H winner/loser,
  amber for "changed outcome", green for dominance (races to spare).

> Validated via Python + jsdom in the sandbox (DuckDB-wasm can't run here); the
> live render still needs an eyeball check on the deployed site.

---

# Phase D — pace & deltas foundation ✅

Tenths-level pace **measurement** on the real lap-time and qualifying data — the
empirical bedrock for the eventual car-normalisation USP (Phase E). **Pure
measurement, no modelling.** Guiding principle: compute a delta only where the
comparison is genuinely clean, and tag every delta with a **comparability tier**
so nothing reads as more precise than it is.

Run: `python3 pipeline/run_phase_d.py` → **Phase D gate: 17 PASS / 0 FAIL**.

| Tier | Meaning | Artifact(s) |
|------|---------|-------------|
| **1** | same session / track / car | `quali_teammate_delta_*` |
| **2** | same race / car, clean-lap method | `racepace_teammate_*` |
| **3** | cross-era / cross-context (contextual only) | `event_pace`, `circuit_layout` |

| Artifact | Rows | Grain |
|----------|-----:|-------|
| `quali_teammate_delta_race` | 5,231 | per (pair, race): deepest-common-session gap (s) |
| `quali_teammate_delta_pairseason` | 456 | per (season, constructor, pair): robust mean/median/std |
| `quali_teammate_delta_career` | 172 | per driver: pooled delta vs all teammates |
| `racepace_teammate_race` | 5,321 | per (pair, race): clean-lap pace delta (s/lap) + reliability |
| `racepace_teammate_pairseason` | 407 | per (season, constructor, pair): aggregate over reliable races |
| `event_pace` | 1,125 | per race: pole time + fastest race lap (Tier-3 facts) |
| `circuit_layout` | 77 | per circuit: layout-stability note + heuristic discontinuity flag |

## Methods (exact)

**Qualifying delta (Tier 1).** Times parsed `M:SS.mmm`→seconds. Comparison basis =
the **deepest qualifying session both drivers set a time in** (Q3 if both reached
it, else Q2, else Q1) — strictly like-for-like. `gap = A − B` (pair ordered
driverA<driverB; negative ⇒ A faster). A `|gap| > 3.0s` is flagged
**non-representative** (crash/mechanical/aborted lap) and excluded from the stats
(counted separately); races with no common timed session are counted as
`no_common_session`. **Median is the primary statistic** (incident-insensitive);
mean/std use an additional within-pair MAD fence (median ± 3·1.4826·MAD, scale
floored at 0.25s). 1994+ only.

**Race-pace delta (Tier 2).** From `lap_times.milliseconds`, a **clean green-lap
median**, not a naive mean. Per race we exclude: **lap 1**; **safety-car/VSC laps**
(field-median lap > 1.15× the race baseline, excluded field-wide); **pit in/out
laps** (`{pit_lap, pit_lap+1}` from pit_stops, 2011+; earlier races fall back to
outliers); **per-driver outliers** (slower than median+3·1.4826·MAD, or >1.30× own
median). Pace = median of remaining clean laps; `delta = A − B` (s/lap). Each race
carries a **reliability** tag — `low` if: <8 clean laps for either driver; either
classified with <90% race distance (DNF/delayed); >30% safety-car laps; pit-count
differs by ≥2 (strategy); or clean-lap imbalance. Only `ok` races feed the
pair-season aggregate; `low` races are kept but counted separately.

**Pole & fastest lap (Tier 3).** Per-event facts (pole = polesitter's best session
time; fastest lap = min lap-time). Cross-era comparison is **contextual only**:
circuit layout/length history is **not in the dataset**, so `layout_stability` is
`undetermined`; a heuristic flags year-on-year pole jumps >4% as a *possible*
layout/regulation change (not ground truth). A 2004 vs 2024 lap is **not** the same lap.

## Phase D gate (17 PASS / 0 FAIL)

| Check | Result |
|-------|--------|
| 2016 Mercedes HAM vs ROS quali delta | **−0.159s median** (Hamilton faster), tenths; sign-count 12–7 reconciles Phase A 12–8 |
| 2019 Red Bull VER vs GAS quali delta | **−0.409s** (Verstappen faster), large; sign-count 10–1 matches Phase A |
| Race-pace clean race (2016 Abu Dhabi) | +0.173s/lap, reliability **ok** |
| Safety-car race (2016 Brazil, 46% SC) | correctly flagged **low** (`safety_car_heavy`) |
| DNF race (2016 Malaysia) | correctly flagged **low** (`dnf_or_delayed`) |
| Clean-lap exclusion (2016 Brazil) | 71 total laps → 35/36 clean retained (lap 1 + SC + pit/outliers removed) |
| Sample-size honesty | 1,980 low-reliability flagged; 91 pair-seasons with ≤2 reliable races exposed |
| Comparability tiers | every artifact row carries its tier (1/2/3) |

This phase is data/computation; the deltas presentation will be designed once the
numbers are validated. (Validated via Python; live render — none added this phase.)

### Surfaced in the UI (presentation pass)

The validated deltas now appear in **Lift and Coast** (presentation only — read
straight from the artifacts, nothing recomputed):

- **Season dossier → VS. TEAMMATE** shows the champion's measured **qualifying Δ**
  (Tier 1, e.g. *HAM −0.159s vs ROS*, median over n races) and **race-pace Δ**
  (Tier 2, s/lap, with the reliable / flagged-low race counts) beside the H2H counts.
- **`#/pace` — Teammate pace gaps**: a cross-season leaderboard of every pair-season's
  quali Δ and race-pace Δ, faster driver in timing-purple with the negative sign.
- **Tier chips (T1/T2/T3)** sit on every delta; the ranked list requires ≥5
  comparison races (small samples drop to a separate dimmed section), and
  race-pace deltas from <3 reliable races are dimmed and flagged. The 1994+ /
  1996+ data boundaries are shown explicitly.

---

# Phase E — car-normalisation model (the USP) ⚠️ ESTIMATE

The first phase that **models** rather than measures. It estimates a relative
driver **qualifying-pace** rating with the car removed, by solving the
teammate-delta network. **There is no ground-truth "skill" column — every output
here is an UNFALSIFIABLE ESTIMATE, not a measured fact.** It is labelled as such,
ships with uncertainty, and is kept structurally separate from the validated
Phase D measurements.

Run: `python3 pipeline/run_phase_e.py` → **Phase E gate: 17 PASS / 0 FAIL** (method
& sanity, *not* correctness — correctness is unprovable).

## Method — teammate-linkage network least-squares

Nodes = drivers (career-average pace). Edges = Phase D **Tier-1 teammate
qualifying deltas** (one per pair-season). The car cancels within a teammate pair,
so each edge observes the driver-pace difference `r_A − r_B ≈ d_AB`. We solve all
edges at once by **weighted least squares** — a chained teammate comparison
(A>B, B>C ⇒ A>C) propagated across the connected graph:

> minimise `Σ_k w_k (r_i − r_j − d_k)²`, gauge `Σ r = 0`,
> with `w_k = n_k / (std_k² + 0.15²)` (inverse-variance; the 0.15 s floor stops a
> 1-race edge being over-trusted). Normal equations `L r = b` (L = weighted graph
> Laplacian); solved `r = L⁺ b` (pseudoinverse → unique mean-zero solution).

Rating is in **seconds vs the field mean, lower = faster**. Network spans **170
drivers / 454 edges** (one giant component, 1994+); 2 isolated drivers are flagged
not-comparable.

## Uncertainty — analytic propagation (+ bootstrap cross-check)

- Residual scale `σ̂² = Σ w_k resid_k² / dof`. Here **σ̂² ≈ 6**: the
  single-number-per-driver (career-average) assumption leaves real scatter, so we
  **scale the covariance by σ̂²**, widening every interval honestly. (Driver-season
  *dynamic* modelling is the natural future refinement.)
- Covariance `C = σ̂²·L⁺`; per-driver 95% CI `= ±1.96·√C_ii`.
- **Pairwise** `Var(r_i − r_j) = σ̂²·R_eff(i,j)` — the **effective resistance**:
  short, high-sample chains (direct modern teammates) → tight; long, weak,
  cross-era chains → wide. This is *why* cross-era rankings must not read as
  confident.
- A fixed-seed bootstrap (seed `20240619`, 400 resamples) independently confirms
  the analytic σ (corr ≈ 0.64 over rankable drivers).

A driver is **`rankable`** (confident headline) only if well-connected
(≥3 teammates, ≥5 observations, σ ≤ 0.30 s). Degree-1 / isolated / high-σ drivers
are flagged and **excluded from confident ranking**.

## Example estimates (WITH intervals)

| Driver | Estimate (s vs mean) | 95% CI | Teammates | Confidence |
|--------|---------------------:|:------:|:---------:|------------|
| Max Verstappen | −1.113 | ±0.208 | 5 | rankable (tight, modern) |
| Lewis Hamilton | −0.992 | ±0.181 | 6 | rankable |
| Fernando Alonso | −0.979 | ±0.169 | 13 | rankable (best-connected) |
| Michael Schumacher | −1.052 | ±0.233 | 7 | rankable |
| Ayrton Senna | −1.29 | ±0.64 | 1 | **sparse** — 1994 only, not rankable |
| Roland Ratzenberger | +1.57 | ±3.22 | 1 | **sparse** — 1 race, not rankable |

**Cross-era is not confidently separable:** Schumacher vs Verstappen — estimated
gap 0.061 s but pairwise 95% CI **±0.285 s** (long teammate chain), i.e. a
statistical tie. The model says so rather than inventing a cross-era ranking.

## Phase E gate (17 PASS / 0 FAIL — method/sanity, not truth)

| Group | Check | Result |
|-------|-------|--------|
| Anchor sanity | model doesn't invert direct strong edges (HAM<ROS, VER<GAS, VER<PER, HAM<BOT); 88.5% sign-agreement on strong edges | PASS |
| Reconstruction | solved ratings predict their own input deltas; median \|resid\| 0.124 s | PASS |
| Uncertainty | sparse CI (0.83 s) ≫ rankable CI (0.27 s); cross-era pairwise ≫ direct | PASS |
| Degenerate | isolated/degree-1 flagged, never rankable; dominant-car not inflated | PASS |
| Separation | estimates in their own `*_estimate` table, `is_estimate=1`, never merged into measured Tier-1 | PASS |
| Bootstrap | analytic vs bootstrap σ agree (corr 0.64) | PASS |

Artifacts: `driver_pace_model_estimate` (172 rows; rating + CI + connectivity +
confidence flag), `pace_model_residual` (454 rows; reconstruction residuals). Both
carry `is_estimate=1` and are separate from the Phase D measured-delta tables.

## Presentation spec (for a following pass — not built this phase)

The modelled ratings must be surfaced in a **clearly-labelled "MODEL / ESTIMATE"
context**, visually distinct from the measured timing-screen deltas:

- A dedicated `#/model` view titled as an **estimate**, with a persistent "this is
  our model, not measured fact" banner and a "how this works / limitations"
  explainer (method + σ̂² caveat + cross-era warning).
- **Confidence intervals shown as the primary visual** (error bars / CI ranges),
  never a naked point ranking. Drivers whose intervals overlap are shown as
  *not confidently separated*.
- Only **rankable** drivers in the headline ranking; sparse/isolated shown
  separately with their wide intervals and a flag.
- **No cross-era ranking without its (wide) interval**; offer a pairwise
  "compare two drivers" that reports the effective-resistance CI and says
  "statistical tie" when it is one.
- Keep the Lift and Coast identity, but the modelled section signals *estimate*
  (e.g. distinct treatment from the amber-on-black factual deltas) so it can never
  be mistaken for the measured Tier-1/2 numbers.

## Surfaced in the UI (`#/model` — presentation pass)

The model is now in the site at **`#/model`** ("PACE MODEL · est"), deliberately
**visually distinct** from the factual amber/timing panels — a violet "estimate"
treatment (dashed, hatched chrome) so it can never be mistaken for measured fact:

- An **unmissable caveat banner**: what it is (car-normalised *qualifying* pace vs
  teammates, 1994+) and what it is **not** (greatness, racecraft, wheel-to-wheel,
  titles, wet/tyre skill).
- **Confidence intervals are the hero**: each driver is a CI *band* with the point
  estimate as a tick on a shared seconds axis — **overlapping bars read as
  "not separable"**, never a naked leaderboard.
- A **pairwise compare** (defaults to Schumacher vs Verstappen) using the
  effective-resistance CI: it reports **"STATISTICAL TIE"** when the gap is within
  the uncertainty (SCH–VER: 0.061 s gap vs ±0.285 s).
- A **thin-evidence section** sorted fastest-estimate-first so the danger is
  obvious — Senna tops it on paper but with a ±0.64 s interval (3 races, 1994).
- A **how-it-works / limitations** explainer (teammate-network method,
  chain-confidence collapse, what the intervals mean, σ̂² caveat).

> **Era-framing correction:** the brief's example "Schumacher here largely reflects
> his 2010–2012 return" is **not** what the data shows — his teammate-delta record
> spans **1994–2012** and includes his Ferrari-prime teammates (Irvine, Barrichello,
> Massa). Stating the comeback-only caveat would have been false, so the UI uses the
> genuine era-limitation case (**Senna: 1994 only**) and shows each driver's real
> data span. Honesty over the script.

Every value is read from the validated `*_estimate` artifacts; the model section is
a separate `model` block in `web/data.js`, never merged with the measured deltas.


---

# Phase F — time-varying car-normalisation ⚠️ ESTIMATE

The evolution of the USP. Phase E used **one career-average rating per driver**,
blending prime and decline into a single number (so beating *late* Räikkönen was
miscredited as beating *career* Räikkönen). Phase F makes pace **time-resolved**:
a teammate comparison is between two drivers **at a point in time**, not two fixed
entities. Still an estimate — all the Phase E honesty discipline applies, and the
validated Phase D deltas are untouched.

Run: `python3 pipeline/run_phase_f.py` → **Phase F gate: 13 PASS / 0 FAIL**.

## Method — driver-SEASON nodes + a smoothing prior

Nodes become **driver-seasons** (e.g. `Räikkönen_2005` ≠ `Räikkönen_2020`). Edges:
- **Teammate edges** (one per Phase-D Tier-1 pair-season): `r_{A,yr} − r_{B,yr} ≈ d`.
- **Continuity (smoothing) edges**: a **random-walk prior** linking each driver's
  consecutive seasons `r_{d,s+gap} − r_{d,s} ≈ 0`, weight `λ/gap` — pace may drift
  year to year but not jump. This regularises the network (84% of driver-seasons
  have only one teammate edge, so without the prior they'd be unsolvable).

Solve `minimise Σ_tm w(r_i−r_j−d)² + Σ_cont (λ/gap)(r_i−r_j)²`, gauge `Σr=0`, via
`r = L⁺ b`. Graph: **766 driver-season nodes, 456 teammate + 594 continuity edges**.

### Choosing λ (the key tuning choice — stated, not hidden)

λ is **not** taken from CV-argmin. Cross-validation on this data is **monotone in
λ** (it keeps preferring more smoothing → collapse to the Phase-E career-average,
which defeats the phase) — CV is therefore *uninformative* here, and we report the
curve to show it. Instead λ is set from an **interpretable random-walk drift
prior**: `σ_drift = 0.10 s/yr` (a plausible year-on-year change for a top driver),
giving **λ = 1/σ_drift² = 100**. This sits in the CV-flat band and resolves known
career arcs without fitting single-season noise.

**Sensitivity** (Hamilton, under λ=25 / **100** / 400):

| Season | ×¼ (λ25) | ×1 (λ100) | ×4 (λ400) |
|--------|---------:|----------:|----------:|
| 2008 | −0.63 | **−0.62** | −0.59 |
| 2014 | −0.52 | **−0.54** | −0.55 |
| 2020 | −0.41 | **−0.44** | −0.47 |
| 2024 | −0.22 | **−0.26** | −0.34 |

Stronger smoothing flattens the late decline toward a career-average; weaker
smoothing tracks single seasons more closely. λ=100 keeps the arc while staying
smooth. (Full sensitivity for 5 drivers is in `pace_model_tv_sensitivity`.)

## Uncertainty

Same analytic propagation (`C = σ̂²·L⁺`, σ̂² scaled by the residual misfit). Effective
params `p_eff ≈ 304` of 766 nodes; **σ̂² = 3.34** (lower than Phase E's 6.09 — time
resolution explains more). Intervals are **wider than Phase E** (sparser nodes,
median 95% CI ≈ ±0.48 s) — that is honest: a driver-season on one thin edge *should*
read as very uncertain.

## Phase F gate (13 PASS / 0 FAIL) — has qualitative ground truth

| Check | Result |
|-------|--------|
| **Schumacher** comeback (2010–12 **−0.23**) rates below prime (1994–04 **−0.91**) | PASS (Δ +0.68) |
| **Räikkönen** Alfa (2019–21 **−0.28**) rates below prime (2005–07 **−0.39**) | PASS (Δ +0.10) |
| **Alonso** late (2021–24 **−0.38**) rates below peak (2005–12 **−0.66**) | PASS (Δ +0.29) |
| **Giovinazzi de-inflation**: Phase E **−0.894** → Phase F **−0.365** (benchmark is now faded Räikkönen, not career Räikkönen) | PASS (+0.53 s) |
| Smoothing sanity: Hamilton/Alonso arcs not flat, not noise (range ~0.4 s, median \|Δyr\| ~0.03–0.05 s) | PASS |
| Reconstruction: median \|resid\| **0.057 s** (Phase E 0.124 s) — time resolution fits better | PASS |
| Connectivity: single-edge driver-seasons wider & flagged; intervals widened honestly | PASS |
| Separation/labelling: `is_estimate=1`, measured Tier-1 deltas untouched | PASS |

**The Giovinazzi case is the thesis in one number:** career-blended Räikkönen
(−0.706, prime-weighted) made beating him look elite; time-resolved, the man
Giovinazzi actually out-qualified was *faded* Räikkönen (−0.284), so Giovinazzi's
estimate drops from a wildly inflated −0.894 to a midfield-realistic −0.365.

Artifacts: `driver_season_pace_estimate` (766 driver-seasons; rating + CI +
connectivity), `pace_model_tv_residual` (456), `pace_model_tv_sensitivity` (5
drivers × 3 λ). All `is_estimate=1`, separate from the measured deltas.

> Data/computation phase. The natural next presentation pass is **career-arc
> trajectory charts** (rating vs season with CI ribbons) in the `#/model` view —
> spec'd for a following pass, keeping the violet "estimate" treatment.

## Surfaced in the UI (`#/model` → Career arcs)

The time-varying model is now the **headline view** at `#/model` ("Career arcs"),
hand-rolled SVG in the violet estimate treatment (distinct from the amber factual
panels):

- **Single & multi-driver career arcs** (rating vs season): the point estimate as
  a line, with a **95% CI ribbon as the hero** — semi-transparent, **widening where
  evidence thins** (rookie years, single-teammate seasons, short careers; e.g.
  Alonso 2001 ±0.575 vs his 2004 peak ±0.333). **Faster is up**, axis explicitly
  labelled (lower s = faster).
- **Overlay of 2–4 drivers** (default **Schumacher · Alonso · Hamilton**) so peaks,
  plateaus and declines sit side by side; **overlapping ribbons read as "not
  confidently separable."** No naked cross-era ranking.
- **Career gaps are shown, not interpolated** — Schumacher's 2007–2009 absence
  breaks the line; Alonso's 2019–2020 gap likewise.
- **Hover any season** → that year's rating ± CI, the teammate(s) and races behind
  it, and a thin-evidence flag — every point traceable to its evidence.
- The pre-1994 coverage caveat is carried over: a legend with a short/late arc is a
  **data limit, not a verdict**.

Reads straight from `driver_season_pace_estimate` (separate `model.trajectories`
block; `is_estimate` preserved). Below the arcs sits the Phase-E **career-average
snapshot** for one-number-per-driver context.

# Phase G — era-normalisation via spanning-driver bridges ⚠️ ESTIMATE

Phase F is car-normalised and time-resolved, but its scale is only as trustworthy
as the chain of teammate links tying a given driver-season back to the rest of the
field. A driver who only ever shared a car inside a **weak, locally isolated
cluster** can float to an inflated level on intra-cluster deltas alone — nothing
pulls that cluster onto the cross-era scale. Phase G fixes the **anchoring**, never
the relative structure, and **never assumes an era is strong or weak**: the
cross-era scale is allowed to *emerge* from real overlapping careers.

Run: `python3 pipeline/run_phase_g.py` → **Phase G gate: 14 PASS / 0 FAIL**.

## Method — a spanning backbone + selective shrinkage

- **Spanning backbone.** A driver is a *spanning bridge* if their teammate record
  spans ≥ 10 years **and** touches teammates in ≥ 2 of three era-thirds (boundaries
  at 2003\|2004 and 2013\|2014). **26 such drivers** (Alonso 2001–24, Räikkönen
  2001–21, Schumacher 1994–2012, Coulthard 1994–2008, Webber 2002–13, …). Their
  driver-season nodes form the **backbone**; everyone else is **free**.
- **Effective resistance to the backbone.** On the full Phase-F Laplacian (teammate +
  continuity edges), ground the backbone and read `R_bb = diag((L_ff)⁻¹)`. Small when
  a season is tied to the spine by many short paths; **explodes** when it hangs off
  one thin bridge — or sits in a component the spine never reaches (Marussia 2013–14,
  who only raced each other: `R_bb → ∞`). This is the honest measure of *how
  confidently a season can be placed cross-era*.
- **Spine consensus.** Harmonic extension of the backbone ratings to the free nodes
  (`L_ff μ_f = b_f − L_fb r_backbone`) — "where the real chains, followed back to the
  spine, say this node sits", derived purely from measured deltas.
- **Selective shrinkage (the era-normalisation).** Re-solve with a per-node prior that
  pulls each free node toward its spine consensus with strength `K0·R_bb_i`
  (`K0 = 1`). Well-anchored nodes are left to the data; thinly-bridged pockets are
  pulled onto the spine. This **re-references a pocket's absolute level while
  preserving the within-pocket teammate deltas** (reconstruction unchanged). Gauge:
  mean over the backbone = 0, so the cross-era zero is the empirically-bridged spine,
  not the population mix.
- **Uncertainty.** Cross-era CI = `Z95·σ̂·√(C_ii/σ² + R_bb)` — Phase-F intra-model
  variance **plus** the backbone-anchoring resistance. Thinly-bridged / disconnected
  nodes blow out so wide they make **no cross-era claim**, exactly where the bridges
  run thin. The prior moving a point estimate does **not** shrink its uncertainty.

## Phase G gate (14 PASS / 0 FAIL)

| Check | Result |
|-------|--------|
| **Bridge reality**: 26 spanning drivers; **17** straddle 2003\|2004, **13** straddle 2013\|2014 → **≥13 independent** end-to-end bridges connect 1994–2003 to 2014–2024 | PASS |
| **Selective deflation**: isolated Marussia 2013 (`R_bb→∞`, *unanchored*) — Chilton **+0.562 → +0.289**; **within-pocket Bianchi−Chilton delta preserved exactly (−0.577)** | PASS |
| **Honest Giovinazzi finding**: already anchored by Phase-F continuity (`R_bb=0.013`), so Phase G **barely moves him** (2021 −0.291 → −0.288). The de-inflation happened at F, not here — reported, not faked | PASS |
| **Decline preserved**: prime Räikkönen 2005–07 **−0.114** rates faster than late Alfa 2019–21 **−0.007** | PASS |
| **Uncertainty honesty**: median cross-era CI anchored **±0.534 s** vs thin/unanchored **±1.438 s**; 4 pockets flagged *unanchored* | PASS |
| **Selectivity**: well-bridged core barely moves (Hamilton 2008 Δ +0.001, Alonso 2012 Δ +0.003; max \|Δ\| **0.004 s**) | PASS |
| **Reconstruction**: median \|resid\| **0.056 s** (Phase F 0.057) — re-anchoring did not break the fit | PASS |
| Separation/labelling: `is_estimate=1`, measured Tier-1 deltas untouched | PASS |

**The honest correction in one line:** the spec expected Phase G to *deflate*
Giovinazzi, but the data shows Phase F's continuity prior (via Räikkönen's own
career chain) had **already** anchored him — Phase G confirms he is well-bridged
and correctly leaves him alone. The genuine weak-pocket inflation Phase G fixes is
the backbone-**disconnected** clusters (Marussia 2013–14, mid-90s backmarkers like
Ratzenberger/Gounon/Papis): their floating absolute level is pulled to the spine
consensus *with within-pocket deltas preserved*, and their uncertainty blown out so
they make no cross-era claim.

Artifacts: `driver_season_pace_era_estimate` (766 driver-seasons; era rating +
Phase-F rating on the same backbone gauge + `R_bb` + cross-era CI + anchor flag),
`pace_model_era_residual` (456), `era_bridge_density` (per era boundary). All
`is_estimate=1`, separate from the measured deltas. No UI this phase (combination is
Phase J, presentation Phase K).

# Phase H — the RACECRAFT axis (results-vs-car-strength) ⚠️ CONSTRUCTED ESTIMATE

The pace axes (qualifying = G, race pace = D) measure how **fast** a driver is. They
cannot see Sunday: starts, overtaking, tyre/SC execution, and not binning it. Phase H
isolates exactly that — how well a driver turned the **machinery** into a **result**,
*beyond what their raw pace predicts*. This is where a quick-on-Saturday, poor-on-Sunday
driver is finally separated. It is a **constructed/modelled axis** (more so than pace) —
so the caveats are heavier and the intervals wider.

Run: `python3 pipeline/run_phase_h.py` → **Phase H gate: 13 PASS / 0 FAIL**.

## Method — finishing margin, with pace regressed out

The four traps and how each is avoided:

1. **Circularity** — the car's "deserved" result is never read off the driver's own
   outcome. The independent baseline is the **teammate** (same car): result *relative to
   the teammate* is the car-controlled signal.
2. **Luck ≠ racecraft** — a race counts only when both cars had a *driver-attributable*
   outcome. Status buckets: **CLASSIFIED** (`Finished` / `+N Laps`); **DRIVER_ERROR**
   (`Accident`, `Spun off` — unambiguous solo error, counts as a loss); **EXCLUDED**
   (mechanical DNFs, `Collision`/`Damage`/`Debris` — ambiguous victim/aggressor — DNQ,
   withdrawals). **35 % of all teammate races are dropped** as luck/ambiguous.
3. **Redundancy with pace** — take the head-to-head **finishing-position margin**
   (winsorised ±10) and **regress out both the quali delta and the race-pace delta**
   (one OLS, `margin ≈ 1.23·(−quali) + 1.95·(−racepace)`; pace explains R²=0.31). The
   **residual** — finished better/worse than the pace gap predicts — is the pure
   racecraft signal, orthogonal to both pace axes by construction.
4. **Era-incomparable points** — everything is in **finishing positions vs the
   teammate**, never championship points.

**Driver-level network** (racecraft is sparse → career nodes): one edge per pair-season
with target = racecraft residual, weight = #eligible races; solve the weighted
Laplacian → career racecraft rating in *"positions better than pace predicts."*
**Era-normalised** with the Phase-G spanning-bridge machinery (25 bridges; racecraft
lives in the lap-timing era ~1996+, so "cross-era" means across that window):
effective resistance to the backbone shrinks poorly-anchored drivers toward the spine
and blows out their cross-era uncertainty.

## Phase H gate (13 PASS / 0 FAIL)

| Check | Result |
|-------|--------|
| **Orthogonality**: career racecraft vs era pace **r = +0.079** (edge residual vs both pace deltas r = 0.000 by construction). *Same pace, different racecraft*: Fisichella **+0.44** vs Grosjean **−1.32** (Δpace ≈ 0.01 s) | PASS |
| **Anchor sanity**: renowned racers positive — Alonso **+1.56**, Verstappen **+1.66**, Ricciardo **+1.01**; crash-prone Grosjean **−1.32** (the "not-crashing" signal); Alonso − Grosjean = **+2.88 pos** | PASS |
| **The Giovinazzi check**: racecraft **−1.83 ± 1.87** — negative, converted worse than his pace predicted (consistent with the thesis); reported as-is, wide interval flagged | PASS |
| **Luck-exclusion** (worked): Prost 2000 Heidfeld vs Alesi — **2 eligible / 14 dropped**; 35 % of all teammate races excluded | PASS |
| **Reconstruction**: median \|resid\| **0.758 pos** (< 1.5) | PASS |
| **Uncertainty honesty**: anchored ±**1.03** pos vs thin/unanchored ±**3.96** pos; intervals honestly wide throughout (constructed axis) | PASS |
| Separation/labelling: `is_estimate=1`, measured results untouched | PASS |

**What the axis catches that pace can't:** Grosjean and Fisichella sit at essentially
the same era pace, but Grosjean's crash-prone Sundays drop him ~1.8 positions below
where his pace would land him while Fisichella sits above — a separation invisible to
the pace axes. The crash-prone tail (Grosjean) and the elite-racer head (Alonso,
Verstappen, Ricciardo) emerge from the residual alone.

**Honest limits (constructed axis):** racecraft needs Phase-D race-pace, which needs
lap timing (~1996+), so the axis is **modern-era only** and "cross-era" is within that
window. Intervals are wide (anchored ±1 pos; most drivers wider) — a single season vs
one teammate is a noisy read of Sunday craft, and the model says so. `Collision` is
treated as ambiguous and excluded, so genuinely-aggressive-but-clean overtaking that
ended in a racing incident is neither rewarded nor punished.

Artifacts: `driver_racecraft_estimate` (130 drivers; rating + `R_bb` + CI + #edges +
#races + anchor flag), `racecraft_pair_residual` (347 pair-seasons; margin, pace
prediction, luck drops — full audit trail), `racecraft_recon_residual`,
`racecraft_meta` (pace coefficients, R², orthogonality). All `is_estimate=1`, separate
from measured results. No UI this phase (combination = Phase J, presentation = Phase K).

# Phase I — the LONGEVITY / sustained-level axis ⚠️ CONSTRUCTED ESTIMATE

Pace (G) says how *fast*; racecraft (H) says how well they *converted* it. Neither sees
**durability** — staying at a competitive level season after season, adapting as the
sport changes. Phase I measures that, and only that. **Constructed axis** — heavy
caveats, honest intervals.

Run: `python3 pipeline/run_phase_i.py` → **Phase I gate: 13 PASS / 0 FAIL**.

## Method — effective competitive seasons

For each driver-season with a Phase-G era pace rating `r` (lower = faster):

```
competitiveness = σ((C0 − r)/KW)        # logistic, saturating in [0,1]; C0=0.30, KW=0.25
   r≈−0.2 (above backbone) → 0.87  near the front: counts fully
   r≈+0.1 (grid median)    → 0.68  midfield: counts substantially
   r≈+0.8 (back of grid)   → 0.10  backmarker: counts little
presence = min(1, starts / races_in_season)   # partial/reserve year counts partially
LONGEVITY = Σ presence · competitiveness        # "effective competitive seasons"
```

The three traps, avoided:
- **Raw length rewards mediocrity** — years aren't counted; a season counts only insofar
  as the driver was competitive. (Coulthard, 15 seasons → ranks **#18**, not top-10; by
  raw length he'd be **#8**.)
- **Over-adjustment kills orthogonality** — the weight **saturates**, so elite and merely-strong
  seasons both count ~fully; what survives is *duration at a competitive level*, not pace
  again. (corr with pace **+0.49**, not 1.)
- **Brevity ≠ badness** — a brief-but-strong career scores **moderate**, never bottom, and
  low longevity means *"didn't sustain"*, not *"wasn't good"* (ability lives in G/H).
  (Leclerc, 7 strong seasons → **6.5**, rivalling Coulthard's 15 weaker ones at 7.9.)

**Uncertainty** has two honest sources, added in quadrature: *statistical* (propagate each
season's G interval through the weight) and *construction* (recompute across a grid of
(C0, KW) and take the spread — a constructed axis should wear its arbitrariness). Active
drivers are flagged: their longevity is *"so far."*

## Phase I gate (13 PASS / 0 FAIL)

| Check | Result |
|-------|--------|
| **Top is long-AND-competitive**: Alonso **18.9**, Hamilton **16.0**, Barrichello 15.2, Schumacher 14.3, Räikkönen 14.2 — the four long-elite all top-8 | PASS |
| **Mediocrity avoided**: Coulthard (15 seasons) ranks **#18** (raw-length #8); weak seasons discounted | PASS |
| **Brevity ≠ badness**: Leclerc (7 strong seasons) **6.5**, above median, rivals Coulthard's 15-season 7.9 | PASS |
| **Orthogonality**: corr with pace G **+0.49**, with racecraft H **+0.16** — adds the duration dimension, not redundant | PASS |
| **The Giovinazzi check**: 4 seasons, **L=2.6** — among genuine careers (≥4 seasons) he's **#47/63, bottom 25%**, well below the group median 4.9 (short AND uncompetitive) | PASS |
| **Uncertainty**: Hamilton 16.0 ± 1.5 (construction band [14.5, 16.9]); 24 active drivers flagged; genuine careers all carry populated intervals | PASS |
| Separation/labelling: `is_estimate=1`, measured results untouched | PASS |

**The honest reference-set note:** Giovinazzi sits #47 of *all* 172 only because half the
field are one-race cameos who sustained even less; against the **63 drivers with real
careers (≥4 seasons)** he is firmly bottom-quartile — which is the fair read of "short and
uncompetitive." (The gate originally compared him to all 172 and *failed*; the catch was
the gate's, and the fix was the reference population, not the model.)

**Honest limits (constructed axis):** Phase-G pace exists only where qualifying timing does
(**1994+**), so longevity is a **modern-era axis** — pre-1994 greats are out of scope.
"Effective competitive seasons" is a model construct, not a record; the construction band
shows how much it moves under different weightings. Low longevity is **never** a verdict on
ability — Kubica (injury-curtailed) and Leclerc (mid-career) score modestly because they
*haven't sustained a long career*, not because they lacked pace.

Artifacts: `driver_longevity_estimate` (172 drivers; longevity + statistical CI +
construction band + mean competitiveness + active flag), `longevity_season_weight` (766
driver-seasons; the per-season presence × competitiveness audit trail). All
`is_estimate=1`, separate from measured results. No UI this phase (combination = Phase J,
presentation = Phase K).

# Phase J — combination + USER-WEIGHTING ⚠️ ESTIMATE · interactive

The three axes are measured honestly and **orthogonally** — pace (G), racecraft (H),
longevity (I). Phase J combines them into a composite **without asserting a single
weighting**. The whole model's defensibility rests here: *the model measures the axes;
the **user** decides how much each counts.* There is no official ranking — the composite
is a function of user-set weights, and the equal default is an arbitrary starting point,
explicitly not a claim.

Run: `python3 pipeline/run_phase_j.py` → **Phase J gate: 13 PASS / 0 FAIL**. The
interactive view ships this phase at **`#/quality`** (regenerate `web/data.js` with
`python3 pipeline/export_web.py`).

## Method — normalise, then weight (live)

- **Reference population** — the **63 genuine careers** (≥4 seasons, all three axes) of the
  1994+ era. Cameos would distort the spread, so they are excluded from the normalisation.
- **Normalise** — each axis is **z-scored** against that population (mean 0, sd 1), oriented
  so higher = better. Career pace = inverse-variance weighted mean of a driver's Phase-G
  season ratings.
- **Composite** — `composite = w_pace·z_pace + w_race·z_race + w_long·z_long`, weights
  user-set and renormalised to sum 1. Default **equal** (labelled arbitrary).
- **Uncertainty propagates** — each axis CI goes onto the z scale; the axes are orthogonal,
  so `σ_composite = √Σ(w·σ_z)²`. Overlapping composite intervals read as **"not confidently
  separable"** — the list marks adjacent ties (≈) and a **Compare** tool gives an explicit
  tie/separable verdict for any pair.
- **Coverage** — a full composite needs all three axes **and** a genuine career; everyone
  else is flagged **partial** (missing axis named), never zero-filled or silently dropped.

## Phase J gate (13 PASS / 0 FAIL)

| Check | Result |
|-------|--------|
| **No fixed weighting**: balanced / pace-heavy / racecraft-heavy give **different** top-10s (Δ 2 and 10 members) — the composite genuinely responds to the user | PASS |
| **THE GIOVINAZZI TEST**: rank of 63 — **pace-ONLY #14**, **balanced #47**, **racecraft-heavy #56**. Pure pace flatters him; the full picture sinks him. *"Decent qualifier, little else"* — shown by the weighting, not asserted | PASS |
| **Uncertainty**: under racecraft-heavy, high-CI Alesi (+2.01 ±1.93) floats to nominal #1 but its interval overlaps **49** drivers → not separable; balanced #1/#2 (Alonso/Schumacher) overlap and are marked tied | PASS |
| **Sanity**: balanced top-8 = Alonso, Schumacher, Hamilton, Verstappen, Barrichello, Leclerc, Sainz, Button — all four of {Alonso, Hamilton, Schumacher, Verstappen} present, median CI ±0.28 (not uncertainty artifacts) | PASS |
| **Coverage**: 109 partial drivers flagged & excluded (not zero-filled); every partial names its missing axis | PASS |
| **Transparency**: every composite decomposes into its three axis z-scores (no black box); `is_estimate=1` | PASS |

**The thesis in one line:** weight pace alone and Giovinazzi is a respectable #14; add the
racecraft and longevity the model also measures, and he falls to #47 → #56. The full
picture sinks him — *exactly what the three-axis model was built to show* — and it does so
by your own weighting, not ours.

**The interactive view (`#/quality`).** Three sliders (pace · racecraft · longevity) recompute
the ranking live; presets (equal / pace-only / racecraft-led / longevity-led) jump to corners.
Every row shows its composite 95% interval **and** its three axis z-scores (always
decomposable). Adjacent statistical ties are marked **≈** — under balanced weighting almost
every neighbour is a tie, which is the honest result; the **Compare** tool resolves any
specific pair (e.g. Alonso vs Giovinazzi → *clearly separable, gap 2.24*; Alonso vs
Schumacher → *statistical tie*). A partial-coverage panel lists who's excluded and why.

**Honesty caveats carried through:** the composite is an **estimate** built on estimates; it
covers only the 1994+ all-three-axis careers; longevity is the softest axis and may be
weighted to **zero**; and a high rank with a wide interval is *not* a confident claim — the
view says so. *(The combination logic is validated in Python; the live in-browser render
wants an eyeball.)*

Artifacts: `driver_quality_axes` (172 drivers; raw + z-scored axes + z-scale CIs + coverage
flags), `quality_norm_meta` (per-axis reference mean/std/population). Web: `quality` block in
`web/data.js`. All `is_estimate=1`. Full radar/profile polish is **Phase K**.

# Phase K — interval-aware refinement, within-era mode, radar profiles ⚠️ ESTIMATE · interactive

Phase K closes the model. A diagnostic found the composite skewed toward modern drivers;
the investigation (reported in full before any change) showed it was **mostly real signal**
— 1990s grids were genuinely more spread out (**field compression**: ~1.5–2 s teammate
gaps then vs ~0.3 s now), carried faithfully through the era-normalised pace — **plus** one
genuine defect: thin-data early-era racecraft (intervals ~2× wider) counted **noisy point
estimates at full weight**. Phase K fixes the defect without erasing the real gradient, adds
a within-era option, surfaces the era trend, and ships the radar.

Run: `python3 pipeline/run_phase_k.py` → **Phase J gate 13/13 + Phase K gate 10/10**.

## A — interval-aware shrinkage (empirical Bayes), the new baseline

Each axis estimate `z` carries measurement noise `σ_z`. Model `z = θ + ε`,
`ε ~ N(0, σ_z²)`, `θ ~ N(0, τ²)`; estimate `τ² = Var(z) − mean(σ_z²)` per axis, then

```
z_shrunk = z · τ²/(τ²+σ_z²)          (toward 0 = neutral)
σ_shrunk = √( τ²·σ_z²/(τ²+σ_z²) )    (tighter posterior → tighter composite CI)
```

`τ²`: **pace 0.88, racecraft 0.34, longevity 0.97**. So racecraft (the noisy axis) shrinks
hard (mean factor **0.48**, noisy ones to 0.08); **pace barely moves (0.89), longevity barely
(0.97)** — the real field-compression pace gradient is **preserved**. It is **era-neutral by
construction** (shrinkage depends only on each driver's interval): risers *and* fallers are
both early-era — **Hill #38→#31, Coulthard #42→#35** (noisy-negative lifted) vs **Berger
#33→#53, Alesi #20→#42** (noisy-positive racecraft deflated, killing the old racecraft-heavy
artifact). Era cohort means barely move (**−0.38/+0.06/+0.31 → −0.25/+0.11/+0.23**, still
monotonic) — a noise-reduction, *not* an era-adjustment.

> **A self-caught correction:** the original prototype under-shrank — it treated the exported
> z-scale *sigma* as a 95% *halfwidth* and divided by Z95 again, shrinking ~3.8× too little.
> The pipeline computes it correctly from raw units; the real effect is stronger (racecraft
> factor 0.48, not 0.85), and *better* — the Giovinazzi thesis still holds and racecraft-heavy
> no longer crowns high-variance artifacts.

## B — within-era / cross-era toggle (you decide)

- **Cross-era (default)** — z-score against one cross-era spine; **keeps** the field-compression
  gradient. "How far from the all-time spine."
- **Within-era** — z-score within the driver's era-third (1994-2003 / 2004-2013 / 2014-2024);
  **flattens** each era's mean to 0. "Standing among contemporaries." It *assumes* equal era
  depth, so it's offered as an explicit choice, never the silent default.

## C — per-era readout

A live strip shows the **mean composite per era** under the current weights+mode — so the
field-compression effect is **visible, not hidden** (cross: −0.25 / +0.11 / +0.23, the modern
tilt; within: ≈ 0 / 0 / 0). Updates with every slider and toggle.

## Radar profiles + polish

Each driver is a **three-axis shape** (pace top, racecraft lower-right, longevity lower-left;
rings at z = −1…+2, the z = 0 spine dashed). The Compare panel **overlays two radars** (violet
vs cyan) so quality *shapes* sit side by side — a spiky triangle (great at one axis) vs a big
balanced one. **Click any ranked row** to load its radar and verdict.

## Phase K gate (10 PASS / 0 FAIL) — plus Phase J gate still 13/13

| Check | Result |
|-------|--------|
| Shrinkage targets the noisy axis: racecraft factor **0.48** vs pace **0.89**, longevity **0.97** | PASS |
| Field-compression gradient **survives** shrink (Δ era means +0.48, still monotonic) | PASS |
| **Era-neutral**: risers (Hill, Coulthard) AND fallers (Alesi, Berger) both 1994-2003 | PASS |
| Within-era flattens every cohort mean to ≈ 0 (max \|mean\| 0.06) | PASS |
| Hill rises **#38→#31** (legitimate) while Alonso/Hamilton/Schumacher move **0** places | PASS |
| EB posterior intervals tighten (median composite CI ±0.47 → **±0.36**) | PASS |
| Every driver decomposable in both modes (radar well-defined); `is_estimate=1` | PASS |

**Giovinazzi thesis, post-shrinkage:** pace-only **#16** → balanced **#41** → racecraft-heavy
**#56** of 63 — still the whole story (pace flatters, the full picture sinks him). He rises a
little vs the unshrunk #47 because his *thin-data* racecraft is pulled toward neutral — the
**same honest rule that lifts Hill**, applied without looking at who it is.

The model is **complete**: three orthogonally-measured, era-normalised axes → an
interval-aware, user-weighted composite that asserts no single ranking, carries its
uncertainty as the hero, shows ties as ties, and stays decomposable to the last pixel.
Everything is an estimate; nothing is overclaimed.

Artifacts: `driver_quality_axes` extended (cohort + cross/within shrunk z & σ),
`quality_norm_meta` (per-mode/axis τ²). Web: `#/quality` view (sliders · mode toggle · per-era
readout · radar · Compare). All `is_estimate=1`.

