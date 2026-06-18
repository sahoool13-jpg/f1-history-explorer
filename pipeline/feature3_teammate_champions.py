"""Phase B — FEATURE 3: teammate-adjusted champions.

"How did each drivers' champion fare against their OWN teammate that season?"

Pure join of Phase A's teammate-H2H spine to each season's champion. No modelling.

* For each season's actual champion we sum their head-to-head record against every
  teammate they had that season (a champion can have >1 teammate — injury subs,
  mid-season swaps), using teammate_pair_season_directed from Phase A. Numbers tie
  back to Phase A exactly (same tables).
* Qualifying H2H respects Phase A's 1994+ boundary: pre-1994 has no qualifying-table
  data, so quali_h2h_races = 0 and only the race H2H is meaningful (noted in output).
* Flags the interesting anomalies: champions OUT-QUALIFIED or OUT-RACED by a
  teammate (rare) vs champions who dominated their teammate.
"""
from common import connect, PARQUET


def build(con):
    print("=" * 78)
    print("FEATURE 3 — TEAMMATE-ADJUSTED CHAMPIONS")
    print("=" * 78)

    con.execute("""
        CREATE OR REPLACE TABLE f1_champion_teammate AS
        WITH finals AS (SELECT season, max(round) mr FROM fact_races GROUP BY season),
        champ AS (
            SELECT r.season, ds.driverId AS championId
            FROM driver_standings ds JOIN fact_races r USING (raceId)
            JOIN finals f ON f.season=r.season AND f.mr=r.round
            WHERE CAST(ds.position AS INT)=1
        ),
        joined AS (
            SELECT c.season, c.championId,
                   t.teammateId, t.quali_h2h_races, t.quali_wins, t.quali_losses,
                   t.race_h2h_races, t.race_wins, t.race_losses,
                   t.points_for, t.points_against
            FROM champ c
            LEFT JOIN teammate_pair_season_directed t
              ON t.season=c.season AND t.driverId=c.championId
        )
        SELECT
            j.season,
            dc.full_name AS champion,
            string_agg(DISTINCT dt.full_name, ', ') AS teammates,
            count(DISTINCT j.teammateId)            AS n_teammates,
            coalesce(sum(j.quali_h2h_races),0)      AS quali_h2h_races,
            coalesce(sum(j.quali_wins),0)           AS champ_quali_wins,
            coalesce(sum(j.quali_losses),0)         AS champ_quali_losses,
            coalesce(sum(j.race_h2h_races),0)       AS race_h2h_races,
            coalesce(sum(j.race_wins),0)            AS champ_race_wins,
            coalesce(sum(j.race_losses),0)          AS champ_race_losses,
            coalesce(sum(j.points_for),0)           AS champ_points,
            coalesce(sum(j.points_against),0)       AS teammate_points,
            (coalesce(sum(j.quali_wins),0) < coalesce(sum(j.quali_losses),0)) AS out_qualified_by_teammate,
            (coalesce(sum(j.race_wins),0)  < coalesce(sum(j.race_losses),0))  AS out_raced_by_teammate
        FROM joined j
        JOIN dim_drivers dc ON dc.driverId=j.championId
        LEFT JOIN dim_drivers dt ON dt.driverId=j.teammateId
        GROUP BY j.season, dc.full_name
        ORDER BY j.season
    """)
    pq = PARQUET / "f1_champion_teammate.parquet"
    con.execute(f"COPY f1_champion_teammate TO '{pq}' (FORMAT PARQUET)")
    n = con.execute("SELECT count(*) FROM f1_champion_teammate").fetchone()[0]

    print("\n--- Champions OUT-QUALIFIED by a teammate (1994+; the rare anomaly) ---")
    for row in con.execute("""
        SELECT season, champion, teammates, champ_quali_wins, champ_quali_losses
        FROM f1_champion_teammate
        WHERE out_qualified_by_teammate AND quali_h2h_races > 0
        ORDER BY season
    """).fetchall():
        print(f"  {row[0]} {row[1]:18} quali {row[3]}-{row[4]} vs {row[2]}")

    print("\n--- Champions OUT-RACED by a teammate (any era; very rare) ---")
    outraced = con.execute("""
        SELECT season, champion, teammates, champ_race_wins, champ_race_losses
        FROM f1_champion_teammate WHERE out_raced_by_teammate ORDER BY season
    """).fetchall()
    if outraced:
        for row in outraced:
            print(f"  {row[0]} {row[1]:18} race {row[3]}-{row[4]} vs {row[2]}")
    else:
        print("  (none)")

    print("\n--- Most DOMINANT champions vs teammate (qualifying, 1994+) ---")
    for row in con.execute("""
        SELECT season, champion, teammates, champ_quali_wins, champ_quali_losses
        FROM f1_champion_teammate WHERE quali_h2h_races > 0
        ORDER BY (champ_quali_wins - champ_quali_losses) DESC, champ_quali_wins DESC LIMIT 6
    """).fetchall():
        print(f"  {row[0]} {row[1]:18} quali {row[3]}-{row[4]} vs {row[2]}")

    print(f"\n  wrote {pq.relative_to(PARQUET.parent.parent)}  ({n:,} rows)\n")


def main():
    con = connect()
    build(con)
    con.close()
    print("FEATURE 3: done.")


if __name__ == "__main__":
    main()
