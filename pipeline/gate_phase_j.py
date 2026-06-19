"""Phase J GATE — combination: no-fixed-weighting, the Giovinazzi test, uncertainty.

The composite is only honest if (1) there is NO hard-coded official ranking — it genuinely
responds to the user's weights (different weightings → different top-10s); (2) the GIOVINAZZI
TEST holds — pure pace flatters him, the full picture sinks him; (3) overlapping composite
intervals read as not-separable, never falsely ordered; (4) the balanced top is credible; and
(5) drivers missing an axis are flagged, not mishandled. Any FAIL exits non-zero. ESTIMATES.
"""
import sys
import numpy as np
from common import connect
import quality_composite as J

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    drivers, meta = J.build(con)
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    gio = [d for d, n in name.items() if n == "Antonio Giovinazzi"][0]
    print()
    print("=" * 78); print("PHASE J GATE — combination: no fixed weighting, Giovinazzi, uncertainty"); print("=" * 78)
    print("  Composite is a FUNCTION of user weights — there is no official ranking.\n")

    WEIGHTINGS = {
        "balanced":        (1, 1, 1),
        "pace-heavy":      (3, 0.5, 0.5),
        "racecraft-heavy": (0.5, 3, 0.5),
        "longevity-heavy": (0.5, 0.5, 3),
        "pace-ONLY":       (1, 0, 0),
    }
    res = {tag: J.composite(drivers, *w) for tag, w in WEIGHTINGS.items()}
    rankmap = {tag: {d: i + 1 for i, (d, _, _) in enumerate(r)} for tag, r in res.items()}
    nelig = len(res["balanced"])

    def top(tag, k=10):
        return [name[d] for d, _, _ in res[tag][:k]]

    # ---- GATE 1: no fixed weighting — the LIVE axes move the board ----------
    # NOTE (post Phase-L FIX 1, Option C): racecraft is honestly NEAR-DEAD (tau^2~0), so
    # racecraft-heavy ~= balanced -- the slider is inert because the axis has no signal to
    # weight. That is the correct Option-C signature, not a regression. We therefore test
    # that the LIVE axes (pace, longevity) genuinely move the board.
    print("GATE 1 — no fixed weighting: the LIVE axes (pace, longevity) move the board")
    for tag in ["balanced", "pace-heavy", "longevity-heavy"]:
        print(f"        {tag:16s} top-5: " + ", ".join(n.split()[-1] for n in top(tag, 5)))
    diff_bp = len(set(top("balanced")) ^ set(top("pace-heavy")))
    diff_bl = len(set(top("balanced")) ^ set(top("longevity-heavy")))
    diff_br = len(set(top("balanced")) ^ set(top("racecraft-heavy")))
    print(f"        racecraft-heavy vs balanced: {diff_br} members differ  (≈0 EXPECTED — racecraft is near-dead under Option C)")
    check("pace-heavy top-10 differs from balanced", top("pace-heavy") != top("balanced"), f"{diff_bp} members differ")
    check("longevity-heavy top-10 differs from balanced", top("longevity-heavy") != top("balanced"), f"{diff_bl} members differ")
    check("the live axes genuinely move the board (pace & longevity)", diff_bp >= 1 and diff_bl >= 1,
          f"Δpace {diff_bp}, Δlong {diff_bl}")

    # ---- GATE 2: THE GIOVINAZZI TEST (re-anchored to the live axes) ---------
    # Post FIX 1 the thesis is no longer "racecraft sinks him" (racecraft is near-dead).
    # It is now carried by the live axes: pure pace flatters him; LONGEVITY (a short,
    # uncompetitive career) is what sinks him.
    print("\nGATE 2 — the Giovinazzi test: pure pace flatters; the full picture (longevity) sinks him")
    r_pace = rankmap["pace-ONLY"][gio]
    r_bal = rankmap["balanced"][gio]
    r_long = rankmap["longevity-heavy"][gio]
    print(f"        Giovinazzi rank of {nelig}:  pace-ONLY #{r_pace}   balanced #{r_bal}   longevity-heavy #{r_long}")
    print(f"        → he can qualify (#{r_pace}); weight the sustained career and he falls to #{r_long}.")
    print(f"        'decent qualifier, didn't sustain' — racecraft no longer part of the story (near-dead).")
    check("Giovinazzi drops far from pace-only to the full picture (pace is his one strong axis)",
          r_pace <= r_long - 18, f"#{r_pace} pace-only vs #{r_long} longevity-heavy (drop {r_long-r_pace})")
    check("weighting the sustained career puts Giovinazzi in the bottom ~third", r_long > 0.6 * nelig,
          f"#{r_long} of {nelig} under longevity-heavy")

    # ---- GATE 3: uncertainty — overlapping composites read as not-separable -
    print("\nGATE 3 — overlapping composite intervals are NOT falsely ordered")
    rh = res["racecraft-heavy"]
    (d0, c0, ci0) = rh[0]
    # how many drivers below the nominal #1 does its interval still overlap?
    sep_idx = next((i for i in range(1, len(rh)) if c0 - ci0 > rh[i][1] + rh[i][2]), None)
    n_overlap_top = (sep_idx - 1) if sep_idx else len(rh) - 1
    print(f"        racecraft-heavy nominal #1: {name[d0]} {c0:+.2f} ±{ci0:.2f}  (interval [{c0-ci0:+.2f},{c0+ci0:+.2f}])")
    print(f"        its interval overlaps the next {n_overlap_top} drivers → the 'top' is NOT confidently separable")
    # a concrete adjacent overlapping pair under balanced
    bal = res["balanced"]
    pair = next(((bal[i], bal[i+1]) for i in range(len(bal)-1)
                 if abs(bal[i][1]-bal[i+1][1]) < (bal[i][2]+bal[i+1][2])), None)
    (da, ca, cia), (db, cb, cib) = pair
    print(f"        balanced adjacent overlap: {name[da]} {ca:+.2f}±{cia:.2f} vs {name[db]} {cb:+.2f}±{cib:.2f} "
          f"→ ranked #{rankmap['balanced'][da]}/#{rankmap['balanced'][db]} but NOT separable")
    check("a high-CI driver floats to the nominal top yet overlaps several below (must show as tied)",
          n_overlap_top >= 1, f"{n_overlap_top} overlapping")
    check("adjacent composites with overlapping intervals exist (ranking must mark ties)",
          pair is not None)

    # ---- GATE 4: sanity — balanced top is credible -------------------------
    print("\nGATE 4 — sanity: the balanced top is credible (long-elite, no artifacts)")
    bt = top("balanced", 8)
    print("        balanced top-8: " + ", ".join(n.split()[-1] for n in bt))
    credible = {"Fernando Alonso", "Lewis Hamilton", "Michael Schumacher", "Max Verstappen"}
    nfound = len(credible & set(bt))
    check("at least 3 of {Alonso, Hamilton, Schumacher, Verstappen} are in the balanced top-8",
          nfound >= 3, f"{nfound} of 4 present")
    # no absurd artifact: balanced top-8 shouldn't be dominated by huge-CI drivers
    top_ci = [ci for d, _, ci in res["balanced"][:8]]
    check("balanced top-8 are reasonably-resolved (median CI < 0.5), not uncertainty artifacts",
          float(np.median(top_ci)) < 0.5, f"median ±{np.median(top_ci):.2f}")

    # ---- GATE 5: coverage — missing-axis drivers flagged, not mishandled ----
    print("\nGATE 5 — coverage: drivers missing an axis are flagged 'partial', not zero-filled")
    q = lambda s: con.execute(s).fetchall()
    npart = q("SELECT count(*) FROM driver_quality_axes WHERE is_composite_eligible=0")[0][0]
    nmiss_race = q("SELECT count(*) FROM driver_quality_axes WHERE has_racecraft=0 AND n_seasons>=4")[0][0]
    ex = q("""SELECT driver_name, n_seasons, missing_axes FROM driver_quality_axes
              WHERE is_composite_eligible=0 AND has_racecraft=0 AND n_seasons>=8 LIMIT 3""")
    for nm, ns, miss in ex:
        print(f"        partial: {nm} ({ns} seasons) — missing [{miss}], excluded from composite but axes kept")
    elig_ids = {d for d, _, _ in res["balanced"]}
    check("partial drivers are excluded from the composite ranking (not silently zero-filled)",
          all(d in drivers and drivers[d]["eligible"] for d in elig_ids) and npart > 0, f"{npart} partial")
    check("every partial driver names which axis it is missing", all(miss for _, _, miss in ex) if ex else True)

    # ---- GATE 6: transparency + labelling ----------------------------------
    print("\nGATE 6 — composite is decomposable + estimate kept separate")
    # every eligible driver has all three shrunk z-components present (decomposable, no black box)
    decomp_ok = all(len(drivers[d]["cross"]["zs"]) == 3 and all(v is not None for v in drivers[d]["cross"]["zs"])
                    for d in elig_ids)
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_quality_axes")[0][0]
    check("every composite is decomposable into its three axis scores (no black box)", decomp_ok)
    check("every Phase J row labelled is_estimate=1", bool(all_est))

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE J GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE J GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE J GATE: *** ALL PASS *** — no fixed weighting; the composite responds to the user; "
          "pure pace flatters Giovinazzi, the full picture doesn't; overlaps read as ties. (Estimates.)")


if __name__ == "__main__":
    main()
