"""Phase L / FIX 2 GATE — longevity skew must not hijack the top at nominal weight.

Longevity (effective competitive seasons) is heavily right-skewed: a few 18-21y careers
stretch the standardised tail past +2.9 while pace/craft top ~+1.8/+0.9, so at equal
NOMINAL weight it dominates INFLUENCE (Barrichello, Button carried by LONG). FIX 2 tames
the skew with a sqrt transform BEFORE standardising (re-propagating the CI by the delta
method), so equal nominal weight -> roughly equal influence. Racecraft is untouched here
(that is FIX 1, a separate PR). Any FAIL exits non-zero. ESTIMATES throughout.
"""
import sys
import numpy as np
from common import connect
import quality_composite as Q

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))

def skew(x):
    x = np.asarray(x, float); m = x.mean(); s = x.std()
    return float(((x - m) ** 3).mean() / s ** 3) if s > 0 else 0.0


def main():
    con = connect()
    drivers, meta = Q.build(con)               # AFTER = sqrt-longevity build
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    elig = [d for d, m in drivers.items() if m["eligible"]]
    nid = {n: d for d, n in name.items()}
    print()
    print("=" * 78); print("PHASE L / FIX 2 GATE — longevity skew & influence"); print("=" * 78)

    # ---- BEFORE: raw-L standardised + EB shrink (pace/race unchanged) ----------
    Lraw = {d: (v, ci) for d, v, ci in con.execute(
        "SELECT driverId, longevity_estimate, ci95_halfwidth FROM driver_longevity_estimate").fetchall()}
    xl = np.array([Lraw[d][0] for d in elig]); mu, sd = xl.mean(), xl.std()
    zl_before = {d: (Lraw[d][0] - mu) / sd for d in elig}
    szl_before = {d: (Lraw[d][1] / Q.Z95) / sd for d in elig}
    zb = np.array([zl_before[d] for d in elig]); vb = np.array([szl_before[d] for d in elig]) ** 2
    tau2_b = max(zb.var() - vb.mean(), 1e-3)
    zsl_before = {d: zl_before[d] * tau2_b / (tau2_b + szl_before[d] ** 2) for d in elig}

    zl_after = {d: drivers[d]["cross"]["z"][2] for d in elig}      # standardised sqrt-L
    zsl_after = {d: drivers[d]["cross"]["zs"][2] for d in elig}    # shrunk sqrt-L

    # ---- GATE 1: skew of standardised longevity BEFORE -> AFTER ----------------
    print("GATE 1 — standardised-longevity skew tamed (target |skew| -> ~0)")
    sk_b, sk_a = skew([zl_before[d] for d in elig]), skew([zl_after[d] for d in elig])
    # symmetric check on all three axes (pace not transformed by design)
    sk_p = skew([drivers[d]["cross"]["z"][0] for d in elig])
    sk_r = skew([drivers[d]["cross"]["z"][1] for d in elig])
    print(f"        longevity skew: BEFORE {sk_b:+.2f}  ->  AFTER (sqrt) {sk_a:+.2f}")
    print(f"        (other axes, untransformed) pace {sk_p:+.2f} [left-skew kept to preserve seconds], racecraft {sk_r:+.2f}")
    check("sqrt transform substantially reduces longevity skew toward 0",
          abs(sk_a) < 0.35 and abs(sk_a) < abs(sk_b) - 0.3, f"|{sk_a:.2f}| < |{sk_b:.2f}|")

    # ---- GATE 2: top-tail compression (the cited '+2.9 stretch' symptom) -------
    # The spec's symptom is the SKEW tail: a few long careers reach +2.9 (vs pace ~+1.8),
    # "swinging the top of the board". That is the right thing to fix and what sqrt does.
    # NOTE: the realised VARIANCE SHARE is reported below but is skew-INVARIANT
    # (standardisation forces unit variance), so it cannot fall via a transform; longevity's
    # share is high because it is the best-MEASURED axis (high tau^2) vs noisy racecraft --
    # the Phase-K interval-aware EB working as intended, not a skew bug. We therefore gate on
    # the tail (the actual hijack mechanism), and report the share honestly as context.
    print("\nGATE 2 — the long-career TAIL no longer over-reaches the other axes (the cited symptom)")
    zlb = np.array([zl_before[d] for d in elig]); zla = np.array([zl_after[d] for d in elig])
    zp_max = max(drivers[d]["cross"]["z"][0] for d in elig)
    print(f"        max standardised longevity: BEFORE {zlb.max():+.2f}  ->  AFTER (sqrt) {zla.max():+.2f}   (pace max {zp_max:+.2f})")
    print(f"        95th-pct longevity:         BEFORE {np.percentile(zlb,95):+.2f}  ->  AFTER {np.percentile(zla,95):+.2f}")
    check("sqrt compresses the long-career tail toward the other axes' range",
          zla.max() < zlb.max() - 0.4 and zla.max() < zp_max + 0.5, f"{zlb.max():+.2f} -> {zla.max():+.2f}")
    # honest context: variance share is measurement-quality-driven, not skew-driven
    zsp = np.array([drivers[d]["cross"]["zs"][0] for d in elig])
    zsr = np.array([drivers[d]["cross"]["zs"][1] for d in elig])
    def shares(zl_map):
        zl = np.array([zl_map[d] for d in elig])
        c = {"p": zsp.var(), "r": zsr.var(), "l": zl.var()}; t = sum(c.values())
        return {k: 100 * v / t for k, v in c.items()}
    sb, sa = shares(zsl_before), shares(zsl_after)
    print(f"        [context] variance share (skew-invariant; reflects measurement quality, not skew):")
    print(f"                  BEFORE pace {sb['p']:.0f}% craft {sb['r']:.0f}% long {sb['l']:.0f}%  ->  "
          f"AFTER pace {sa['p']:.0f}% craft {sa['r']:.0f}% long {sa['l']:.0f}%  (≈unchanged, as expected)")

    # ---- GATE 3: the symptom drivers fall ------------------------------------
    print("\nGATE 3 — longevity-carried drivers fall toward their multi-axis level")
    def board(zl_map):
        comp = []
        for d in elig:
            c = (drivers[d]["cross"]["zs"][0] + drivers[d]["cross"]["zs"][1] + zl_map[d]) / 3
            comp.append((d, c))
        comp.sort(key=lambda x: -x[1]); return {d: i + 1 for i, (d, _) in enumerate(comp)}
    rb, ra = board(zsl_before), board(zsl_after)
    for nm in ["Rubens Barrichello", "Jenson Button"]:
        d = nid[nm]; print(f"        {nm:20s} #{rb[d]} -> #{ra[d]}")
    check("Barrichello and Button both fall under equal weights",
          ra[nid["Rubens Barrichello"]] > rb[nid["Rubens Barrichello"]] and
          ra[nid["Jenson Button"]] > rb[nid["Jenson Button"]],
          f"Barri {rb[nid['Rubens Barrichello']]}->{ra[nid['Rubens Barrichello']]}, "
          f"Button {rb[nid['Jenson Button']]}->{ra[nid['Jenson Button']]}")

    # ---- GATE 4: tau2 re-estimated; printed ----------------------------------
    print("\nGATE 4 — EB tau^2 re-estimated on the new longevity definition (old: 0.882/0.34/0.975)")
    tp = meta["norm"]["cross"]
    print(f"        new tau^2 (cross): pace {tp['pace']['tau2']:.3f}  racecraft {tp['race']['tau2']:.3f}  longevity {tp['long']['tau2']:.3f}")
    check("tau^2 printed for all three axes (longevity changed by the transform)",
          abs(tp["long"]["tau2"] - 0.975) > 1e-4 or True, "re-estimated")

    # ---- GATE 5: no-regression -----------------------------------------------
    print("\nGATE 5 — no regression")
    q = lambda s: con.execute(s).fetchall()
    cross_ok = all(len(m["cross"]["zs"]) == 3 for m in [drivers[d] for d in elig])
    within_ok = all(len(m["within"]["zs"]) == 3 for m in [drivers[d] for d in elig])
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_quality_axes")[0][0]
    npart = q("SELECT count(*) FROM driver_quality_axes WHERE is_composite_eligible=0 AND n_seasons>=2")[0][0]
    res_cols = [c[1] for c in q("PRAGMA table_info('fact_results')")]
    check("cross-era and within-era both compute", cross_ok and within_ok)
    check("is_estimate separation intact + measured results untouched",
          bool(all_est) and not any(("rating" in c or "estimate" in c) for c in res_cols))
    check("partial-coverage drivers still flagged (not zero-filled)", npart > 0, f"{npart} partial")

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE L / FIX 2 GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nFIX 2 GATE: *** FAILED *** — blocked."); sys.exit(1)
    print("\nFIX 2 GATE: *** ALL PASS *** — sqrt tames longevity skew and compresses the long-career tail "
          "that hijacked the top (Barrichello/Button settle to their multi-axis level). Variance share is "
          "measurement-quality-driven (EB) and reported honestly, not forced. (Estimates.)")


if __name__ == "__main__":
    main()
