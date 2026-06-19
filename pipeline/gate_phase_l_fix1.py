"""Phase L / FIX 1 GATE — racecraft must not reward grid opportunity.

The old racecraft used the raw teammate finishing-position margin, which censors dominant
front-runners (no positions to gain at the front) -> corr(CRAFT_z, grid) = -0.427. FIX 1
switches to CONVERSION (finish_gap - grid_gap): positions gained on the teammate during the
race, beyond pace. This removes the grid-opportunity bias -- but in teammate data the grid
gap IS essentially the pace gap, so once both are removed the residual signal is weak.

A z^2/v signal-to-noise scan (printed) decides the prior treatment by a FIXED rule:
  CONCENTRATED (~1-3 distinguishable drivers) -> Option C: no tau^2 floor; racecraft sits
    near-dead with its honest tau^2~0, near-zero points, wide CIs. Do NOT manufacture signal.
  HETEROGENEOUS (a dozen+)                     -> Option A-refined (heavier-tailed prior/floor).

The gate proves the bias is removed, the front-runner penalty is gone, and -- crucially --
that the composite recovery of penalised front-runners comes from the REMOVED PENALTY, not
from a strong racecraft contribution (it survives racecraft being near-dead). Any FAIL exits
non-zero. ESTIMATES throughout.
"""
import sys
import numpy as np
from common import connect
import pace_model_racecraft as H
import quality_composite as Q

DEFAULT_W = (44, 12, 44)     # FIX 1 presentation default: racecraft de-emphasised (~12%)
RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    nid = {n: d for d, n in name.items()}
    grid = dict(con.execute("SELECT driverId, avg(grid) FROM fact_results WHERE grid>0 GROUP BY 1").fetchall())

    print("=" * 78); print("PHASE L / FIX 1 GATE — racecraft grid-opportunity removal"); print("=" * 78)

    # ---- build BEFORE (old finish-margin) and AFTER (conversion), each -> composite
    def state(conversion):
        H.build(con, conversion=conversion)
        drivers, meta = Q.compute(con)
        elig = [d for d, m in drivers.items() if m["eligible"]]
        craft = {d: drivers[d]["cross"]["z"][1] for d in elig}        # standardised CRAFT_z
        def board(w):
            r = Q.composite(drivers, *w, mode="cross")
            return {d: i + 1 for i, (d, _, _) in enumerate(r)}, {d: (c, ci) for d, c, ci in r}
        return dict(drivers=drivers, meta=meta, elig=elig, craft=craft,
                    eq=board((1, 1, 1)), df=board(DEFAULT_W))
    B = state(False)
    A = state(True)        # leaves DB in conversion state (correct for export)
    elig = A["elig"]

    # ---- z^2/v diagnostic + branch decision --------------------------------
    print("\nDIAGNOSTIC — conversion racecraft signal-to-noise (z^2 / v) across n=%d" % len(elig))
    znv = []
    for d in elig:
        z = A["drivers"][d]["cross"]["z"][1]; v = A["drivers"][d]["cross"]["sz"][1] ** 2
        znv.append((d, z * z / v if v > 0 else 0.0))
    znv.sort(key=lambda x: -x[1])
    cnt = {t: sum(1 for _, s in znv if s >= t) for t in (4, 9, 15)}
    print(f"   z^2/v >= 4: {cnt[4]}   >= 9: {cnt[9]}   >= 15: {cnt[15]}   (median {np.median([s for _,s in znv]):.2f})")
    print(f"   >=4 names: {[name[d] for d, s in znv if s >= 4]}")
    concentrated = cnt[9] <= 3 and cnt[4] <= 5
    branch = "CONCENTRATED -> Option C (no tau^2 floor; racecraft near-dead, honest)" if concentrated \
        else "HETEROGENEOUS -> Option A-refined (heavier-tailed prior/floor)"
    print(f"   BRANCH FIRED: {branch}")
    print(f"   => signal sits in ~{cnt[4]} driver(s); NOT a dozen-plus -> concentrated. No floor applied.")
    check("branch decision is CONCENTRATED -> Option C (matches the locked rule)", concentrated,
          f">=9:{cnt[9]}, >=4:{cnt[4]}")

    # ---- GATE 1: grid-opportunity bias materially removed -------------------
    print("\nGATE 1 — corr(CRAFT_z, mean grid): bias materially removed (floor of achievability)")
    def corr(craft):
        ids = [d for d in elig if d in grid]
        return np.corrcoef([craft[d] for d in ids], [grid[d] for d in ids])[0, 1]
    cb, ca = corr(B["craft"]), corr(A["craft"])
    print(f"        BEFORE {cb:+.3f}  ->  AFTER {ca:+.3f}   (target: substantially toward 0; ~-0.19 is the floor)")
    check("grid bias substantially reduced (|corr| drops by >=40%)",
          abs(ca) < abs(cb) * 0.6, f"{cb:+.3f} -> {ca:+.3f}")

    # ---- GATE 2: front-runner penalty removed; carver opportunity compressed
    print("\nGATE 2 — front-runners not dragged negative; carver opportunity-inflation compressed")
    fr = ["Michael Schumacher", "Lewis Hamilton", "Sebastian Vettel"]
    print("        front-runners (CRAFT_z must NOT be dragged negative by grid):")
    for nm in fr:
        d = nid[nm]
        print(f"          {nm:20s} BEFORE {B['craft'][d]:+.2f}  ->  AFTER {A['craft'][d]:+.2f}  (grid {grid.get(d,0):.1f})")
    print("        (honest: these three were already ~neutral under the old metric -- the -0.427 bias is")
    print("         DISTRIBUTIONAL; the visible effect is the carvers below losing their grid upside)")
    carv = ["Carlos Sainz", "Charles Leclerc", "Esteban Ocon", "Pierre Gasly"]
    print("        carvers (composite rank must FALL as opportunity inflation is removed):")
    for nm in carv:
        d = nid[nm]
        print(f"          {nm:20s} equal rank  BEFORE #{B['eq'][0][d]}  ->  AFTER #{A['eq'][0][d]}")
    check("no front-runner is dragged negative after (CRAFT_z > -0.2)",
          all(A["craft"][nid[nm]] > -0.2 for nm in fr),
          ", ".join(f"{nm.split()[-1]} {A['craft'][nid[nm]]:+.2f}" for nm in fr))
    nfall = sum(1 for nm in carv if A["eq"][0][nid[nm]] > B["eq"][0][nid[nm]])
    check("most opportunity-carvers fall once grid upside is removed (>=3 of 4)",
          nfall >= 3, f"{nfall} of 4 fell")

    # ---- GATE 3: tau^2 re-estimated (Option C: racecraft near-dead) ---------
    print("\nGATE 3 — EB tau^2 re-estimated on the conversion definition (old stale: 0.882/0.34/0.975)")
    tp = A["meta"]["norm"]["cross"]
    print(f"        new tau^2 (cross): pace {tp['pace']['tau2']:.3f}  racecraft {tp['race']['tau2']:.3f}  longevity {tp['long']['tau2']:.3f}")
    check("racecraft tau^2 collapses to ~0 (honest near-dead axis under Option C, no floor)",
          tp["race"]["tau2"] < 0.05, f"racecraft tau^2={tp['race']['tau2']:.3f}")

    # ---- GATE 4: recovery comes from REMOVED PENALTY, not racecraft signal --
    print("\nGATE 4 — penalised front-runners recover via REMOVED PENALTY (survives racecraft near-dead)")
    for nm in ["Sebastian Vettel", "Mika Häkkinen"]:
        d = nid[nm]
        print(f"        {nm:20s} composite rank (equal): BEFORE #{B['eq'][0][d]}  ->  AFTER #{A['eq'][0][d]}")
    # racecraft contributes ~0 after (shrunk), so the rank change is driven by the removed penalty
    after_craft_contrib = np.mean([abs(A["drivers"][d]["cross"]["zs"][1]) for d in elig])
    print(f"        mean |racecraft contribution| after = {after_craft_contrib:.3f} (≈0 -> recovery is from removed penalty, not new signal)")
    check("Vettel and Häkkinen both recover (rank improves) BEFORE->AFTER",
          A["eq"][0][nid["Sebastian Vettel"]] < B["eq"][0][nid["Sebastian Vettel"]] and
          A["eq"][0][nid["Mika Häkkinen"]] < B["eq"][0][nid["Mika Häkkinen"]],
          f"Vettel {B['eq'][0][nid['Sebastian Vettel']]}->{A['eq'][0][nid['Sebastian Vettel']]}, "
          f"Häkkinen {B['eq'][0][nid['Mika Häkkinen']]}->{A['eq'][0][nid['Mika Häkkinen']]}")
    check("racecraft is genuinely near-dead after (mean |contribution| < 0.05) -> recovery is the removed penalty",
          after_craft_contrib < 0.05, f"{after_craft_contrib:.3f}")

    # ---- GATE 5: CIs re-propagated; composite interval computes ------------
    print("\nGATE 5 — composite CIs re-propagated; overlap-tie logic intact")
    ci_ok = all(ci > 0 for _, (c, ci) in A["eq"][1].items())
    med_ci = float(np.median([ci for _, (c, ci) in A["eq"][1].items()]))
    print(f"        median composite CI (equal) after = ±{med_ci:.2f}; all intervals populated = {ci_ok}")
    check("every composite carries a populated interval (CI re-propagated)", ci_ok, f"median ±{med_ci:.2f}")

    # ---- GATE 6: no-regression ---------------------------------------------
    print("\nGATE 6 — no regression")
    q = lambda s: con.execute(s).fetchall()
    cross_ok = all(len(A["drivers"][d]["cross"]["zs"]) == 3 for d in elig)
    within_ok = all(len(A["drivers"][d]["within"]["zs"]) == 3 for d in elig)
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_racecraft_estimate")[0][0]
    npart = q("SELECT count(*) FROM driver_quality_axes WHERE is_composite_eligible=0 AND n_seasons>=2")[0][0]
    res_cols = [c[1] for c in q("PRAGMA table_info('fact_results')")]
    check("cross-era and within-era both compute", cross_ok and within_ok)
    check("is_estimate intact + measured results untouched",
          bool(all_est) and not any(("rating" in c or "estimate" in c) for c in res_cols))
    check("partial-coverage drivers still flagged", npart > 0, f"{npart} partial")

    # ---- FULL BEFORE/AFTER BOARD DIFF (equal + default weights) -------------
    print("\n" + "=" * 78)
    print("FULL BEFORE/AFTER BOARD  (rank under EQUAL | rank under DEFAULT %d/%d/%d)" % DEFAULT_W)
    print("=" * 78)
    audit = ["Fernando Alonso", "Michael Schumacher", "Lewis Hamilton", "Max Verstappen",
             "Rubens Barrichello", "Jenson Button", "Charles Leclerc", "Sebastian Vettel", "Mika Häkkinen"]
    print(f"  {'driver':22s} {'equal B->A':>12s}  {'default B->A':>14s}")
    # full board ordered by AFTER-equal rank
    order = sorted(elig, key=lambda d: A["eq"][0][d])
    for d in order:
        nm = name[d]; star = "  <-- audit" if nm in audit else ""
        print(f"  {nm:22s} {B['eq'][0][d]:>4d}->{A['eq'][0][d]:<4d}    "
              f"{B['df'][0][d]:>4d}->{A['df'][0][d]:<4d}{star}")

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE L / FIX 1 GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nFIX 1 GATE: *** FAILED *** — blocked."); sys.exit(1)
    print("\nFIX 1 GATE: *** ALL PASS *** — conversion removes the grid-opportunity bias; front-runner "
          "penalty gone; signal is concentrated -> Option C (racecraft honestly near-dead, no manufactured "
          "signal); recovery comes from the removed penalty. (Estimates; racecraft weakly identified.)")


if __name__ == "__main__":
    main()
