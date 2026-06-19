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

