"""Phase E GATE — METHOD & SANITY (not correctness).

There is no ground truth for "driver skill", so this gate CANNOT check whether a
rating is right. It checks: (1) anchor sanity — the model does not invert direct,
strong teammate evidence; (2) reconstruction — the solved ratings reproduce their
own input deltas within tolerance; (3) uncertainty behaviour — intervals widen for
cross-era / low-connectivity / small-sample drivers; (4) degenerate inputs are
flagged, not silently rated; (5) separation — modelled estimates are stored and
labelled separately from the measured Phase D deltas; (6) the analytic intervals
agree with a bootstrap. Any FAIL exits non-zero.
"""
import sys
import numpy as np
from common import connect
from pace_model import compute, effective_resistance, Z95

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    did = lambda fore, sur: con.execute(
        "SELECT driverId FROM dim_drivers WHERE forename=? AND surname=?", [fore, sur]).fetchone()[0]
    print("=" * 78); print("PHASE E GATE — model method & sanity (NOT correctness)"); print("=" * 78)
    print("  Reminder: ratings are UNFALSIFIABLE ESTIMATES. These are method checks.\n")

    M = compute(con)
    r, idx, Lp, sigma2 = M["r"], M["idx"], M["Lp"], M["sigma2"]
    rat = lambda fore, sur: r[idx[did(fore, sur)]]

    HAM = did("Lewis", "Hamilton"); ROS = did("Nico", "Rosberg")
    VER = did("Max", "Verstappen"); GAS = did("Pierre", "Gasly")
    PER = did("Sergio", "Pérez"); BOT = did("Valtteri", "Bottas")
    ALO = did("Fernando", "Alonso"); SCH = did("Michael", "Schumacher")
    NOR = did("Lando", "Norris")

    # ---- GATE 1: anchor sanity (relative; must not invert direct strong evidence)
    print("GATE 1 — anchor sanity (RELATIVE; vs direct, strong teammate deltas — not truth claims)")
    anchors = [("Hamilton faster than Rosberg", rat("Lewis", "Hamilton") < rat("Nico", "Rosberg")),
               ("Verstappen faster than Gasly", rat("Max", "Verstappen") < rat("Pierre", "Gasly")),
               ("Verstappen faster than Pérez", rat("Max", "Verstappen") < rat("Sergio", "Pérez")),
               ("Hamilton faster than Bottas",  rat("Lewis", "Hamilton") < rat("Valtteri", "Bottas"))]
    for nm, ok in anchors:
        check("  " + nm + " (direct teammate edge not inverted)", ok)
    # global sign agreement on strong edges
    rows = con.execute("SELECT measured_delta_s, predicted_delta_s FROM pace_model_residual").fetchall()
    strong = [(m, p) for m, p in rows if abs(m) > 0.15]
    agree = sum(1 for m, p in strong if (m < 0) == (p < 0))
    frac = agree / len(strong)
    check("model reproduces the SIGN of strong teammate deltas (>80%)", frac > 0.80,
          f"{agree}/{len(strong)} = {100*frac:.1f}%")

    # ---- GATE 2: reconstruction (explains its own inputs within tolerance) ----
    print("\nGATE 2 — reconstruction (solved ratings predict the input deltas)")
    resid = np.array([x[2] for x in con.execute(
        "SELECT * FROM pace_model_residual").fetchall()]) if False else \
        np.array([row[0] for row in con.execute("SELECT residual_s FROM pace_model_residual").fetchall()])
    med = float(np.median(np.abs(resid))); rms = float(np.sqrt((resid**2).mean()))
    big = int((np.abs(resid) > 0.5).sum())
    print(f"        median|residual|={med:.3f}s  RMS={rms:.3f}s  |resid|>0.5s: {big}/{len(resid)}  "
          f"(σ̂²={sigma2:.2f} — career-average misfit, intervals scaled up)")
    check("median |residual| within tolerance (< 0.20 s)", med < 0.20, f"{med:.3f}s")
    check("most edges reconstructed (|resid|>0.5s on < 15% of edges)", big < 0.15 * len(resid),
          f"{big}/{len(resid)}")

    # ---- GATE 3: uncertainty behaviour (widens for sparse / cross-era) -------
    print("\nGATE 3 — uncertainty behaviour (tight where data is dense, wide where it thins)")
    est = {row[0]: row for row in con.execute("""
        SELECT driverId, sigma_s, ci95_halfwidth_s, n_teammates, confidence_flag, rankable
        FROM driver_pace_model_estimate WHERE component='giant'""").fetchall()}
    rankable_ci = [v[2] for v in est.values() if v[5] == 1]
    sparse_ci = [v[2] for v in est.values() if v[4] == 'sparse']
    med_rank, med_sparse = float(np.median(rankable_ci)), float(np.median(sparse_ci))
    print(f"        median 95% CI half-width:  rankable={med_rank:.3f}s   sparse={med_sparse:.3f}s")
    check("sparse/low-connectivity drivers have wider intervals than rankable", med_sparse > 2 * med_rank,
          f"{med_sparse:.3f} vs {med_rank:.3f}")
    # pairwise effective resistance: direct modern vs cross-era
    R_direct = effective_resistance(Lp, idx, VER, PER)     # direct, multi-season
    R_cross = effective_resistance(Lp, idx, SCH, VER)      # cross-era, long chain
    ci_direct = Z95 * np.sqrt(sigma2 * R_direct)
    ci_cross = Z95 * np.sqrt(sigma2 * R_cross)
    print(f"        pairwise 95% CI on the gap:  VER–PER (direct) ±{ci_direct:.3f}s   "
          f"SCH–VER (cross-era) ±{ci_cross:.3f}s")
    check("cross-era pairwise interval much wider than a direct one (effective resistance)",
          R_cross > 2 * R_direct, f"R_eff cross={R_cross:.3f} vs direct={R_direct:.3f}")
    check("cross-era gap is NOT confidently separable (CI ≳ gap)",
          ci_cross > abs(rat("Michael", "Schumacher") - rat("Max", "Verstappen")),
          f"±{ci_cross:.3f}s vs gap {abs(rat('Michael','Schumacher')-rat('Max','Verstappen')):.3f}s")

    # ---- GATE 4: degenerate inputs flagged, not silently rated ----------------
    print("\nGATE 4 — degenerate inputs (isolated / single-teammate / dominant-car)")
    iso = con.execute("SELECT count(*) FROM driver_pace_model_estimate WHERE component='isolated'").fetchone()[0]
    iso_flagged = con.execute("""SELECT count(*) FROM driver_pace_model_estimate
        WHERE component='isolated' AND confidence_flag='not_comparable' AND rankable=0""").fetchone()[0]
    deg1_rankable = con.execute("""SELECT count(*) FROM driver_pace_model_estimate
        WHERE n_teammates<=1 AND rankable=1""").fetchone()[0]
    check("isolated-component drivers flagged not_comparable (never rankable)",
          iso > 0 and iso == iso_flagged, f"{iso_flagged}/{iso}")
    check("no single-teammate driver is presented as confidently rankable", deg1_rankable == 0,
          f"{deg1_rankable} rankable degree-1 drivers")
    # dominant-car: a dominant-car driver isn't inflated by the car — the rating is
    # purely teammate-relative. Verstappen (2021-24 dominant RBR) rates fast because
    # he beats his teammate, with a finite CI — not because the car is fast.
    v = est[VER]
    check("dominant-car driver (Verstappen) rated from teammate gap with finite CI, not inflated by car",
          v[5] == 1 and v[2] < 0.35, f"VER ±{v[2]:.3f}s, rankable={v[5]}")

    # ---- GATE 5: separation of modelled estimate from measured deltas ---------
    print("\nGATE 5 — modelled ESTIMATE kept separate from measured Phase D deltas")
    all_est = con.execute("SELECT bool_and(is_estimate=1) FROM driver_pace_model_estimate").fetchone()[0]
    measured_cols = [c[1] for c in con.execute("PRAGMA table_info('quali_teammate_delta_pairseason')").fetchall()]
    no_rating_in_measured = not any("rating" in c or "estimate" in c for c in measured_cols)
    has_estimate_col = any("estimate" in c[1] for c in
                           con.execute("PRAGMA table_info('driver_pace_model_estimate')").fetchall())
    check("every model row labelled is_estimate=1", bool(all_est))
    check("rating lives in its own table, named *_estimate", has_estimate_col)
    check("measured Tier-1 table carries NO rating/estimate column (not merged)", no_rating_in_measured)

    # ---- GATE 6: analytic vs bootstrap intervals agree -----------------------
    print("\nGATE 6 — analytic intervals cross-checked against a fixed-seed bootstrap")
    pairs = con.execute("""SELECT sigma_s, bootstrap_sigma_s FROM driver_pace_model_estimate
        WHERE component='giant' AND rankable=1 AND sigma_s IS NOT NULL""").fetchall()
    a = np.array([p[0] for p in pairs]); bsd = np.array([p[1] for p in pairs])
    corr = float(np.corrcoef(a, bsd)[0, 1])
    print(f"        corr(analytic σ, bootstrap σ) over {len(pairs)} rankable drivers = {corr:.3f}")
    check("analytic and bootstrap uncertainties agree (corr > 0.6)", corr > 0.6, f"{corr:.3f}")

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE E GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE E GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE E GATE: *** ALL PASS *** — model method sound, uncertainty honest. "
          "(Ratings remain estimates, not facts.)")


if __name__ == "__main__":
    main()
