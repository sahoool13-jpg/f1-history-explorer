"""Phase B — FEATURE 1: points-system invariance.

"Would the champion change under a different scoring system?"

Pure recomputation of real finishing positions under every historical points
TABLE. No modelling, no estimates.

METHOD & STATED ASSUMPTIONS
---------------------------
* ACTUAL champion (the reference) = the driver in P1 of driver_standings after the
  final round of the season — i.e. real history under that era's real rules
  (its points table, fastest-lap rule, AND its dropped-scores rule).

* FAITHFUL RECOMPUTATION (master gate): each driver's per-race points are taken
  from the dataset (results.points + sprint_results.points, which already bake in
  the era's table, fastest-lap and half-points rules), then the season's real
  dropped-scores rule is applied. This must reproduce the ACTUAL champion for ALL
  seasons, and reproduces official TOTALS for 74/75 seasons (1956 flagged).

* CROSS-TABLE COMPARISON (the headline): for each named points table we apply its
  position-points vector to every driver's real finishing positions and sum ALL
  races. To isolate the effect of the TABLE SHAPE we hold two things constant
  across every table: (a) ALL RESULTS COUNT (no dropped scores) and (b) NO
  fastest-lap points. Dropped-scores is a season property, not a table property,
  so mixing it in would confound the comparison. Half-points races are scored at
  full value here (hypothetical). Every one of these assumptions is stated; the
  faithful recomputation above is what reconciles to history.

* The dropped-scores effect is shown explicitly for the season's OWN table
  (all-results vs real dropped rule) — this is the 1988 Senna/Prost story.
"""
from collections import defaultdict
from common import connect, PARQUET
from points_systems import (
    POINTS_TABLES, SEASON_TABLE, points_for_position,
    dropped_rule, apply_dropped, FLAGGED_SEASONS,
)


def load_perrace(con):
    """season -> driver -> round -> {'pts': real pts, 'pos': finish position or None}."""
    rows = con.execute("""
        WITH pr AS (
            SELECT ra.season, ra.round, r.driverId,
                   CAST(r.points AS DOUBLE) pts, r.position AS pos
            FROM results r JOIN fact_races ra USING (raceId)
        ),
        sp AS (
            SELECT ra.season, ra.round, s.driverId,
                   CAST(s.points AS DOUBLE) pts
            FROM sprint_results s JOIN fact_races ra USING (raceId)
        )
        SELECT season, round, driverId,
               sum(pts)      AS pts,
               max(pos)      AS finish_pos      -- race finish position (sprint has none)
        FROM (
            SELECT season, round, driverId, pts, pos FROM pr
            UNION ALL
            SELECT season, round, driverId, pts, NULL FROM sp
        )
        GROUP BY season, round, driverId
    """).fetchall()
    real_pts = defaultdict(lambda: defaultdict(dict))   # season->driver->round->pts (real, incl sprint/FL)
    finish = defaultdict(lambda: defaultdict(dict))     # season->driver->round->finish_pos
    for season, rnd, drv, pts, pos in rows:
        real_pts[season][drv][rnd] = pts
        finish[season][drv][rnd] = int(pos) if pos is not None else None
    return real_pts, finish


def actual_champions(con):
    rows = con.execute("""
        WITH finals AS (SELECT season, max(round) mr FROM fact_races GROUP BY season)
        SELECT r.season, ds.driverId, ds.points
        FROM driver_standings ds JOIN fact_races r USING (raceId)
        JOIN finals f ON f.season=r.season AND f.mr=r.round
        WHERE CAST(ds.position AS INT)=1
    """).fetchall()
    return {s: (d, p) for s, d, p in rows}


def faithful_champion(real_pts_season, season):
    """Reproduce the champion from real per-race points + the season's dropped rule."""
    rule = dropped_rule(season)
    totals = {d: apply_dropped(rule, byr) for d, byr in real_pts_season.items()}
    champ = max(totals, key=lambda d: totals[d])
    return champ, totals[champ], totals


def champion_under_table(finish_season, table_key):
    """Champion if `table_key` (position vector, all results, no FL) had been used."""
    totals = defaultdict(float)
    for drv, byr in finish_season.items():
        for rnd, pos in byr.items():
            if pos is not None:
                totals[drv] += points_for_position(table_key, pos, fl=False)
    champ = max(totals, key=lambda d: totals[d])
    return champ, totals[champ], totals


def build(con):
    print("=" * 78)
    print("FEATURE 1 — POINTS-SYSTEM INVARIANCE")
    print("=" * 78)
    real_pts, finish = load_perrace(con)
    actual = actual_champions(con)
    name = lambda d: con.execute("SELECT full_name FROM dim_drivers WHERE driverId=?", [d]).fetchone()[0]

    table_keys = list(POINTS_TABLES.keys())
    out_rows = []
    n_change_any = 0
    for season in sorted(actual):
        actual_drv, actual_pts = actual[season]
        for tk in table_keys:
            champ, champ_pts, _ = champion_under_table(finish[season], tk)
            changed = (champ != actual_drv)
            out_rows.append((season, name(actual_drv), tk, name(champ), changed, round(champ_pts, 2)))
        if any(r[4] for r in out_rows if r[0] == season):
            n_change_any += 1

    # persist
    con.execute("""
        CREATE OR REPLACE TABLE f1_points_invariance (
            season INT, actual_champion VARCHAR, points_table VARCHAR,
            champion_under_table VARCHAR, champion_changes BOOLEAN, table_points DOUBLE
        )
    """)
    con.executemany("INSERT INTO f1_points_invariance VALUES (?,?,?,?,?,?)", out_rows)
    out = PARQUET / "f1_points_invariance.parquet"
    con.execute(f"COPY f1_points_invariance TO '{out}' (FORMAT PARQUET)")

    # report: seasons where SOME table changes the champion
    print(f"\nSeasons where at least one points TABLE would change the champion: {n_change_any}/{len(actual)}")
    print("(cross-table comparison: position-vector only, all results count, no FL)\n")
    changed_seasons = sorted({r[0] for r in out_rows if r[4]})
    for season in changed_seasons:
        actual_drv = name(actual[season][0])
        flips = [(r[2], r[3]) for r in out_rows if r[0] == season and r[4]]
        flip_str = "; ".join(f"{tk.split('_')[0][1:]}->{ch}" for tk, ch in flips)
        print(f"  {season}: actual={actual_drv:18}  flips: {flip_str}")

    # explicit 1988 dropped-scores demonstration (own table, drop vs no-drop)
    print("\n--- 1988 dropped-scores demonstration (own table 9-6-4-3-2-1) ---")
    s = 1988
    _, _, nodrop = champion_under_table(finish[s], SEASON_TABLE[s])
    _, _, faith = faithful_champion(real_pts[s], s)
    top_nodrop = sorted(nodrop.items(), key=lambda x: -x[1])[:2]
    top_drop = sorted(faith.items(), key=lambda x: -x[1])[:2]
    print(f"  all results (no drop):  {name(top_nodrop[0][0])} {top_nodrop[0][1]:.0f}  >  "
          f"{name(top_nodrop[1][0])} {top_nodrop[1][1]:.0f}")
    print(f"  best-11 (real rule):    {name(top_drop[0][0])} {top_drop[0][1]:.0f}  >  "
          f"{name(top_drop[1][0])} {top_drop[1][1]:.0f}")

    if FLAGGED_SEASONS:
        print("\n--- FLAGGED seasons (totals not exactly reproducible; champion correct) ---")
        for yr, note in FLAGGED_SEASONS.items():
            print(f"  {yr}: {note}")
    print(f"\n  wrote {out.relative_to(PARQUET.parent.parent)}  ({len(out_rows):,} rows)\n")


def main():
    con = connect()
    build(con)
    con.close()
    print("FEATURE 1: done.")


if __name__ == "__main__":
    main()
