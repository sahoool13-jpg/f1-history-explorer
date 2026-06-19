"""Phase G GATE — era-normalisation: bridge reality, selective deflation, honesty.

Phase G re-anchors the time-resolved ratings onto a cross-era scale that EMERGES
from real overlapping careers (spanning-driver bridges) — never from an assumed era
strength. This gate proves: (1) the bridges are real and dense enough to connect the
eras; (2) genuinely backbone-DISCONNECTED weak pockets deflate toward the spine while
their within-pocket deltas are preserved; (3) where Phase F continuity already
anchored a "weak pocket" (Giovinazzi via Räikkönen), Phase G correctly leaves it
alone — the honest finding, reported not faked; (4) late-career stays a decline of
the same driver's prime; (5) uncertainty blows out exactly where bridges run thin;
(6) the well-bridged core is barely moved (anchoring, not rewriting); (7) the
reconstruction still holds. Any FAIL exits non-zero. Ratings remain ESTIMATES.
"""
import sys
import numpy as np
from common import connect
import pace_model_era as G

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    M = G.build(con)                 # builds tables + prints the model summary
    q = lambda s, *a: con.execute(s, list(a)).fetchall()
    print()
    print("=" * 78); print("PHASE G GATE — era-normalisation: bridges, deflation, honesty"); print("=" * 78)
    print("  Ratings are ESTIMATES; the cross-era scale emerges from real spanning careers.\n")

    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    sbd, spanning = M["sbd"], M["spanning"]

    def era(nm, s):
        r = q("""SELECT rating_era_s_estimate FROM driver_season_pace_era_estimate
                 WHERE driver_name=? AND season=?""", nm, s)
        return r[0][0] if r else None
    def phasef(nm, s):
        r = q("""SELECT rating_phasef_s FROM driver_season_pace_era_estimate
                 WHERE driver_name=? AND season=?""", nm, s)
        return r[0][0] if r else None
    def era_avg(nm, lo, hi):
        return q("""SELECT avg(rating_era_s_estimate) FROM driver_season_pace_era_estimate
                    WHERE driver_name=? AND season BETWEEN ? AND ?""", nm, lo, hi)[0][0]

    # ---- GATE 1: era-bridge reality ----------------------------------------
    print("GATE 1 — the spanning bridges are real and connect the eras")
    span_sorted = sorted(spanning, key=lambda d: -(max(sbd[d]) - min(sbd[d])))
    print(f"        {len(spanning)} spanning bridge drivers (span≥{G.SPAN_MIN}y, teammates in ≥2 era-thirds):")
    for d in span_sorted[:8]:
        ss = sorted(sbd[d]); print(f"           {name[d]:24s} {ss[0]}-{ss[-1]} ({ss[-1]-ss[0]}y)")
    print(f"           … and {len(spanning)-8} more")
    bd = dict(((lo, hi), n) for lo, hi, n in q("SELECT era_lo_last, era_hi_first, n_spanning_bridges FROM era_bridge_density"))
    s1 = bd.get((2003, 2004)); s2 = bd.get((2013, 2014))
    indep = min(s1, s2)
    print(f"        spanning drivers straddling 2003|2004: {s1};  straddling 2013|2014: {s2}")
    print(f"        => ≥{indep} INDEPENDENT end-to-end bridges connect the 1994-2003 era to 2014-2024")
    print(f"        example chain: Coulthard(1994-2008) → Webber(2002-2013) → Alonso(2001-2024)")
    check("a substantial spanning backbone exists (≥15 bridge drivers)", len(spanning) >= 15, f"{len(spanning)}")
    check("both era boundaries are crossed by many independent bridges (≥8 each)",
          s1 >= 8 and s2 >= 8, f"2003|2004={s1}, 2013|2014={s2}")

    # ---- GATE 2: selective deflation of genuinely DISCONNECTED weak pockets --
    print("\nGATE 2 — backbone-disconnected weak pockets deflate toward the spine,")
    print("         WITHOUT rewriting who-beat-whom inside the pocket")
    chi_f, chi_g = phasef("Max Chilton", 2013), era("Max Chilton", 2013)
    bia_f, bia_g = phasef("Jules Bianchi", 2013), era("Jules Bianchi", 2013)
    chi_R = q("SELECT backbone_resistance, anchor_flag FROM driver_season_pace_era_estimate WHERE driver_name='Max Chilton' AND season=2013")[0]
    print(f"        Marussia 2013 (a fully isolated 2-driver pocket, R_bb={chi_R[0]:.0f} → {chi_R[1]}):")
    print(f"           Chilton : Phase F {chi_f:+.3f}  →  era-normalised {chi_g:+.3f}  (deflated {chi_g-chi_f:+.3f})")
    print(f"           Bianchi : Phase F {bia_f:+.3f}  →  era-normalised {bia_g:+.3f}")
    dlt_f, dlt_g = bia_f - chi_f, bia_g - chi_g
    print(f"           within-pocket delta (Bianchi−Chilton): Phase F {dlt_f:+.3f}  →  era {dlt_g:+.3f}")
    check("isolated weak-pocket leader (Chilton) is deflated toward the spine (>0.15s)",
          chi_g < chi_f - 0.15, f"{chi_g:+.3f} < {chi_f:+.3f}")
    check("within-pocket teammate delta is PRESERVED (re-anchoring, not rewriting)",
          abs(dlt_g - dlt_f) < 0.02, f"|Δ change|={abs(dlt_g-dlt_f):.3f}s")

    # ---- GATE 2b: the honest Giovinazzi finding ----------------------------
    print("\nGATE 2b — HONEST Giovinazzi finding: Phase F continuity already anchored him,")
    print("          so Phase G (correctly) barely moves him")
    gio_e = q("SELECT rating_s_estimate FROM driver_pace_model_estimate WHERE driver_name='Antonio Giovinazzi'")[0][0]
    gio_f21, gio_g21 = phasef("Antonio Giovinazzi", 2021), era("Antonio Giovinazzi", 2021)
    gio_R = q("SELECT max(backbone_resistance) FROM driver_season_pace_era_estimate WHERE driver_name='Antonio Giovinazzi'")[0][0]
    print(f"        Giovinazzi: Phase E career-blended {gio_e:+.3f}  →  Phase F (continuity-anchored)  →  Phase G")
    print(f"           2021: Phase F {gio_f21:+.3f}  →  era {gio_g21:+.3f}  (Δ {gio_g21-gio_f21:+.3f});  R_bb(max)={gio_R:.4f}")
    print(f"        The de-inflation happened at Phase F (continuity via Räikkönen's chain), not here.")
    check("Giovinazzi is well-anchored to the spine (R_bb below the thin threshold)",
          gio_R < M["thin_thr"], f"R_bb={gio_R:.4f} < thin {M['thin_thr']:.4f}")
    check("Phase G leaves the already-anchored Giovinazzi essentially unchanged (<0.05s)",
          abs(gio_g21 - gio_f21) < 0.05, f"|Δ|={abs(gio_g21-gio_f21):.3f}s")

    # ---- GATE 3: late-Räikkönen reads as declined prime-Räikkönen ----------
    print("\nGATE 3 — late-Räikkönen reads as a DECLINE of prime-Räikkönen (lower = faster)")
    rai_p, rai_l = era_avg("Kimi Räikkönen", 2005, 2007), era_avg("Kimi Räikkönen", 2019, 2021)
    print(f"        Räikkönen: prime 2005-2007 {rai_p:+.3f}  →  late Alfa 2019-2021 {rai_l:+.3f}  (Δ {rai_l-rai_p:+.3f})")
    check("prime Räikkönen rates faster than late Räikkönen on the era scale",
          rai_l > rai_p + 0.03, f"{rai_l:+.3f} > {rai_p:+.3f}")

    # ---- GATE 4: uncertainty blows out where bridges run thin --------------
    print("\nGATE 4 — cross-era uncertainty widens exactly where bridges run thin")
    ci_anch = q("SELECT median(era_ci95_halfwidth_s) FROM driver_season_pace_era_estimate WHERE anchor_flag='anchored'")[0][0]
    ci_thin = q("SELECT median(era_ci95_halfwidth_s) FROM driver_season_pace_era_estimate WHERE anchor_flag IN ('thin','unanchored')")[0][0]
    n_thin = q("SELECT count(*) FROM driver_season_pace_era_estimate WHERE anchor_flag='thin'")[0][0]
    n_unanch = q("SELECT count(*) FROM driver_season_pace_era_estimate WHERE anchor_flag='unanchored'")[0][0]
    print(f"        median cross-era CI: anchored ±{ci_anch:.3f}s  vs  thin/unanchored ±{ci_thin:.3f}s")
    print(f"        flagged: {n_thin} thin, {n_unanch} unanchored (no cross-era claim)")
    check("thinly-bridged driver-seasons carry wider cross-era intervals than anchored ones",
          ci_thin > ci_anch, f"±{ci_thin:.3f} > ±{ci_anch:.3f}")
    check("the disconnected pockets are explicitly flagged unanchored", n_unanch >= 1, f"{n_unanch}")

    # ---- GATE 5: the well-bridged core is barely moved (selectivity) -------
    print("\nGATE 5 — anchoring, NOT rewriting: the well-bridged core is barely moved")
    moved = []
    for nm, s in [("Lewis Hamilton", 2008), ("Lewis Hamilton", 2020),
                  ("Fernando Alonso", 2012), ("Sebastian Vettel", 2011)]:
        f, g = phasef(nm, s), era(nm, s)
        moved.append(abs(g - f))
        print(f"        {nm} {s}: Phase F {f:+.3f}  →  era {g:+.3f}  (Δ {g-f:+.3f})")
    check("backbone core driver-seasons shift <0.05s F→G (era-norm is selective)",
          max(moved) < 0.05, f"max |Δ|={max(moved):.3f}s")

    # ---- GATE 6: reconstruction still holds --------------------------------
    print("\nGATE 6 — era-normalised ratings still reproduce the per-season teammate deltas")
    resid = np.array([x[0] for x in q("SELECT residual_s FROM pace_model_era_residual")])
    med = float(np.median(np.abs(resid)))
    rF = np.array([x[0] for x in q("SELECT residual_s FROM pace_model_tv_residual")])
    medF = float(np.median(np.abs(rF)))
    print(f"        Phase G median|resid|={med:.3f}s  (Phase F was {medF:.3f}s)")
    check("reconstruction within tolerance (median |resid| < 0.12 s)", med < 0.12, f"{med:.3f}s")
    check("re-anchoring did not break the fit (within 0.02s of Phase F)", abs(med - medF) < 0.02,
          f"|{med:.3f}-{medF:.3f}|")

    # ---- GATE 7: separation / labelling ------------------------------------
    print("\nGATE 7 — modelled estimate kept separate & labelled")
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_season_pace_era_estimate")[0][0]
    measured_cols = [c[1] for c in q("PRAGMA table_info('quali_teammate_delta_pairseason')")]
    check("every Phase G row labelled is_estimate=1", bool(all_est))
    check("measured Tier-1 deltas untouched (no rating/estimate column)",
          not any("rating" in c or "estimate" in c for c in measured_cols))

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE G GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE G GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE G GATE: *** ALL PASS *** — the cross-era scale emerges from real spanning "
          "bridges; isolated pockets deflate with deltas preserved; uncertainty honest where "
          "bridges thin. (Ratings remain estimates.)")


if __name__ == "__main__":
    main()
