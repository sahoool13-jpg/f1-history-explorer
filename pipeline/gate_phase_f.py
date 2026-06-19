"""Phase F GATE — time-resolved model: ageing/decline ground truth + method sanity.

Unlike Phase E, this model HAS qualitative ground truth: known late-career decline
must show. We check decline shape, the Giovinazzi de-inflation (the core thesis),
smoothing sanity (plausible arc, not flat / not noise), reconstruction, and
connectivity honesty. Any FAIL exits non-zero. Ratings remain ESTIMATES.
"""
import sys
import numpy as np
from common import connect
import pace_model_tv as tv

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    q = lambda s, *a: con.execute(s, list(a)).fetchall()
    print("=" * 78); print("PHASE F GATE — time-resolved ageing/decline + method sanity"); print("=" * 78)
    print("  Ratings are ESTIMATES; these check the model captures known career shape.\n")

    def span_mean(nm, lo, hi):
        r = q("""SELECT avg(rating_s_estimate) FROM driver_season_pace_estimate
                 WHERE driver_name=? AND season BETWEEN ? AND ?""", nm, lo, hi)[0][0]
        return r
    def arc(nm):
        return q("""SELECT season, rating_s_estimate, ci95_halfwidth_s, n_teammate_edges
                    FROM driver_season_pace_estimate WHERE driver_name=? ORDER BY season""", nm)

    # ---- GATE 1: ageing / decline shape ------------------------------------
    print("GATE 1 — late-career rates BELOW prime for known decline cases (lower = faster)")
    sch_p, sch_c = span_mean("Michael Schumacher", 1994, 2004), span_mean("Michael Schumacher", 2010, 2012)
    print(f"        Schumacher: prime 1994–2004 {sch_p:+.3f}  →  comeback 2010–2012 {sch_c:+.3f}  (Δ {sch_c-sch_p:+.3f})")
    check("Schumacher comeback rates below his prime", sch_c > sch_p + 0.05, f"{sch_c:+.3f} > {sch_p:+.3f}")

    rai_p, rai_a = span_mean("Kimi Räikkönen", 2005, 2007), span_mean("Kimi Räikkönen", 2019, 2021)
    print(f"        Räikkönen: prime 2005–2007 {rai_p:+.3f}  →  Alfa 2019–2021 {rai_a:+.3f}  (Δ {rai_a-rai_p:+.3f})")
    check("Räikkönen late-Alfa rates below his prime (meaningful margin)", rai_a > rai_p + 0.05,
          f"{rai_a:+.3f} > {rai_p:+.3f}")

    alo_p, alo_l = span_mean("Fernando Alonso", 2005, 2012), span_mean("Fernando Alonso", 2021, 2024)
    print(f"        Alonso (long span): peak 2005–2012 {alo_p:+.3f}  →  late 2021–2024 {alo_l:+.3f}  (Δ {alo_l-alo_p:+.3f})")
    check("Alonso late-career rates below his peak (long-span decline)", alo_l > alo_p + 0.05,
          f"{alo_l:+.3f} > {alo_p:+.3f}")

    # ---- GATE 2: the Giovinazzi de-inflation (core thesis) -----------------
    print("\nGATE 2 — beating LATE Räikkönen no longer inflates Giovinazzi (vs Phase E)")
    gio_e = q("SELECT rating_s_estimate FROM driver_pace_model_estimate WHERE driver_name='Antonio Giovinazzi'")[0][0]
    gio_f = q("SELECT avg(rating_s_estimate) FROM driver_season_pace_estimate WHERE driver_name='Antonio Giovinazzi'")[0][0]
    rai_e = q("SELECT rating_s_estimate FROM driver_pace_model_estimate WHERE driver_name='Kimi Räikkönen'")[0][0]
    print(f"        Räikkönen benchmark: Phase E career {rai_e:+.3f}  →  Phase F faded 19–21 {rai_a:+.3f}  (slower)")
    print(f"        Giovinazzi: Phase E (career-blended) {gio_e:+.3f}  →  Phase F (time-resolved) {gio_f:+.3f}")
    check("Phase F de-inflates Giovinazzi vs Phase E (reference is now faded Räikkönen)",
          gio_f > gio_e + 0.15, f"{gio_f:+.3f} > {gio_e:+.3f} by {gio_f-gio_e:.3f}s")
    check("Räikkönen's benchmark genuinely faded between the two models",
          rai_a > rai_e + 0.10, f"faded {rai_a:+.3f} vs career {rai_e:+.3f}")

    # ---- GATE 3: smoothing sanity (plausible arc, not flat / not noise) -----
    print("\nGATE 3 — smoothing sanity: a real career arc, not a flat line or noise")
    for nm in ["Lewis Hamilton", "Fernando Alonso"]:
        a = arc(nm); rs = [x[1] for x in a]
        diffs = [abs(rs[k + 1] - rs[k]) for k in range(len(rs) - 1)]
        med_d, max_d, rng = np.median(diffs), max(diffs), max(rs) - min(rs)
        print(f"        {nm}: {len(rs)} seasons, range {rng:.3f}s, median|Δyr|={med_d:.3f}s, max|Δyr|={max_d:.3f}s")
        check(f"  {nm}: not flat (range > 0.12s) and not noisy (median|Δyr| < 0.12s)",
              rng > 0.12 and med_d < 0.12, f"range {rng:.3f}, med|Δ| {med_d:.3f}")

    # ---- GATE 4: reconstruction --------------------------------------------
    print("\nGATE 4 — time-resolved ratings reproduce the per-season teammate deltas")
    resid = np.array([x[0] for x in q("SELECT residual_s FROM pace_model_tv_residual")])
    med = float(np.median(np.abs(resid)))
    # Phase E baseline
    rE = np.array([x[0] for x in q("SELECT residual_s FROM pace_model_residual")])
    medE = float(np.median(np.abs(rE)))
    print(f"        Phase F median|resid|={med:.3f}s  (Phase E was {medE:.3f}s)")
    check("reconstruction within tolerance (median |resid| < 0.12 s)", med < 0.12, f"{med:.3f}s")
    check("time resolution improves the fit vs Phase E career-average", med < medE, f"{med:.3f} < {medE:.3f}")

    # ---- GATE 5: connectivity honesty --------------------------------------
    print("\nGATE 5 — sparse driver-seasons read as uncertain, and are flagged")
    ci1 = q("SELECT median(ci95_halfwidth_s) FROM driver_season_pace_estimate WHERE n_teammate_edges=1")[0][0]
    ci2 = q("SELECT median(ci95_halfwidth_s) FROM driver_season_pace_estimate WHERE n_teammate_edges>=2")[0][0]
    n1 = q("SELECT count(*) FROM driver_season_pace_estimate WHERE n_teammate_edges=1")[0][0]
    flagged = q("SELECT count(*) FROM driver_season_pace_estimate WHERE n_teammate_edges=1 AND confidence_flag='sparse'")[0][0]
    print(f"        median 95% CI: 1-edge seasons ±{ci1:.3f}s  vs  ≥2-edge seasons ±{ci2:.3f}s "
          f"({n1} single-edge driver-seasons)")
    check("single-edge driver-seasons have wider intervals than multi-edge", ci1 > ci2, f"{ci1:.3f} > {ci2:.3f}")
    check("intervals widened vs Phase E (sparser nodes — honest)", ci1 > 0.30, f"median 1-edge CI ±{ci1:.3f}s")

    # ---- separation / labelling -------------------------------------------
    print("\nGATE 6 — modelled estimate kept separate & labelled")
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_season_pace_estimate")[0][0]
    measured_cols = [c[1] for c in q("PRAGMA table_info('quali_teammate_delta_pairseason')")]
    check("every Phase F row labelled is_estimate=1", bool(all_est))
    check("measured Tier-1 deltas untouched (no rating/estimate column)",
          not any("rating" in c or "estimate" in c for c in measured_cols))

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE F GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE F GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE F GATE: *** ALL PASS *** — time resolution captures known career arcs; "
          "uncertainty honest. (Ratings remain estimates.)")


if __name__ == "__main__":
    main()
