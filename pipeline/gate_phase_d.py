"""Phase D GATE — reconcile the measured pace deltas to known truths.

Prints PASS/FAIL per check; any FAIL exits non-zero. Every figure traces to the
raw lap/quali data via the Phase D artifacts.
"""
import sys
from common import connect

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    # NB: driver `code` is ambiguous (VER = Vergne & Verstappen, ROS = Keke & Nico
    # Rosberg), so resolve gate drivers by full name.
    did = lambda fore, sur: con.execute(
        "SELECT driverId FROM dim_drivers WHERE forename=? AND surname=?", [fore, sur]).fetchone()[0]
    rid = lambda season, rnd: con.execute(
        "SELECT raceId FROM fact_races WHERE season=? AND round=?", [season, rnd]).fetchone()[0]
    print("=" * 78); print("PHASE D GATE — pace & deltas reconciliation"); print("=" * 78)

    HAM = did("Lewis", "Hamilton")
    ROS = did("Nico", "Rosberg")
    VER = did("Max", "Verstappen")
    GAS = did("Pierre", "Gasly")

    # helper: fetch a quali pair-season row oriented to a chosen driver
    def quali_pair(season, dX, dY):
        r = con.execute("""
            SELECT driverA, driverB, median_gap_s, mean_gap_s, std_s, n_included,
                   a_faster_races, n_valid, n_incident
            FROM quali_teammate_delta_pairseason
            WHERE season=? AND ((driverA=? AND driverB=?) OR (driverA=? AND driverB=?))
        """, [season, dX, dY, dY, dX]).fetchone()
        if not r: return None
        dA, dB, med, mean, std, n, a_faster, nval, ninc = r
        # orient to dX (negative => dX faster)
        if dA == dX:
            return dict(median=med, mean=mean, std=std, n=n, x_faster=a_faster, nval=nval, ninc=ninc)
        return dict(median=-med, mean=-mean, std=std, n=n, x_faster=nval - a_faster, nval=nval, ninc=ninc)

    # ---- GATE 1: 2016 Mercedes HAM vs ROS quali delta ----------------------
    print("\nGATE 1 — 2016 Mercedes teammate qualifying delta (Hamilton vs Rosberg)")
    q16 = quali_pair(2016, HAM, ROS)
    print(f"        median {q16['median']:+.3f}s  mean {q16['mean']:+.3f}s  std {q16['std']:.3f}  "
          f"n={q16['n']}  incidents={q16['ninc']}  (negative => Hamilton faster)")
    print(f"        sign-count: Hamilton faster in {q16['x_faster']} of {q16['nval']} valid races")
    # reconcile to Phase A 12-8 quali H2H
    pa = con.execute("""
        SELECT t.quali_wins, t.quali_losses FROM teammate_pair_season_directed t
        JOIN dim_drivers d ON d.driverId=t.driverId JOIN dim_constructors c USING (constructorId)
        WHERE t.season=2016 AND d.code='HAM' AND c.constructor_name='Mercedes'
    """).fetchone()
    check("Hamilton faster than Rosberg on average (median < 0)", q16["median"] < 0, f"{q16['median']:+.3f}s")
    check("delta is plausibly tenths (0.02–0.50s), not seconds", 0.02 < abs(q16["median"]) < 0.50, f"{abs(q16['median']):.3f}s")
    check("sign-count reconciles with Phase A 12–8 quali H2H",
          q16["x_faster"] == pa[0] == 12, f"delta {q16['x_faster']}–{q16['nval']-q16['x_faster']} vs PhaseA {pa[0]}–{pa[1]}")

    # ---- GATE 2: 2019 Red Bull VER vs GAS quali delta ----------------------
    print("\nGATE 2 — 2019 Red Bull teammate qualifying delta (Verstappen vs Gasly)")
    q19 = quali_pair(2019, VER, GAS)
    print(f"        median {q19['median']:+.3f}s  mean {q19['mean']:+.3f}s  std {q19['std']:.3f}  "
          f"n={q19['n']}  (negative => Verstappen faster)")
    print(f"        sign-count: Verstappen faster in {q19['x_faster']} of {q19['nval']} valid races")
    check("Verstappen faster than Gasly (median < 0)", q19["median"] < 0, f"{q19['median']:+.3f}s")
    check("gap is large, favouring Verstappen (|median| > 0.25s)", abs(q19["median"]) > 0.25, f"{q19['median']:+.3f}s")
    check("sign-count consistent with the 10–1 H2H from Phase A",
          q19["x_faster"] >= 10 and (q19["nval"] - q19["x_faster"]) <= 1,
          f"{q19['x_faster']}–{q19['nval']-q19['x_faster']}")

    # ---- GATE 3: race-pace method sanity (clean vs disrupted) --------------
    print("\nGATE 3 — race-pace clean-lap method (clean race vs disrupted race)")
    def racepace(season, rnd, dX, dY):
        r = con.execute("""
            SELECT driverA, driverB, delta_s_per_lap, clean_laps_a, clean_laps_b,
                   sc_fraction, reliability, reasons
            FROM racepace_teammate_race
            WHERE raceId=? AND ((driverA=? AND driverB=?) OR (driverA=? AND driverB=?))
        """, [rid(season, rnd), dX, dY, dY, dX]).fetchone()
        return r
    clean = racepace(2016, 21, HAM, ROS)        # Abu Dhabi — both finished, no SC
    print(f"        2016 Abu Dhabi  delta={clean[2]:+.3f}s/lap  clean {clean[3]}/{clean[4]}  "
          f"SC={clean[5]*100:.0f}%  reliability={clean[6]}")
    check("clean race: sensible small delta (|delta| < 0.6s/lap)", abs(clean[2]) < 0.6, f"{clean[2]:+.3f}s/lap")
    check("clean race: tagged reliability = ok", clean[6] == "ok", clean[6])

    disr = racepace(2016, 20, HAM, ROS)         # Brazil — wet, heavy safety car
    print(f"        2016 Brazil     delta={disr[2]:+.3f}s/lap  clean {disr[3]}/{disr[4]}  "
          f"SC={disr[5]*100:.0f}%  reliability={disr[6]} ({disr[7]})")
    check("safety-car-disrupted race correctly flagged LOW reliability",
          disr[6] == "low" and "safety_car_heavy" in (disr[7] or ""), f"{disr[6]}: {disr[7]}")

    dnf = racepace(2016, 16, HAM, ROS)          # Malaysia — Hamilton engine failure
    print(f"        2016 Malaysia   delta={dnf[2]}  reliability={dnf[6]} ({dnf[7]})")
    check("early/late-DNF race correctly flagged LOW (dnf_or_delayed)",
          dnf[6] == "low" and "dnf_or_delayed" in (dnf[7] or ""), f"{dnf[6]}: {dnf[7]}")

    # ---- GATE 4: clean-lap exclusion actually happening --------------------
    print("\nGATE 4 — clean-lap exclusion (in/out laps + safety-car laps removed)")
    total = con.execute("SELECT max(lap) FROM lap_times WHERE raceId=?", [rid(2016, 20)]).fetchone()[0]
    print(f"        2016 Brazil: {total} total laps; clean green laps retained — "
          f"HAM {disr[3]}, ROS {disr[4]} (lap 1 + ~{int(disr[5]*total)} SC laps + pit/outliers excluded)")
    check("clean laps retained << total laps (exclusions applied)",
          disr[3] < total and disr[4] < total and disr[3] >= 5, f"{disr[3]} of {total}")

    # ---- GATE 5: sample-size honesty ---------------------------------------
    print("\nGATE 5 — sample-size honesty (tiny samples flagged, not presented as confident)")
    low_n = con.execute("SELECT count(*) FROM racepace_teammate_race WHERE reliability='low'").fetchone()[0]
    few = con.execute("SELECT count(*) FROM racepace_teammate_race WHERE reasons LIKE '%few_clean_laps%'").fetchone()[0]
    ps_small = con.execute("SELECT count(*) FROM racepace_teammate_pairseason WHERE n_ok_races <= 2").fetchone()[0]
    qcarry = con.execute("SELECT bool_and(n_included IS NOT NULL) FROM quali_teammate_delta_pairseason").fetchone()[0]
    print(f"        race-pace low-reliability comparisons: {low_n:,}; few_clean_laps: {few:,}; "
          f"pair-seasons with <=2 reliable races: {ps_small:,}")
    check("low-reliability comparisons are flagged (not silently averaged)", low_n > 0, str(low_n))
    check("every quali pair-season carries its sample size n", bool(qcarry))
    check("small-sample race-pace pair-seasons are distinguishable (n_ok_races exposed)", ps_small > 0, str(ps_small))

    # ---- GATE 6: comparability-tier distribution + every delta carries a tier
    print("\nGATE 6 — comparability tiers present on every artifact")
    t1 = con.execute("SELECT count(*) FROM quali_teammate_delta_race WHERE tier=1").fetchone()[0]
    t2 = con.execute("SELECT count(*) FROM racepace_teammate_race WHERE tier=2").fetchone()[0]
    t3 = con.execute("SELECT count(*) FROM event_pace WHERE tier=3").fetchone()[0]
    t2ok = con.execute("SELECT count(*) FROM racepace_teammate_race WHERE reliability='ok'").fetchone()[0]
    print(f"        TIER 1 quali comparisons: {t1:,} | TIER 2 race-pace: {t2:,} ({t2ok:,} ok) | TIER 3 events: {t3:,}")
    check("every quali row tagged TIER 1", t1 == con.execute("SELECT count(*) FROM quali_teammate_delta_race").fetchone()[0])
    check("every race-pace row tagged TIER 2", t2 == con.execute("SELECT count(*) FROM racepace_teammate_race").fetchone()[0])
    check("every event row tagged TIER 3", t3 == con.execute("SELECT count(*) FROM event_pace").fetchone()[0])

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE D GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE D GATE: *** FAILED *** — phase blocked.")
        sys.exit(1)
    print("\nPHASE D GATE: *** ALL PASS *** — pace foundation validated. Cleared for Phase E.")


if __name__ == "__main__":
    main()
