"""Phase B GATE — reconcile all three features to known F1 truths.

Each feature has its OWN gate. The MASTER check (Feature 1a: own-system
recomputation reproduces the real champion for ALL seasons) is the most
important — any failure is printed loudly. Any FAIL exits non-zero.
"""
import sys
from common import connect
from points_systems import (
    SEASON_TABLE, POINTS_TABLES, dropped_rule, apply_dropped, FLAGGED_SEASONS,
)
from feature1_points_invariance import (
    load_perrace, actual_champions, faithful_champion, champion_under_table,
)

RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append((name, bool(passed)))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    q1 = lambda s, *a: con.execute(s, list(a)).fetchone()
    name = lambda d: con.execute("SELECT full_name FROM dim_drivers WHERE driverId=?", [d]).fetchone()[0]

    print("=" * 78)
    print("PHASE B GATE — reconciliation to known F1 truths")
    print("=" * 78)

    real_pts, finish = load_perrace(con)
    actual = actual_champions(con)

    # =================================================== FEATURE 1
    print("\nFEATURE 1 — points-system invariance")

    # (1a) MASTER: own-system recomputation reproduces the real champion, ALL seasons
    champ_mismatches, total_mismatches = [], []
    official_tot = {}
    for s, rnd, d, p in con.execute("""
        WITH finals AS (SELECT season, max(round) mr FROM fact_races GROUP BY season)
        SELECT r.season, r.round, ds.driverId, ds.points
        FROM driver_standings ds JOIN fact_races r USING (raceId)
        JOIN finals f ON f.season=r.season AND f.mr=r.round
    """).fetchall():
        official_tot.setdefault(s, {})[d] = p
    for season in sorted(actual):
        champ, _, totals = faithful_champion(real_pts[season], season)
        if champ != actual[season][0]:
            champ_mismatches.append((season, name(champ), name(actual[season][0])))
        # totals reconciliation (per driver)
        off = official_tot[season]
        if any(abs(totals.get(d, 0.0) - off[d]) > 1e-6 for d in off):
            total_mismatches.append(season)

    print("  -- MASTER CHECK (own historical system must reproduce the real champion) --")
    if champ_mismatches:
        print("  *** CHAMPION MISMATCHES (loud failure): ***")
        for s, got, exp in champ_mismatches:
            print(f"      {s}: recomputed {got} != real {exp}")
    check("Own-system recomputation reproduces the REAL champion for ALL 75 seasons",
          not champ_mismatches, f"{len(actual)-len(champ_mismatches)}/{len(actual)} seasons")

    unexpected = [s for s in total_mismatches if s not in FLAGGED_SEASONS]
    check("Own-system reproduces official TOTALS for all unflagged seasons",
          not unexpected,
          f"{len(actual)-len(total_mismatches)}/{len(actual)} exact; "
          f"flagged={sorted(FLAGGED_SEASONS)}; unexpected={unexpected}")

    # points-table catalogue validation: modal results.points at each finish position == table
    cat_bad = []
    for season in sorted(actual):
        tk = SEASON_TABLE[season]
        vec = POINTS_TABLES[tk]["points"]
        for pos in range(1, len(vec) + 1):
            row = q1("""
                SELECT mode(CAST(r.points AS DOUBLE))
                FROM results r JOIN fact_races ra USING (raceId)
                WHERE ra.season=? AND CAST(r.position AS INT)=?
            """, season, pos)
            modal = row[0] if row else None
            if modal is None:
                continue
            # winner may carry +1 FL in FL eras; accept base or base+1 at P1 only
            ok = (modal == vec[pos - 1]) or (pos == 1 and POINTS_TABLES[tk]["fl_rule"] != "none"
                                             and modal == vec[pos - 1] + 1)
            if not ok:
                cat_bad.append((season, pos, modal, vec[pos - 1]))
    check("Points-table catalogue matches observed per-position points (modal)",
          not cat_bad, f"{len(cat_bad)} position-mismatches" if cat_bad else "all eras match")

    # (1b) 1988 dropped-scores spot-check
    s = 1988
    _, _, nodrop = champion_under_table(finish[s], SEASON_TABLE[s])
    _, _, drop = faithful_champion(real_pts[s], s)
    nd_champ = max(nodrop, key=lambda d: nodrop[d])
    dr_champ = max(drop, key=lambda d: drop[d])
    check("1988: best-11 (real) champion is Senna", "Senna" in name(dr_champ), name(dr_champ))
    check("1988: total-points (no drop) champion would be Prost", "Prost" in name(nd_champ), name(nd_champ))

    # =================================================== FEATURE 2
    print("\nFEATURE 2 — clinch geometry")
    clinch = {r[0]: r for r in con.execute("""
        SELECT season, clinch_round, total_rounds, races_remaining_at_clinch, went_to_finale, clinch_race
        FROM f1_clinch
    """).fetchall()}
    c08 = clinch[2008]; check("2008 title decided at the FINAL race",
                              c08[4] and c08[1] == c08[2], f"clinch R{c08[1]} of {c08[2]} ({c08[5]})")
    c21 = clinch[2021]; check("2021 title decided at the FINAL race",
                              c21[4] and c21[1] == c21[2], f"clinch R{c21[1]} of {c21[2]} ({c21[5]})")
    c02 = clinch[2002]; check("2002 Schumacher early clinch: round 11, 6 races to spare",
                              c02[1] == 11 and c02[3] == 6 and not c02[4],
                              f"clinch R{c02[1]} ({c02[5]}), {c02[3]} to spare")

    # =================================================== FEATURE 3
    print("\nFEATURE 3 — teammate-adjusted champions")
    r16 = q1("""SELECT champ_quali_wins, champ_quali_losses, champ_race_wins, champ_race_losses
                FROM f1_champion_teammate WHERE season=2016""")
    # cross-check against Phase A teammate spine directly (no divergence allowed)
    a16 = q1("""
        SELECT t.quali_wins, t.quali_losses, t.race_wins, t.race_losses
        FROM teammate_pair_season_directed t JOIN dim_drivers d ON d.driverId=t.driverId
        JOIN dim_constructors c USING (constructorId)
        WHERE t.season=2016 AND d.full_name LIKE '%Rosberg%' AND c.constructor_name='Mercedes'
    """)
    check("2016 champion Rosberg was OUT-QUALIFIED by teammate Hamilton",
          r16[0] < r16[1], f"quali {r16[0]}-{r16[1]}")
    check("Feature 3 ties back to Phase A teammate spine exactly (no divergence)",
          tuple(r16) == tuple(a16), f"F3={tuple(r16)} PhaseA={tuple(a16)}")
    dom = q1("""SELECT champion, champ_quali_wins, champ_quali_losses, teammates
                FROM f1_champion_teammate WHERE season=2013""")
    check("Dominant case: 2013 champion Vettel crushed teammate in qualifying",
          dom[1] > dom[2] and (dom[1] - dom[2]) >= 10, f"{dom[0]} quali {dom[1]}-{dom[2]} vs {dom[3]}")

    # =================================================== SUMMARY
    print("\n" + "=" * 78)
    n_pass = sum(1 for _, p in RESULTS if p)
    n_fail = len(RESULTS) - n_pass
    print(f"PHASE B GATE SUMMARY: {n_pass} PASS / {n_fail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if n_fail:
        print("\nPHASE B GATE: *** FAILED *** — phase blocked.")
        sys.exit(1)
    print("\nPHASE B GATE: *** ALL PASS *** — Phase B validated. Cleared for Phase C.")


if __name__ == "__main__":
    main()
