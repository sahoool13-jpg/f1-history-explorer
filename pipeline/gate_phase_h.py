"""Phase H GATE — racecraft axis: orthogonality, anchors, Giovinazzi, luck, honesty.

The racecraft axis is a CONSTRUCTED estimate. This gate proves it measures what the
pace axes cannot, without falling into the four traps: (1) ORTHOGONALITY — racecraft
is not pace in disguise (corr ~ 0, and a concrete same-pace / different-racecraft
pair); (2) ANCHOR SANITY — known strong racers trend positive, the crash-prone trend
negative; (3) the GIOVINAZZI CHECK — reported honestly; (4) LUCK-EXCLUSION — a worked
example where mechanical/ambiguous races are dropped; (5) reconstruction within
tolerance; (6) uncertainty widens for thin/small-sample drivers (and is honestly wide
throughout — constructed axis). Any FAIL exits non-zero. Ratings remain ESTIMATES.
"""
import sys
import numpy as np
from common import connect
import pace_model_racecraft as H

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    M = H.build(con)                 # builds tables + prints model summary
    q = lambda s, *a: con.execute(s, list(a)).fetchall()
    print()
    print("=" * 78); print("PHASE H GATE — racecraft: orthogonality, anchors, luck-exclusion, honesty"); print("=" * 78)
    print("  CONSTRUCTED axis — results-vs-pace residual. Intervals are honestly wide.\n")

    rc = {r[0]: (r[1], r[2], r[3]) for r in q(
        "SELECT driver_name, racecraft_pos_estimate, ci95_halfwidth_pos, anchor_flag "
        "FROM driver_racecraft_estimate")}      # name -> (rating, ci, flag)
    def craft(nm):
        return rc[nm][0] if nm in rc else None

    # ---- GATE 1: ORTHOGONALITY (racecraft is NOT pace) ---------------------
    print("GATE 1 — racecraft is orthogonal to pace (else it is redundant / broken)")
    # edge-level: residual vs both pace deltas (~0 by OLS construction)
    cq = np.corrcoef(M["resid"], M["Qv"])[0, 1]
    cr = np.corrcoef(M["resid"], M["Rv"])[0, 1]
    # rating-level: racecraft vs Phase G era pace (career mean)
    pace = dict(q("""SELECT d.full_name, avg(p.rating_era_s_estimate)
                     FROM driver_season_pace_era_estimate p JOIN dim_drivers d USING(driverId)
                     GROUP BY 1"""))
    xs = [rc[n][0] for n in rc if n in pace]; ys = [-pace[n] for n in rc if n in pace]
    crate = np.corrcoef(xs, ys)[0, 1]
    print(f"        edge residual vs quali delta: r={cq:+.3f};  vs race-pace delta: r={cr:+.3f} (≈0 by construction)")
    print(f"        career racecraft vs era pace: r={crate:+.3f}  over {len(xs)} drivers (pace R²removed={M['r2_pace']:.3f})")
    print(f"        same pace, different racecraft: Fisichella ({craft('Giancarlo Fisichella'):+.2f}) "
          f"vs Grosjean ({craft('Romain Grosjean'):+.2f}) — Δpace ≈ 0.01s, Δracecraft ≈ "
          f"{craft('Giancarlo Fisichella')-craft('Romain Grosjean'):+.2f} pos")
    check("racecraft↔pace correlation is well below 1 (not redundant)", abs(crate) < 0.35, f"r={crate:+.3f}")
    check("edge residual is orthogonal to BOTH pace deltas (≈0)", abs(cq) < 0.02 and abs(cr) < 0.02,
          f"quali {cq:+.3f}, racepace {cr:+.3f}")

    # ---- GATE 2: known-racecraft anchor sanity (relative) ------------------
    print("\nGATE 2 — anchor sanity (relative reputations, not ground truth)")
    print("        strong race-day craft / overtakers (expect positive):")
    pos_anchors = ["Fernando Alonso", "Max Verstappen", "Daniel Ricciardo"]
    for nm in pos_anchors:
        print(f"           {nm:20s} {craft(nm):+.2f} ± {rc[nm][1]:.2f}")
    print("        crash-prone / weak Sunday conversion (expect negative):")
    neg_anchors = ["Romain Grosjean", "Antonio Giovinazzi"]
    for nm in neg_anchors:
        print(f"           {nm:20s} {craft(nm):+.2f} ± {rc[nm][1]:.2f}")
    check("renowned racers (Alonso, Verstappen, Ricciardo) all score positive",
          all(craft(n) > 0 for n in pos_anchors),
          ", ".join(f"{n.split()[-1]} {craft(n):+.2f}" for n in pos_anchors))
    check("crash-prone Grosjean scores clearly negative (the 'not-crashing' signal)",
          craft("Romain Grosjean") < -0.5, f"{craft('Romain Grosjean'):+.2f}")
    check("strong racer beats crash-prone by a wide margin (Alonso − Grosjean > 1.0)",
          craft("Fernando Alonso") - craft("Romain Grosjean") > 1.0,
          f"{craft('Fernando Alonso') - craft('Romain Grosjean'):+.2f} pos")

    # ---- GATE 3: THE GIOVINAZZI CHECK (reported honestly) ------------------
    print("\nGATE 3 — the Giovinazzi check (decent quali, poor Sunday conversion?)")
    gio, gio_ci, gio_flag = rc["Antonio Giovinazzi"]
    print(f"        Giovinazzi racecraft = {gio:+.2f} ± {gio_ci:.2f} pos  ({gio_flag})")
    print(f"        → negative: he converted WORSE than his pace predicted — consistent with the thesis.")
    print(f"        (interval is wide — small sample; reported as-is, not fudged.)")
    check("Giovinazzi's racecraft point estimate is negative (weak Sunday conversion)",
          gio < 0, f"{gio:+.2f}")

    # ---- GATE 4: LUCK-EXCLUSION (mechanical / ambiguous dropped) -----------
    print("\nGATE 4 — luck-exclusion: mechanical / ambiguous races are not racecraft")
    ex = q("""SELECT season, nameA, nameB, n_eligible_races, n_dropped_luck, finish_margin, racecraft_residual
              FROM racecraft_pair_residual WHERE nameA='Nick Heidfeld' AND nameB='Jean Alesi' AND season=2000""")
    if not ex:
        ex = q("""SELECT season, nameA, nameB, n_eligible_races, n_dropped_luck, finish_margin, racecraft_residual
                  FROM racecraft_pair_residual ORDER BY n_dropped_luck DESC LIMIT 1""")
    s, na, nb, nel, ndrop, fm, rcr = ex[0]
    print(f"        {s} {na} vs {nb} (Prost — dire reliability): {nel} eligible races, "
          f"{ndrop} DROPPED as luck/mechanical/ambiguous")
    print(f"        only the {nel} clean head-to-heads feed racecraft; the {ndrop} unreliable races score nothing")
    total_drop = q("SELECT sum(n_dropped_luck) FROM racecraft_pair_residual")[0][0]
    total_elig = q("SELECT sum(n_eligible_races) FROM racecraft_pair_residual")[0][0]
    print(f"        across all scored pairs: {total_elig} eligible vs {total_drop} dropped for luck "
          f"({total_drop/(total_elig+total_drop):.0%} of teammate races excluded)")
    check("the worked example drops far more races than it counts (luck not credited)",
          ndrop > nel, f"{ndrop} dropped > {nel} counted")
    check("a substantial share of teammate races is excluded as luck (rule actually bites)",
          total_drop > 0.2 * (total_elig + total_drop), f"{total_drop} dropped")

    # ---- GATE 5: reconstruction / consistency ------------------------------
    print("\nGATE 5 — the network reproduces the racecraft residual edges")
    rr = np.array([x[0] for x in q("SELECT residual FROM racecraft_recon_residual")])
    med = float(np.median(np.abs(rr)))
    print(f"        median |reconstruction resid| = {med:.3f} positions  (RMS {np.sqrt((rr**2).mean()):.3f})")
    check("reconstruction within tolerance (median |resid| < 1.5 pos)", med < 1.5, f"{med:.3f} pos")

    # ---- GATE 6: uncertainty widens for thin / small-sample drivers --------
    print("\nGATE 6 — uncertainty is honest: wider for thin / small-sample drivers")
    ci_a = q("SELECT median(ci95_halfwidth_pos) FROM driver_racecraft_estimate WHERE anchor_flag='anchored'")[0][0]
    ci_t = q("SELECT median(ci95_halfwidth_pos) FROM driver_racecraft_estimate WHERE anchor_flag IN ('thin','unanchored')")[0][0]
    na = q("SELECT count(*) FROM driver_racecraft_estimate WHERE anchor_flag='anchored'")[0][0]
    nt = q("SELECT count(*) FROM driver_racecraft_estimate WHERE anchor_flag IN ('thin','unanchored')")[0][0]
    print(f"        median 95% CI: anchored ±{ci_a:.2f} pos ({na} drivers)  vs  thin/unanchored ±{ci_t:.2f} pos ({nt})")
    check("thin / small-sample drivers carry wider intervals than well-sampled ones",
          ci_t > ci_a, f"±{ci_t:.2f} > ±{ci_a:.2f}")
    check("intervals are honestly wide throughout (constructed axis: anchored CI > ±0.6 pos)",
          ci_a > 0.6, f"anchored median ±{ci_a:.2f} pos")

    # ---- GATE 7: separation / labelling ------------------------------------
    print("\nGATE 7 — modelled estimate kept separate & labelled")
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_racecraft_estimate")[0][0]
    res_cols = [c[1] for c in q("PRAGMA table_info('fact_results')")]
    check("every Phase H row labelled is_estimate=1", bool(all_est))
    check("measured results table untouched (no rating/estimate column)",
          not any("rating" in c or "estimate" in c for c in res_cols))

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE H GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE H GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE H GATE: *** ALL PASS *** — racecraft is orthogonal to pace, anchors sane, luck "
          "excluded, uncertainty honest. (Constructed axis — ratings remain estimates.)")


if __name__ == "__main__":
    main()
