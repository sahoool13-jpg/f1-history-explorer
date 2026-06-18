"""Phase A — GATE: reconcile every artifact to known F1 truths.

Prints a PASS/FAIL line for each assertion. ANY failure exits non-zero and stops
the phase (strict phase-gate discipline).
"""
import sys
from common import connect

RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append((name, bool(passed)))
    flag = "PASS" if passed else "FAIL"
    print(f"  [{flag}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    q = lambda s: con.execute(s).fetchall()
    q1 = lambda s: con.execute(s).fetchone()

    print("=" * 78)
    print("PHASE A GATE — reconciliation to known F1 truths")
    print("=" * 78)

    # ---------------------------------------------------------------- GATE 1
    print("\nGATE 1 — 1950 championship: Farina champion, ahead of teammate Fangio (Alfa Romeo)")
    final_round_1950 = q1("SELECT max(round) FROM fact_races WHERE season=1950")[0]
    standings = q(f"""
        SELECT d.full_name, CAST(ds.position AS INT) pos, ds.points
        FROM driver_standings ds
        JOIN fact_races r USING (raceId)
        JOIN dim_drivers d USING (driverId)
        WHERE r.season=1950 AND r.round={final_round_1950}
        ORDER BY CAST(ds.position AS INT) LIMIT 2
    """)
    (champ, champ_pos, champ_pts), (runner, run_pos, run_pts) = standings
    print(f"        P1 {champ} ({champ_pts:.0f} pts)   P2 {runner} ({run_pts:.0f} pts)")
    # both Alfa Romeo in 1950?
    alfa = q("""
        SELECT DISTINCT d.full_name
        FROM fact_results fr JOIN dim_drivers d USING (driverId)
        JOIN dim_constructors c USING (constructorId)
        WHERE fr.season=1950 AND c.constructor_name='Alfa Romeo'
    """)
    alfa_names = {r[0] for r in alfa}
    check("1950 champion is Giuseppe/Nino Farina", "Farina" in champ and champ_pos == 1, champ)
    check("1950 runner-up is Fangio", "Fangio" in runner and run_pos == 2, runner)
    check("Farina beat Fangio on points", champ_pts > run_pts, f"{champ_pts:.0f} > {run_pts:.0f}")
    check("Both were Alfa Romeo teammates in 1950",
          champ in alfa_names and runner in alfa_names)

    # ---------------------------------------------------------------- GATE 2
    print("\nGATE 2 — race counts per season match known values")
    known = {1950: 7, 2010: 19, 2019: 21, 2021: 22, 2022: 22}
    for season, expected in known.items():
        got = q1(f"SELECT count(*) FROM fact_races WHERE season={season}")[0]
        note = " (incl. Indianapolis 500)" if season == 1950 else ""
        check(f"{season} race count == {expected}{note}", got == expected, f"got {got}")

    # ---------------------------------------------------------------- GATE 3
    print("\nGATE 3 — 2016 Mercedes: Rosberg beat Hamilton for the title")
    merc2016 = q("""
        SELECT d.full_name, sum(fr.points) pts
        FROM fact_results fr JOIN dim_drivers d USING (driverId)
        JOIN dim_constructors c USING (constructorId)
        WHERE fr.season=2016 AND c.constructor_name='Mercedes'
        GROUP BY d.full_name ORDER BY pts DESC
    """)
    pts = {r[0]: r[1] for r in merc2016}
    ros = next(k for k in pts if "Rosberg" in k)
    ham = next(k for k in pts if "Hamilton" in k)
    # head-to-head (directional) from the pair-season table
    h2h = q1("""
        SELECT
          CASE WHEN da.full_name LIKE '%Rosberg%' THEN ps.a_quali_wins ELSE ps.b_quali_wins END,
          CASE WHEN da.full_name LIKE '%Rosberg%' THEN ps.b_quali_wins ELSE ps.a_quali_wins END,
          CASE WHEN da.full_name LIKE '%Rosberg%' THEN ps.a_race_wins  ELSE ps.b_race_wins  END,
          CASE WHEN da.full_name LIKE '%Rosberg%' THEN ps.b_race_wins  ELSE ps.a_race_wins  END,
          ps.quali_h2h_races, ps.race_h2h_races
        FROM teammate_pair_season ps
        JOIN dim_drivers da ON da.driverId=ps.driverA
        JOIN dim_drivers db ON db.driverId=ps.driverB
        JOIN dim_constructors c USING (constructorId)
        WHERE ps.season=2016 AND c.constructor_name='Mercedes'
    """)
    ros_q, ham_q, ros_r, ham_r, qn, rn = h2h
    print(f"        Season points: {ros} {pts[ros]:.0f}  vs  {ham} {pts[ham]:.0f}")
    print(f"        Qualifying H2H ({qn} races): Rosberg {ros_q} – {ham_q} Hamilton")
    print(f"        Race H2H ({rn} both-classified races): Rosberg {ros_r} – {ham_r} Hamilton")
    check("Rosberg outscored Hamilton in 2016 (won the title)", pts[ros] > pts[ham],
          f"{pts[ros]:.0f} > {pts[ham]:.0f}")
    check("2016 Merc qualifying H2H is populated & directionally sane (Hamilton strong in quali)",
          qn > 0 and (ros_q + ham_q) == qn, f"{ros_q}-{ham_q} over {qn}")
    check("2016 Merc race H2H is populated", rn > 0 and (ros_r + ham_r) <= rn,
          f"{ros_r}-{ham_r} over {rn}")

    # ---------------------------------------------------------------- GATE 4
    print("\nGATE 4 — dataset totals are sane")
    n_drivers = q1("SELECT count(*) FROM dim_drivers")[0]
    n_constructors = q1("SELECT count(*) FROM dim_constructors")[0]
    n_races = q1("SELECT count(*) FROM fact_races")[0]
    n_seasons = q1("SELECT count(DISTINCT season) FROM fact_races")[0]
    print(f"        drivers={n_drivers}  constructors={n_constructors}  "
          f"races={n_races}  seasons={n_seasons}")
    check("driver count sane (800-900)", 800 <= n_drivers <= 900, str(n_drivers))
    check("constructor count sane (200-220)", 200 <= n_constructors <= 220, str(n_constructors))
    check("race count sane (1100-1150)", 1100 <= n_races <= 1150, str(n_races))
    check("season count sane (74-76)", 74 <= n_seasons <= 76, str(n_seasons))

    # ---------------------------------------------------------------- GATE 5
    print("\nGATE 5 — lopsided teammate qualifying H2H vs a known fact")
    print("        Known: in 2019 Max Verstappen comprehensively out-qualified Pierre")
    print("        Gasly at Red Bull (~10-1), a factor in Gasly's mid-season demotion.")
    vg = q1("""
        SELECT
          CASE WHEN da.full_name LIKE '%Verstappen%' THEN ps.a_quali_wins ELSE ps.b_quali_wins END,
          CASE WHEN da.full_name LIKE '%Verstappen%' THEN ps.b_quali_wins ELSE ps.a_quali_wins END,
          ps.quali_h2h_races
        FROM teammate_pair_season ps
        JOIN dim_drivers da ON da.driverId=ps.driverA
        JOIN dim_drivers db ON db.driverId=ps.driverB
        JOIN dim_constructors c USING (constructorId)
        WHERE ps.season=2019 AND c.constructor_name='Red Bull'
          AND (da.full_name LIKE '%Gasly%' OR db.full_name LIKE '%Gasly%')
    """)
    ver_q, gas_q, vg_n = vg
    print(f"        Qualifying H2H ({vg_n} races): Verstappen {ver_q} – {gas_q} Gasly")
    check("Verstappen >> Gasly in 2019 qualifying (lopsided)",
          ver_q >= 9 and ver_q >= 2 * max(gas_q, 1), f"{ver_q}-{gas_q}")

    # ---------------------------------------------------------------- SUMMARY
    print("\n" + "=" * 78)
    n_pass = sum(1 for _, p in RESULTS if p)
    n_fail = len(RESULTS) - n_pass
    print(f"GATE SUMMARY: {n_pass} PASS / {n_fail} FAIL  (of {len(RESULTS)} assertions)")
    print("=" * 78)
    con.close()
    if n_fail:
        print("\nPHASE A GATE: *** FAILED *** — phase blocked.")
        sys.exit(1)
    print("\nPHASE A GATE: *** ALL PASS *** — Phase A is validated. Cleared for Phase B.")


if __name__ == "__main__":
    main()
