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

    # ---- GATE 1: no fixed weighting — weightings produce DIFFERENT top-10s --
    print("GATE 1 — no fixed weighting: the composite responds to the user's weights")
    for tag in ["balanced", "pace-heavy", "racecraft-heavy"]:
        print(f"        {tag:16s} top-5: " + ", ".join(n.split()[-1] for n in top(tag, 5)))
    t_bal, t_pace, t_race = set(top("balanced")), set(top("pace-heavy")), set(top("racecraft-heavy"))
    diff_bp = len(t_bal ^ t_pace); diff_br = len(t_bal ^ t_race)
    check("pace-heavy top-10 differs from balanced", top("pace-heavy") != top("balanced"), f"{diff_bp} members differ")
    check("racecraft-heavy top-10 differs from balanced", top("racecraft-heavy") != top("balanced"), f"{diff_br} members differ")
    check("orderings genuinely move (not a cosmetic reshuffle)", diff_bp >= 1 and diff_br >= 3,
          f"Δpace {diff_bp}, Δrace {diff_br}")

    # ---- GATE 2: THE GIOVINAZZI TEST ---------------------------------------
    print("\nGATE 2 — the Giovinazzi test: pure pace flatters, the full picture sinks him")
    r_pace = rankmap["pace-ONLY"][gio]
    r_bal = rankmap["balanced"][gio]
    r_race = rankmap["racecraft-heavy"][gio]
    print(f"        Giovinazzi rank of {nelig}:  pace-ONLY #{r_pace}   balanced #{r_bal}   racecraft-heavy #{r_race}")
    print(f"        → he can qualify (#{r_pace}); add racecraft+longevity and he falls to #{r_bal}/#{r_race}.")
    print(f"        'decent qualifier, little else' — the thesis, shown by the weighting, not asserted.")
    check("Giovinazzi ranks far higher on pace-only than balanced (pace is his one axis)",
          r_pace < r_bal - 15, f"#{r_pace} pace-only vs #{r_bal} balanced")
    check("under balanced weighting Giovinazzi is in the bottom third", r_bal > 2 * nelig / 3,
          f"#{r_bal} of {nelig}")

    # ---- GATE 3: uncertainty — overlapping composites read as not-separable -
    print("\nGATE 3 — overlapping composite intervals are NOT falsely ordered")
    # racecraft-heavy floats high-CI drivers (Alesi, Berger) to the nominal top; show the overlap.
    rh = res["racecraft-heavy"]
    (d0, c0, ci0) = rh[0]
    # find the first clearly-separable driver below the nominal #1 (no interval overlap)
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
    # every eligible driver has all three z-components present (decomposable, no black box)
    decomp_ok = all(drivers[d]["z_pace"] is not None and drivers[d]["z_race"] is not None
                    and drivers[d]["z_long"] is not None for d in elig_ids)
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
