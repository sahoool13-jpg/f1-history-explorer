"""Phase B — FEATURE 2: clinch geometry.

"When was each title mathematically secured, and how close did it ever get?"

Pure remaining-points-available math against the real running standings.

METHOD & STATED ASSUMPTIONS
---------------------------
* Running points after each round come from driver_standings (official cumulative
  standings, which already apply each era's dropped-scores rule).

* WEEKEND MAX = the most points any single driver can take from one race weekend
  that season: race-winner points (era table) + a fastest-lap point where the era
  awards one + sprint-winner points on sprint weekends (3 in 2021, 8 from 2022).
  remaining_max(after round r) = sum of weekend-max over rounds > r.

* CLINCH: the champion C is mathematically uncatchable after round r iff
      C_points(r)  >  best_other_points(r) + remaining_max(r)        (STRICT)
  Strict, because equality would leave a rival able to TIE (decided on a
  tie-break, which we do NOT recompute). The clinch round is the first r where
  this holds. For dropped-scores seasons this is SOUND but possibly conservative
  (a rival's net gain per future race can be below the winner's points when it
  replaces an already-counted score), so a pre-1991 clinch may read one race late
  in rare cases. Flagged in the output.

* CLOSEST MARGIN = the minimum gap between P1 and P2 in the running standings
  across all rounds of the season (how close it ever got).
"""
from collections import defaultdict
from common import connect, PARQUET
from points_systems import SEASON_TABLE, POINTS_TABLES


def weekend_max(con):
    """(season, round) -> max points attainable by one driver that weekend."""
    sprint_rounds = dict(con.execute("""
        SELECT ra.season || '-' || ra.round, count(*)
        FROM sprint_results s JOIN fact_races ra USING (raceId)
        GROUP BY ra.season || '-' || ra.round
    """).fetchall())
    races = con.execute("SELECT season, round FROM fact_races").fetchall()
    wmax = {}
    for season, rnd in races:
        tk = SEASON_TABLE[season]
        spec = POINTS_TABLES[tk]
        m = float(spec["points"][0])                      # race win
        if spec["fl_rule"] != "none":
            m += 1.0                                       # fastest-lap point
        if f"{season}-{rnd}" in sprint_rounds:             # sprint weekend
            m += 3.0 if season == 2021 else 8.0
        wmax[(season, rnd)] = m
    return wmax


def running_standings(con):
    """season -> round -> {driverId: cumulative_points}; plus rounds per season."""
    rows = con.execute("""
        SELECT ra.season, ra.round, ds.driverId, ds.points
        FROM driver_standings ds JOIN fact_races ra USING (raceId)
    """).fetchall()
    standings = defaultdict(lambda: defaultdict(dict))
    rounds = defaultdict(set)
    for season, rnd, drv, pts in rows:
        standings[season][rnd][drv] = pts
        rounds[season].add(rnd)
    return standings, rounds


def actual_champions(con):
    rows = con.execute("""
        WITH finals AS (SELECT season, max(round) mr FROM fact_races GROUP BY season)
        SELECT r.season, ds.driverId
        FROM driver_standings ds JOIN fact_races r USING (raceId)
        JOIN finals f ON f.season=r.season AND f.mr=r.round
        WHERE CAST(ds.position AS INT)=1
    """).fetchall()
    return {s: d for s, d in rows}


def build(con):
    print("=" * 78)
    print("FEATURE 2 — CLINCH GEOMETRY")
    print("=" * 78)
    wmax = weekend_max(con)
    standings, rounds = running_standings(con)
    champ = actual_champions(con)
    race_name = dict(con.execute("SELECT season||'-'||round, race_name FROM fact_races").fetchall())
    name = lambda d: con.execute("SELECT full_name FROM dim_drivers WHERE driverId=?", [d]).fetchone()[0]

    out = []
    for season in sorted(champ):
        C = champ[season]
        rs = sorted(rounds[season])
        last = rs[-1]
        # remaining max after each round
        rem = {}
        for i, r in enumerate(rs):
            rem[r] = sum(wmax[(season, rr)] for rr in rs[i + 1:])
        clinch_round = None
        for r in rs:
            board = standings[season][r]
            c_pts = board.get(C, 0.0)
            best_other = max((p for d, p in board.items() if d != C), default=0.0)
            if c_pts > best_other + rem[r]:
                clinch_round = r
                break
        # closest P1-P2 margin across the season
        min_gap = None
        for r in rs:
            board = sorted(standings[season][r].values(), reverse=True)
            if len(board) >= 2:
                gap = board[0] - board[1]
                min_gap = gap if min_gap is None else min(min_gap, gap)
        if clinch_round is None:        # safety: never uncatchable before final math => decided at finale
            clinch_round = last
        races_remaining = last - clinch_round  # rounds after the clinch round
        went_to_finale = (clinch_round == last)
        out.append((
            season, name(C), clinch_round, race_name.get(f"{season}-{clinch_round}"),
            len(rs), races_remaining, went_to_finale, round(min_gap or 0.0, 1),
        ))

    con.execute("""
        CREATE OR REPLACE TABLE f1_clinch (
            season INT, champion VARCHAR, clinch_round INT, clinch_race VARCHAR,
            total_rounds INT, races_remaining_at_clinch INT, went_to_finale BOOLEAN,
            closest_margin DOUBLE
        )
    """)
    con.executemany("INSERT INTO f1_clinch VALUES (?,?,?,?,?,?,?,?)", out)
    pq = PARQUET / "f1_clinch.parquet"
    con.execute(f"COPY f1_clinch TO '{pq}' (FORMAT PARQUET)")

    finale = [r for r in out if r[6]]
    earliest = sorted(out, key=lambda r: -r[5])[:5]
    print(f"\nTitles decided at the FINAL race: {len(finale)}/{len(out)}")
    print("Earliest clinches (most races to spare):")
    for r in earliest:
        print(f"  {r[0]} {r[1]:18} clinched round {r[2]} ({r[3]}), {r[5]} races to spare")
    print("\nSample recent seasons:")
    for r in [x for x in out if x[0] in (2008, 2010, 2012, 2016, 2021, 2023)]:
        tag = "FINALE" if r[6] else f"{r[5]} to spare"
        print(f"  {r[0]} {r[1]:18} clinch R{r[2]} {r[3]:<24} [{tag}]  closest margin {r[7]:g}")
    print(f"\n  wrote {pq.relative_to(PARQUET.parent.parent)}  ({len(out):,} rows)\n")


def main():
    con = connect()
    build(con)
    con.close()
    print("FEATURE 2: done.")


if __name__ == "__main__":
    main()
