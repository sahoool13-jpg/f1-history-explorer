"""Phase A — Step 3: the teammate head-to-head spine.

A teammate pair-season = two drivers who share a constructor within one season.
This is the only car-controlled comparison available without modelling car pace,
so it is the factual spine the later phases build on.

RULES (stated explicitly; messy realities are handled, not papered over):

  * PAIR IDENTIFICATION. Pairs are formed per (season, constructorId). A
    constructor with N drivers in a season yields all C(N,2) pairs, so 3+ drivers
    in one seat are represented as multiple pairwise records.

  * COMMON RACES. A race counts for a pair only if BOTH drivers have a result row
    for that constructor that weekend. This means:
      - mid-season driver swaps -> the pair simply has fewer (possibly zero) common
        races; each driver is paired with whoever actually shared the car.
      - a driver who changes teams mid-season is paired, per constructor, with the
        team-mates at each team.

  * RACE H2H (who finished ahead). Counted ONLY over common races where BOTH drivers
    are CLASSIFIED (finish_position non-NULL; see classification rule in ingest.py).
    The lower finishing position wins. Races where either retired/was unclassified
    (DNF/DNS/DNQ/DSQ) are EXCLUDED from the win/loss tally and reported separately.
    Equal finishing position (shared drives, historic) counts as a tie, not a win.

  * QUALIFYING H2H (who out-qualified whom). Counted ONLY over races where BOTH
    drivers set a timed lap (Q1/Q2/Q3 present) and have a qualifying position. Lower
    qualifying position wins. Source is the dedicated qualifying table, which only
    covers 1994+ ; earlier seasons therefore have zero qualifying-H2H races (grid
    position is deliberately NOT used as a substitute because grid penalties distort
    it).

  * POINTS WITHIN PAIRING. Championship points each driver scored over the pair's
    common races (head-to-head points, not full-season points).

Artifacts:
  teammate_pair_race    one row per (pair, race): the granular comparison
  teammate_pair_season  one row per (season, constructor, driverA<driverB)
  teammate_career       one row per driver: career teammate record (directed)
"""
from common import PARQUET, connect


def build(con):
    print("=" * 78)
    print("BUILDING TEAMMATE HEAD-TO-HEAD SPINE")
    print("=" * 78)

    # ----- granular per-race comparison -----------------------------------
    con.execute("""
        CREATE OR REPLACE TABLE teammate_pair_race AS
        WITH sd AS (  -- distinct driver within a constructor-season
            SELECT DISTINCT season, constructorId, driverId FROM fact_results
        ),
        pairs AS (
            SELECT a.season, a.constructorId,
                   a.driverId AS driverA, b.driverId AS driverB
            FROM sd a JOIN sd b
              ON a.season = b.season
             AND a.constructorId = b.constructorId
             AND a.driverId < b.driverId
        )
        SELECT
            p.season, p.constructorId, p.driverA, p.driverB, ra.raceId, ra.round,
            -- race side
            ra.finish_position AS a_finish, rb.finish_position AS b_finish,
            ra.classified AS a_classified, rb.classified AS b_classified,
            (ra.classified AND rb.classified) AS race_comparable,
            ra.points AS a_points, rb.points AS b_points,
            CASE WHEN ra.classified AND rb.classified
                 THEN CASE WHEN ra.finish_position < rb.finish_position THEN 'A'
                           WHEN rb.finish_position < ra.finish_position THEN 'B'
                           ELSE 'TIE' END END AS race_winner,
            -- qualifying side
            qa.quali_position AS a_quali, qb.quali_position AS b_quali,
            (qa.has_time AND qb.has_time
             AND qa.quali_position IS NOT NULL AND qb.quali_position IS NOT NULL) AS quali_comparable,
            CASE WHEN qa.has_time AND qb.has_time
                  AND qa.quali_position IS NOT NULL AND qb.quali_position IS NOT NULL
                 THEN CASE WHEN qa.quali_position < qb.quali_position THEN 'A'
                           WHEN qb.quali_position < qa.quali_position THEN 'B'
                           ELSE 'TIE' END END AS quali_winner
        FROM pairs p
        JOIN fact_results ra
          ON ra.season = p.season AND ra.constructorId = p.constructorId AND ra.driverId = p.driverA
        JOIN fact_results rb
          ON rb.raceId = ra.raceId AND rb.constructorId = p.constructorId AND rb.driverId = p.driverB
        LEFT JOIN fact_qualifying qa
          ON qa.raceId = ra.raceId AND qa.constructorId = p.constructorId AND qa.driverId = p.driverA
        LEFT JOIN fact_qualifying qb
          ON qb.raceId = ra.raceId AND qb.constructorId = p.constructorId AND qb.driverId = p.driverB
    """)

    # ----- aggregate to pair-season ---------------------------------------
    con.execute("""
        CREATE OR REPLACE TABLE teammate_pair_season AS
        SELECT
            season, constructorId, driverA, driverB,
            count(*)                                              AS common_races,
            count(*) FILTER (WHERE race_comparable)              AS race_h2h_races,
            count(*) FILTER (WHERE race_winner = 'A')            AS a_race_wins,
            count(*) FILTER (WHERE race_winner = 'B')            AS b_race_wins,
            count(*) FILTER (WHERE race_winner = 'TIE')          AS race_ties,
            count(*) FILTER (WHERE a_classified AND NOT b_classified) AS a_only_classified,
            count(*) FILTER (WHERE b_classified AND NOT a_classified) AS b_only_classified,
            count(*) FILTER (WHERE NOT a_classified AND NOT b_classified) AS both_dnf,
            count(*) FILTER (WHERE quali_comparable)             AS quali_h2h_races,
            count(*) FILTER (WHERE quali_winner = 'A')           AS a_quali_wins,
            count(*) FILTER (WHERE quali_winner = 'B')           AS b_quali_wins,
            count(*) FILTER (WHERE quali_winner = 'TIE')         AS quali_ties,
            sum(a_points)                                        AS a_points,
            sum(b_points)                                        AS b_points
        FROM teammate_pair_race
        GROUP BY season, constructorId, driverA, driverB
    """)

    # ----- directed long form, then career rollup -------------------------
    con.execute("""
        CREATE OR REPLACE TABLE teammate_pair_season_directed AS
        SELECT season, constructorId, driverA AS driverId, driverB AS teammateId,
               common_races, race_h2h_races,
               a_race_wins AS race_wins, b_race_wins AS race_losses, race_ties,
               quali_h2h_races, a_quali_wins AS quali_wins, b_quali_wins AS quali_losses, quali_ties,
               a_points AS points_for, b_points AS points_against
        FROM teammate_pair_season
        UNION ALL
        SELECT season, constructorId, driverB, driverA,
               common_races, race_h2h_races,
               b_race_wins, a_race_wins, race_ties,
               quali_h2h_races, b_quali_wins, a_quali_wins, quali_ties,
               b_points, a_points
        FROM teammate_pair_season
    """)

    con.execute("""
        CREATE OR REPLACE TABLE teammate_career AS
        SELECT
            d.driverId, d.full_name, d.code, d.nationality,
            count(DISTINCT teammateId)                                 AS distinct_teammates,
            count(DISTINCT (season::VARCHAR||'-'||constructorId::VARCHAR||'-'||teammateId::VARCHAR)) AS pair_seasons,
            sum(common_races)        AS common_races,
            sum(quali_h2h_races)     AS quali_h2h_races,
            sum(quali_wins)          AS quali_wins,
            sum(quali_losses)        AS quali_losses,
            sum(race_h2h_races)      AS race_h2h_races,
            sum(race_wins)           AS race_wins,
            sum(race_losses)         AS race_losses,
            sum(race_ties)           AS race_ties,
            sum(points_for)          AS points_for,
            sum(points_against)      AS points_against
        FROM teammate_pair_season_directed t
        JOIN dim_drivers d USING (driverId)
        GROUP BY d.driverId, d.full_name, d.code, d.nationality
    """)

    for t in ["teammate_pair_race", "teammate_pair_season", "teammate_career"]:
        out = PARQUET / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{out}' (FORMAT PARQUET)")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  wrote {out.relative_to(PARQUET.parent.parent)}  ({n:,} rows)")
    print()


def main():
    con = connect()
    build(con)
    con.close()
    print("TEAMMATE H2H: done.")


if __name__ == "__main__":
    main()
