"""Phase A — Step 1 & 2: ingest raw CSVs into DuckDB and emit validated Parquet base.

Loads every Ergast CSV in data/raw/, prints a manifest (row count + columns) so we
confirm exactly what is present, then builds the clean relational artifacts:

  dim_drivers, dim_constructors, dim_circuits   (reference tables)
  fact_races                                    (one row per race, with season/round/circuit/date)
  fact_results                                  (one row per driver per race; finish, status, points, grid, constructor)
  fact_qualifying                               (one row per driver per race that has qualifying data)

All artifacts are written to data/parquet/ as build outputs.
"""
import sys
from common import RAW, PARQUET, NULLSTR, RAW_TABLES, connect


def load_raw(con):
    print("=" * 78)
    print("RAW CSV MANIFEST  (what is actually in data/raw/)")
    print("=" * 78)
    missing = []
    for name in RAW_TABLES:
        path = RAW / f"{name}.csv"
        if not path.exists():
            missing.append(name)
            print(f"  !! MISSING: {name}.csv")
            continue
        con.execute(
            f"CREATE OR REPLACE TABLE {name} AS "
            f"SELECT * FROM read_csv('{path}', header=true, nullstr='{NULLSTR}', "
            f"sample_size=-1, all_varchar=false)"
        )
        n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        cols = [c[0] for c in con.execute(f"DESCRIBE {name}").fetchall()]
        print(f"\n  {name}.csv  —  {n:,} rows, {len(cols)} cols")
        print(f"    columns: {', '.join(cols)}")
    if missing:
        print(f"\nFATAL: missing CSVs: {missing}")
        sys.exit(1)
    print()


def build_artifacts(con):
    print("=" * 78)
    print("BUILDING VALIDATED PARQUET ARTIFACTS")
    print("=" * 78)

    # --- reference dimensions ---------------------------------------------
    con.execute("""
        CREATE OR REPLACE TABLE dim_drivers AS
        SELECT driverId, driverRef, code,
               forename, surname,
               trim(forename || ' ' || surname) AS full_name,
               TRY_CAST(dob AS DATE) AS dob,
               nationality
        FROM drivers
    """)

    con.execute("""
        CREATE OR REPLACE TABLE dim_constructors AS
        SELECT constructorId, constructorRef, name AS constructor_name, nationality
        FROM constructors
    """)

    con.execute("""
        CREATE OR REPLACE TABLE dim_circuits AS
        SELECT circuitId, circuitRef, name AS circuit_name, location, country, lat, lng
        FROM circuits
    """)

    # --- fact_races --------------------------------------------------------
    con.execute("""
        CREATE OR REPLACE TABLE fact_races AS
        SELECT raceId,
               year AS season,
               round,
               circuitId,
               name AS race_name,
               TRY_CAST(date AS DATE) AS race_date
        FROM races
    """)

    # --- fact_results ------------------------------------------------------
    # CLASSIFICATION RULE: a driver is "classified" in a race iff Ergast `position`
    # is non-NULL (equivalently positionText is numeric). This mirrors the official
    # F1 classification (completed >=90% of race distance). Non-numeric positionText
    # codes -- R (retired/not classified), D (disqualified), E (excluded),
    # W (withdrawn), F (failed to qualify), N (not classified) -- are NOT classified.
    con.execute("""
        CREATE OR REPLACE TABLE fact_results AS
        SELECT
            r.resultId,
            r.raceId,
            ra.season,
            ra.round,
            ra.circuitId,
            ra.race_date,
            r.driverId,
            r.constructorId,
            CAST(r.grid AS INTEGER)                         AS grid,
            CAST(r.position AS INTEGER)                     AS finish_position,  -- NULL if not classified
            r.positionText,
            CAST(r."positionOrder" AS INTEGER)              AS position_order,   -- dense order incl. retirements
            CAST(r.points AS DOUBLE)                        AS points,
            CAST(r.laps AS INTEGER)                         AS laps,
            r.statusId,
            s.status,
            (r.position IS NOT NULL)                        AS classified
        FROM results r
        JOIN fact_races ra USING (raceId)
        JOIN status s USING (statusId)
    """)

    # --- fact_qualifying ---------------------------------------------------
    # has_time = driver set at least one timed lap (Q1/Q2/Q3). quali_position is the
    # qualifying classification. Qualifying table coverage is limited (see manifest).
    con.execute("""
        CREATE OR REPLACE TABLE fact_qualifying AS
        SELECT
            q.qualifyId,
            q.raceId,
            ra.season,
            ra.round,
            q.driverId,
            q.constructorId,
            CAST(q.position AS INTEGER)                     AS quali_position,
            q.q1, q.q2, q.q3,
            (q.q1 IS NOT NULL OR q.q2 IS NOT NULL OR q.q3 IS NOT NULL) AS has_time
        FROM qualifying q
        JOIN fact_races ra USING (raceId)
    """)

    artifacts = [
        "dim_drivers", "dim_constructors", "dim_circuits",
        "fact_races", "fact_results", "fact_qualifying",
    ]
    for t in artifacts:
        out = PARQUET / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{out}' (FORMAT PARQUET)")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  wrote {out.relative_to(PARQUET.parent.parent)}  ({n:,} rows)")

    # quick coverage notes
    qmin, qmax, qn = con.execute(
        "SELECT min(season), max(season), count(DISTINCT season) FROM fact_qualifying"
    ).fetchone()
    print(f"\n  qualifying-table season coverage: {qmin}-{qmax} ({qn} seasons)")
    print()


def main():
    con = connect()
    load_raw(con)
    build_artifacts(con)
    con.close()
    print("INGEST: done.")


if __name__ == "__main__":
    main()
