"""Phase K GATE — interval-aware shrinkage + within-era mode: era-neutrality & honesty.

Phase K refines the composite with empirical-Bayes interval-aware shrinkage and adds a
within-era normalisation option. This gate proves the refinement does what the diagnostic
promised: (1) the shrink hits the NOISY axis (racecraft), not pace/longevity; (2) it is
ERA-NEUTRAL — the real field-compression gradient survives cross-era, and risers/fallers
are interval-driven not era-driven; (3) the within-era mode flattens each era's mean by
construction (peers, not absolutes); (4) thin-data estimates (Hill) rise legitimately while
the well-measured top is untouched; (5) shrunk intervals tighten; (6) every driver stays
decomposable for the radar. Any FAIL exits non-zero. ESTIMATES throughout.
"""
import sys
import numpy as np
from common import connect
import quality_composite as Q

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    drivers, meta = Q.build(con)            # builds tables + prints summary
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    elig = {d: m for d, m in drivers.items() if m["eligible"]}
    nid = {n: d for d, n in name.items()}
    print()
    print("=" * 78); print("PHASE K GATE — interval-aware shrinkage, within-era mode, era-neutrality"); print("=" * 78)
    print("  Refinement must kill noise-as-signal WITHOUT erasing the real field-compression gradient.\n")

    AX = ["pace", "race", "long"]

    def comp(mode, shrunk=True):
        out = []
        for d, m in elig.items():
            v = m[mode]["zs" if shrunk else "z"]
            out.append((d, sum(v) / 3.0))
        out.sort(key=lambda x: -x[1])
        return {d: i + 1 for i, (d, _) in enumerate(out)}, dict(out)

    # ---- GATE 1: shrinkage hits the NOISY axis (racecraft), not pace/longevity
    print("GATE 1 — shrinkage targets the noisy axis (racecraft), leaves pace/longevity")
    fac = {}
    for ai, a in enumerate(AX):
        fs = [m["cross"]["zs"][ai] / m["cross"]["z"][ai] for m in elig.values() if abs(m["cross"]["z"][ai]) > 1e-9]
        fac[a] = float(np.mean(fs))
        print(f"        {a:5s}: tau^2={meta['norm']['cross'][a]['tau2']:.2f}  mean shrink factor={fac[a]:.2f} "
              f"(range {min(fs):.2f}-{max(fs):.2f})")
    check("racecraft shrinks much more than pace (it is the noisy axis)", fac["race"] < fac["pace"] - 0.2,
          f"race {fac['race']:.2f} vs pace {fac['pace']:.2f}")
    check("pace & longevity barely shrink (real signal preserved)", fac["pace"] > 0.8 and fac["long"] > 0.8,
          f"pace {fac['pace']:.2f}, long {fac['long']:.2f}")

    # ---- GATE 2: ERA-NEUTRAL — cross-era field-compression gradient survives
    print("\nGATE 2 — cross-era field-compression gradient SURVIVES (noise-reduction, not era-adj)")
    _, c_un = comp("cross", False); _, c_sh = comp("cross", True)
    def era_means(cmap):
        by = {}
        for d in elig: by.setdefault(elig[d]["cohort"], []).append(cmap[d])
        return {k: float(np.mean(v)) for k, v in by.items()}
    eu, es = era_means(c_un), era_means(c_sh)
    order = ["1994-2003", "2004-2013", "2014-2024"]
    print("        cross-era cohort means  unshrunk -> shrunk:")
    for k in order:
        print(f"           {k}: {eu[k]:+.2f} -> {es[k]:+.2f}")
    mono = es["1994-2003"] < es["2004-2013"] < es["2014-2024"]
    check("the modern>old gradient is preserved after shrink (field compression kept, not erased)",
          mono and (es["2014-2024"] - es["1994-2003"]) > 0.25,
          f"Δ {es['2014-2024']-es['1994-2003']:+.2f}")

    # ---- GATE 3: ERA-NEUTRALITY — risers & fallers are both early-era ---------
    print("\nGATE 3 — the shrinkage is interval-driven, NOT era-driven (proof: symmetric)")
    r_un, _ = comp("cross", False); r_sh, _ = comp("cross", True)
    movers = sorted(elig, key=lambda d: r_un[d] - r_sh[d])
    risers = [d for d in movers[::-1] if r_un[d] - r_sh[d] > 0][:3]
    fallers = [d for d in movers if r_sh[d] - r_un[d] > 0][:3]
    for d in risers:
        print(f"        riser  {name[d]:20s} #{r_un[d]} -> #{r_sh[d]}  ({elig[d]['cohort']})")
    for d in fallers:
        print(f"        faller {name[d]:20s} #{r_un[d]} -> #{r_sh[d]}  ({elig[d]['cohort']})")
    early_risers = any(elig[d]["cohort"] == "1994-2003" for d in risers)
    early_fallers = any(elig[d]["cohort"] == "1994-2003" for d in fallers)
    check("both risers AND fallers include 1994-2003 drivers (interval-driven, era-neutral)",
          early_risers and early_fallers, f"risers early={early_risers}, fallers early={early_fallers}")

    # ---- GATE 4: WITHIN-ERA mode flattens each cohort to ~0 ------------------
    print("\nGATE 4 — within-era mode = 'standing among contemporaries' (flattens each era)")
    _, w_sh = comp("within", True); ew = era_means(w_sh)
    for k in order:
        print(f"        within-era {k}: mean {ew[k]:+.2f}")
    check("within-era flattens every cohort mean toward 0 (peers, by construction)",
          all(abs(ew[k]) < 0.12 for k in order), f"max |mean| {max(abs(ew[k]) for k in order):.2f}")

    # ---- GATE 5: thin-data Hill rises; well-measured top untouched -----------
    print("\nGATE 5 — thin-data noisy-negative rises; confidently-measured top is untouched")
    hill = nid["Damon Hill"]
    print(f"        Hill (4-7 G-seasons, racecraft ±wide): cross #{r_un[hill]} -> #{r_sh[hill]}")
    top_un, _ = comp("cross", False)
    elite = [nid[n] for n in ["Fernando Alonso", "Lewis Hamilton", "Michael Schumacher"]]
    moved = max(abs(r_un[d] - r_sh[d]) for d in elite)
    check("Hill rises but stays mid-pack (legitimate lift, not rescued to the top)",
          r_sh[hill] < r_un[hill] and r_sh[hill] > 12, f"#{r_un[hill]} -> #{r_sh[hill]}")
    check("the well-measured elite (Alonso/Hamilton/Schumacher) barely move (≤2 places)",
          moved <= 2, f"max move {moved}")

    # ---- GATE 6: shrunk intervals tighten -----------------------------------
    print("\nGATE 6 — empirical-Bayes posterior intervals tighten (more info, honestly)")
    un = Q.composite({d: {"eligible": True,
                          "cross": {"zs": elig[d]["cross"]["z"], "szs": elig[d]["cross"]["sz"]}}
                      for d in elig}, 1, 1, 1)
    sh = Q.composite(drivers, 1, 1, 1)
    mun = float(np.median([ci for _, _, ci in un])); msh = float(np.median([ci for _, _, ci in sh]))
    print(f"        median balanced composite CI: unshrunk ±{mun:.2f} -> shrunk ±{msh:.2f}")
    check("shrunk composite intervals are tighter than unshrunk", msh < mun, f"±{msh:.2f} < ±{mun:.2f}")

    # ---- GATE 7: radar decomposability + labelling --------------------------
    print("\nGATE 7 — every eligible driver stays decomposable (for the radar) + labelled")
    ok = all(len(m["cross"]["zs"]) == 3 and len(m["within"]["zs"]) == 3 for m in elig.values())
    all_est = con.execute("SELECT bool_and(is_estimate=1) FROM driver_quality_axes").fetchone()[0]
    check("all 3 shrunk axes present per driver in BOTH modes (radar shape well-defined)", ok, f"{len(elig)} drivers")
    check("every row labelled is_estimate=1", bool(all_est))

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE K GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE K GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE K GATE: *** ALL PASS *** — shrinkage kills noise-as-signal, era-neutral, keeps the "
          "field-compression gradient; within-era offers the peers view. (Estimates.)")


if __name__ == "__main__":
    main()
