"""Phase D — PACE & DELTAS foundation.

Tenths-level pace measurement on the real lap-time and qualifying data. PURE
MEASUREMENT — no modelling, no car-normalisation (that is Phase E). The guiding
principle: compute a delta only where the comparison is genuinely clean, and tag
every delta with a COMPARABILITY TIER so nothing later reads as more precise than
it is.

  TIER 1  same session / track / car         -> teammate qualifying delta (cleanest)
  TIER 2  same race / car, clean-lap method   -> teammate race-pace delta (caveated)
  TIER 3  cross-era / cross-context           -> pole & fastest-lap facts (contextual only)

Artifacts (all written to data/parquet/ and DuckDB):
  quali_teammate_delta_race        per (pair, race): common-session gap (s)
  quali_teammate_delta_pairseason  per (season, constructor, pair): robust mean/median/std
  quali_teammate_delta_career      per driver: pooled delta vs all teammates
  racepace_teammate_race           per (pair, race): clean-lap pace delta (s/lap) + reliability
  racepace_teammate_pairseason     per (season, constructor, pair): aggregate over reliable races
  event_pace                       per race: pole time + fastest race lap (TIER 3 facts)
  circuit_layout                   per circuit: layout-stability note + heuristic discontinuity flag

================================ METHODS (exact) ==============================

QUALIFYING DELTA (Tier 1)
  * Times parsed "M:SS.mmm" -> seconds; '' and \\N -> null.
  * Comparison basis = the DEEPEST qualifying session BOTH drivers set a time in
    (Q3 if both reached it, else Q2, else Q1) — strictly like-for-like (same
    session, same track evolution window). gap = A_time - B_time in that session,
    with the pair ordered driverA < driverB; negative => A faster.
  * A race has NO comparison if there is no common timed session (counted as
    `no_common_session`).
  * NON-REPRESENTATIVE filter (non-pace events: crash / mechanical / aborted /
    limited running): a comparison with |gap| > 3.0 s is flagged and EXCLUDED from
    the pace statistics (teammate qualifying pace gaps essentially never exceed
    ~1.5 s). Counted as `flagged_incident`.
  * Robust aggregation: median is the primary statistic (incident-insensitive);
    mean/std are computed after an additional within-pair MAD fence
    (keep gaps within median +/- 3 * 1.4826 * MAD, scale floored at 0.25 s) so a
    residual anomaly cannot distort the mean. Sample size and the spread are
    always reported. 1994+ only (qualifying-table coverage).

RACE-PACE DELTA (Tier 2)  — clean green-flag laps, NOT a naive mean
  * From lap_times.milliseconds. For a race we exclude, for every driver:
      - lap 1 (standing-start);
      - SAFETY-CAR / VSC / disrupted laps: a lap L whose FIELD-MEDIAN lap time
        exceeds 1.15 x the race baseline (baseline = median of field-median lap
        times over L>=2). Excluded field-wide.
      - PIT in-laps and out-laps: {pit_lap, pit_lap+1} from pit_stops (2011+;
        earlier races fall back to the outlier step below);
      - per-driver OUTLIERS: laps slower than median + 3*1.4826*MAD, or slower
        than 1.30 x the driver's own median (traffic / mistakes / residual pit).
  * Pace = MEDIAN of a driver's remaining clean laps. delta = A_median - B_median
    (s/lap), pair ordered A < B; negative => A faster.
  * RELIABILITY tag = 'low' (with reasons) if any of: fewer than 8 clean laps for
    either driver; either classified with < 90% of race distance (early DNF /
    heavily delayed); safety-car laps > 30% of the race; pit-stop count differs by
    >= 2 (very different strategy, 2011+); clean-lap counts imbalanced (smaller <
    40% of larger). Otherwise 'ok'. Only 'ok' races feed the pair-season aggregate;
    'low' races are kept but counted separately.

POLE & FASTEST LAP (Tier 3)
  * Per race: pole time = the polesitter's best session time; fastest race lap =
    min lap_times.milliseconds. These are per-event FACTS. Cross-era / cross-circuit
    comparison is Tier 3 (contextual only): circuit layout/length history is NOT in
    the dataset, so layout-stability is 'undetermined'; a heuristic flags year-on-year
    pole jumps > 4% as a possible layout/regulation change (not ground truth).
"""
import statistics as st
from collections import defaultdict
from common import connect, PARQUET

# ----- robust helpers --------------------------------------------------------
def _median(x):
    return st.median(x)

def _mad(x):
    m = _median(x)
    return _median([abs(v - m) for v in x])

INCIDENT_CAP = 3.0      # |quali gap| beyond this s = non-pace incident
MAD_K = 3.0
MAD_FLOOR = 0.25
SC_RATIO = 1.15         # field-median lap > this * baseline => safety car / disrupted
OUTLIER_CAP = 1.30      # lap slower than this * driver median => excluded
MIN_CLEAN = 8           # fewer clean laps than this => low reliability
SC_FRACTION_MAX = 0.30
RACE_DISTANCE_MIN = 0.90


# ============================================================================
# 1. QUALIFYING DELTAS  (Tier 1)
# ============================================================================
def build_quali(con):
    con.execute(r"""CREATE OR REPLACE MACRO t2s(t) AS (
        CASE WHEN t IS NULL OR t='' THEN NULL
             WHEN strpos(t,':')>0 THEN CAST(split_part(t,':',1) AS DOUBLE)*60
                                       + CAST(split_part(t,':',2) AS DOUBLE)
             ELSE TRY_CAST(t AS DOUBLE) END)""")
    # per teammate pair per race: deepest common session gap (A<B by driverId)
    rows = con.execute("""
        WITH qs AS (
            SELECT ra.season, ra.round, q.raceId, q.constructorId, q.driverId,
                   t2s(q.q1) q1, t2s(q.q2) q2, t2s(q.q3) q3
            FROM qualifying q JOIN fact_races ra USING (raceId)
        )
        SELECT a.season, a.constructorId, a.driverId AS dA, b.driverId AS dB,
               a.raceId, a.round,
               CASE WHEN a.q3 IS NOT NULL AND b.q3 IS NOT NULL THEN 'Q3'
                    WHEN a.q2 IS NOT NULL AND b.q2 IS NOT NULL THEN 'Q2'
                    WHEN a.q1 IS NOT NULL AND b.q1 IS NOT NULL THEN 'Q1' END AS sess,
               CASE WHEN a.q3 IS NOT NULL AND b.q3 IS NOT NULL THEN a.q3-b.q3
                    WHEN a.q2 IS NOT NULL AND b.q2 IS NOT NULL THEN a.q2-b.q2
                    WHEN a.q1 IS NOT NULL AND b.q1 IS NOT NULL THEN a.q1-b.q1 END AS gap
        FROM qs a JOIN qs b
          ON a.raceId=b.raceId AND a.constructorId=b.constructorId AND a.driverId < b.driverId
    """).fetchall()

    race_rows, pair = [], defaultdict(list)
    for season, cid, dA, dB, raceId, rnd, sess, gap in rows:
        status = ("no_common_session" if gap is None
                  else "flagged_incident" if abs(gap) > INCIDENT_CAP else "valid")
        race_rows.append((season, cid, dA, dB, raceId, rnd, sess, gap, status, 1))
        if status != "no_common_session":
            pair[(season, cid, dA, dB)].append((gap, status))

    con.execute("""CREATE OR REPLACE TABLE quali_teammate_delta_race (
        season INT, constructorId INT, driverA INT, driverB INT, raceId INT, round INT,
        session_basis VARCHAR, gap_s DOUBLE, status VARCHAR, tier INT)""")
    con.executemany("INSERT INTO quali_teammate_delta_race VALUES (?,?,?,?,?,?,?,?,?,?)", race_rows)

    ps_rows = []
    career = defaultdict(list)   # driverId -> list of signed gaps (driver perspective, neg=faster)
    for (season, cid, dA, dB), vals in pair.items():
        valid = [g for g, s in vals if s == "valid"]
        n_incident = sum(1 for g, s in vals if s == "flagged_incident")
        if not valid:
            continue
        m = _median(valid)
        scale = max(1.4826 * _mad(valid), MAD_FLOOR)
        incl = [g for g in valid if m - MAD_K * scale <= g <= m + MAD_K * scale]
        n_madtrim = len(valid) - len(incl)
        sign_a = sum(1 for g in valid if g < 0)
        ps_rows.append((season, cid, dA, dB, len(incl),
                        round(st.mean(incl), 4), round(_median(incl), 4),
                        round(st.pstdev(incl) if len(incl) > 1 else 0.0, 4),
                        n_incident, n_madtrim, sign_a, len(valid), 1))
        for g in valid:
            career[dA].append(g)        # A perspective: neg => A faster
            career[dB].append(-g)       # B perspective

    con.execute("""CREATE OR REPLACE TABLE quali_teammate_delta_pairseason (
        season INT, constructorId INT, driverA INT, driverB INT, n_included INT,
        mean_gap_s DOUBLE, median_gap_s DOUBLE, std_s DOUBLE, n_incident INT,
        n_madtrim INT, a_faster_races INT, n_valid INT, tier INT)""")
    con.executemany("INSERT INTO quali_teammate_delta_pairseason VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ps_rows)

    car_rows = []
    for d, gaps in career.items():
        car_rows.append((d, len(gaps), round(st.mean(gaps), 4), round(_median(gaps), 4),
                         round(st.pstdev(gaps) if len(gaps) > 1 else 0.0, 4), 1))
    con.execute("""CREATE OR REPLACE TABLE quali_teammate_delta_career (
        driverId INT, n_races INT, mean_gap_s DOUBLE, median_gap_s DOUBLE, std_s DOUBLE, tier INT)""")
    con.executemany("INSERT INTO quali_teammate_delta_career VALUES (?,?,?,?,?,?)", car_rows)
    return len(race_rows), len(ps_rows), len(car_rows)


# ============================================================================
# 2. RACE-PACE DELTAS  (Tier 2)
# ============================================================================
def _driver_clean_laps(byd, sc, pitlaps):
    cand = {L: ms for L, ms in byd.items() if L >= 2 and L not in sc and L not in pitlaps}
    if len(cand) < 3:
        return None
    vals = list(cand.values())
    m = _median(vals)
    scale = 1.4826 * _mad(vals) or 1.0
    clean = [ms for ms in vals if ms <= m + 3 * scale and ms <= OUTLIER_CAP * m]
    return clean


def build_racepace(con):
    # load everything once
    laps = con.execute("""
        SELECT ra.season, ra.round, lt.raceId, lt.driverId, lt.lap, lt.milliseconds
        FROM lap_times lt JOIN fact_races ra USING (raceId)
    """).fetchall()
    race_laps = defaultdict(lambda: defaultdict(dict))      # raceId -> driver -> lap -> ms
    race_meta = {}
    for season, rnd, raceId, d, lap, ms in laps:
        race_laps[raceId][d][lap] = ms
        race_meta[raceId] = (season, rnd)

    pit = defaultdict(lambda: defaultdict(set))             # raceId -> driver -> {pit in/out laps}
    for raceId, d, lap in con.execute("SELECT raceId, driverId, lap FROM pit_stops").fetchall():
        pit[raceId][d].add(lap); pit[raceId][d].add(lap + 1)
    pit_count = defaultdict(lambda: defaultdict(int))
    for raceId, d, c in con.execute("SELECT raceId, driverId, count(*) FROM pit_stops GROUP BY 1,2").fetchall():
        pit_count[raceId][d] = c

    # completed laps + constructor per (race, driver)
    comp = {}
    for raceId, d, cid, laps_done in con.execute(
            "SELECT raceId, driverId, constructorId, CAST(laps AS INT) FROM results").fetchall():
        comp[(raceId, d)] = (cid, laps_done)

    # teammate pairs per race that both have lap data
    pairs_by_race = defaultdict(list)
    bycon = defaultdict(lambda: defaultdict(list))          # raceId -> cid -> [drivers with laps]
    for raceId in race_laps:
        for d in race_laps[raceId]:
            meta = comp.get((raceId, d))
            if meta:
                bycon[raceId][meta[0]].append(d)
    for raceId, cons in bycon.items():
        for cid, drivers in cons.items():
            drivers = sorted(drivers)
            for i in range(len(drivers)):
                for j in range(i + 1, len(drivers)):
                    pairs_by_race[raceId].append((cid, drivers[i], drivers[j]))

    race_rows = []
    agg = defaultdict(lambda: {"ok": [], "low": 0})
    for raceId, plist in pairs_by_race.items():
        season, rnd = race_meta[raceId]
        bylap = defaultdict(list)
        for d, lp in race_laps[raceId].items():
            for L, ms in lp.items():
                bylap[L].append(ms)
        total = max(bylap)
        field_med = {L: _median(v) for L, v in bylap.items()}
        green = [field_med[L] for L in field_med if L >= 2]
        if total < 2 or not green:          # red-flagged after a lap etc. — no green pace
            for cid, A, B in plist:
                race_rows.append((season, cid, A, B, raceId, rnd, None, 0, 0,
                                  0.0, "low", "no_green_laps", 2))
                agg[(season, cid, A, B)]["low"] += 1
            continue
        base = _median(green)
        sc = {L for L in field_med if L >= 2 and field_med[L] > SC_RATIO * base}
        sc_frac = len(sc) / total

        for cid, A, B in plist:
            ca = _driver_clean_laps(race_laps[raceId][A], sc, pit[raceId][A])
            cb = _driver_clean_laps(race_laps[raceId][B], sc, pit[raceId][B])
            if not ca or not cb:
                race_rows.append((season, cid, A, B, raceId, rnd, None,
                                  len(ca) if ca else 0, len(cb) if cb else 0,
                                  round(sc_frac, 3), "low", "insufficient_clean_laps", 2))
                agg[(season, cid, A, B)]["low"] += 1
                continue
            delta = (_median(ca) - _median(cb)) / 1000.0
            na, nb = len(ca), len(cb)
            la = comp[(raceId, A)][1] or 0
            lb = comp[(raceId, B)][1] or 0
            reasons = []
            if min(na, nb) < MIN_CLEAN: reasons.append("few_clean_laps")
            if min(la, lb) < RACE_DISTANCE_MIN * total: reasons.append("dnf_or_delayed")
            if sc_frac > SC_FRACTION_MAX: reasons.append("safety_car_heavy")
            if abs(pit_count[raceId].get(A, 0) - pit_count[raceId].get(B, 0)) >= 2: reasons.append("strategy_divergence")
            if min(na, nb) < 0.4 * max(na, nb): reasons.append("clean_lap_imbalance")
            rel = "low" if reasons else "ok"
            race_rows.append((season, cid, A, B, raceId, rnd, round(delta, 4),
                              na, nb, round(sc_frac, 3), rel, ",".join(reasons), 2))
            if rel == "ok":
                agg[(season, cid, A, B)]["ok"].append(delta)
            else:
                agg[(season, cid, A, B)]["low"] += 1

    con.execute("""CREATE OR REPLACE TABLE racepace_teammate_race (
        season INT, constructorId INT, driverA INT, driverB INT, raceId INT, round INT,
        delta_s_per_lap DOUBLE, clean_laps_a INT, clean_laps_b INT, sc_fraction DOUBLE,
        reliability VARCHAR, reasons VARCHAR, tier INT)""")
    con.executemany("INSERT INTO racepace_teammate_race VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", race_rows)

    ps_rows = []
    for (season, cid, A, B), v in agg.items():
        ok = v["ok"]
        ps_rows.append((season, cid, A, B, len(ok),
                        round(st.mean(ok), 4) if ok else None,
                        round(_median(ok), 4) if ok else None,
                        round(st.pstdev(ok), 4) if len(ok) > 1 else 0.0,
                        v["low"], 2))
    con.execute("""CREATE OR REPLACE TABLE racepace_teammate_pairseason (
        season INT, constructorId INT, driverA INT, driverB INT, n_ok_races INT,
        mean_delta_s DOUBLE, median_delta_s DOUBLE, std_s DOUBLE, n_low_races INT, tier INT)""")
    con.executemany("INSERT INTO racepace_teammate_pairseason VALUES (?,?,?,?,?,?,?,?,?,?)", ps_rows)
    return len(race_rows), len(ps_rows)


# ============================================================================
# 3. POLE & FASTEST LAP  (Tier 3 facts)
# ============================================================================
def build_event_pace(con):
    con.execute("""
        CREATE OR REPLACE TABLE event_pace AS
        WITH pole AS (
            SELECT q.raceId, min(least(coalesce(t2s(q.q3), 1e9), coalesce(t2s(q.q2), 1e9),
                                        coalesce(t2s(q.q1), 1e9))) AS pole_s
            FROM qualifying q WHERE CAST(q.position AS INT)=1 GROUP BY q.raceId
        ),
        fl AS (
            SELECT raceId, min(milliseconds)/1000.0 AS fastest_lap_s FROM lap_times GROUP BY raceId
        )
        SELECT ra.raceId, ra.season, ra.round, ra.circuitId, ra.race_name,
               CASE WHEN p.pole_s >= 1e8 THEN NULL ELSE p.pole_s END AS pole_s,
               fl.fastest_lap_s,
               3 AS tier
        FROM fact_races ra
        LEFT JOIN pole p USING (raceId)
        LEFT JOIN fl USING (raceId)
        ORDER BY ra.season, ra.round
    """)
    # circuit-level layout note + heuristic discontinuity flag (NOT ground truth)
    con.execute("""
        CREATE OR REPLACE TABLE circuit_layout AS
        WITH seq AS (
            SELECT circuitId, season, min(pole_s) pole_s
            FROM event_pace WHERE pole_s IS NOT NULL GROUP BY circuitId, season
        ),
        jumps AS (
            SELECT circuitId, season, pole_s,
                   abs(pole_s - lag(pole_s) OVER (PARTITION BY circuitId ORDER BY season))
                     / lag(pole_s) OVER (PARTITION BY circuitId ORDER BY season) AS yoy
            FROM seq
        )
        SELECT c.circuitId, c.circuit_name,
               count(DISTINCT j.season) AS seasons_with_pole,
               coalesce(max(CASE WHEN j.yoy > 0.04 THEN 1 ELSE 0 END), 0) = 1 AS has_discontinuity,
               'undetermined (layout history not in dataset)' AS layout_stability
        FROM dim_circuits c LEFT JOIN jumps j USING (circuitId)
        GROUP BY c.circuitId, c.circuit_name
    """)
    n_ev = con.execute("SELECT count(*) FROM event_pace").fetchone()[0]
    n_ci = con.execute("SELECT count(*) FROM circuit_layout").fetchone()[0]
    return n_ev, n_ci


def main():
    con = connect()
    print("=" * 78)
    print("PHASE D — PACE & DELTAS")
    print("=" * 78)
    nq = build_quali(con)
    print(f"  Tier 1 quali:    {nq[0]:,} race comparisons, {nq[1]:,} pair-seasons, {nq[2]:,} driver careers")
    nr = build_racepace(con)
    print(f"  Tier 2 racepace: {nr[0]:,} race comparisons, {nr[1]:,} pair-seasons")
    ne = build_event_pace(con)
    print(f"  Tier 3 event:    {ne[0]:,} events (pole+FL), {ne[1]:,} circuits")

    tables = ["quali_teammate_delta_race", "quali_teammate_delta_pairseason",
              "quali_teammate_delta_career", "racepace_teammate_race",
              "racepace_teammate_pairseason", "event_pace", "circuit_layout"]
    for t in tables:
        out = PARQUET / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{out}' (FORMAT PARQUET)")

    # comparability-tier distribution
    print("\n  COMPARABILITY-TIER DISTRIBUTION")
    t1 = con.execute("SELECT count(*) FROM quali_teammate_delta_race WHERE status<>'no_common_session'").fetchone()[0]
    t1v = con.execute("SELECT count(*) FROM quali_teammate_delta_race WHERE status='valid'").fetchone()[0]
    t2ok = con.execute("SELECT count(*) FROM racepace_teammate_race WHERE reliability='ok'").fetchone()[0]
    t2low = con.execute("SELECT count(*) FROM racepace_teammate_race WHERE reliability='low'").fetchone()[0]
    t3 = con.execute("SELECT count(*) FROM event_pace WHERE pole_s IS NOT NULL OR fastest_lap_s IS NOT NULL").fetchone()[0]
    print(f"    TIER 1 (quali, same session):     {t1:,} comparisons ({t1v:,} valid / {t1-t1v:,} incident-or-flagged)")
    print(f"    TIER 2 (race pace, clean-lap):    {t2ok+t2low:,} comparisons ({t2ok:,} ok / {t2low:,} low-reliability)")
    print(f"    TIER 3 (pole/FL, cross-era facts): {t3:,} events (contextual only)")
    con.close()
    print("\nPHASE D: done.")


if __name__ == "__main__":
    main()
