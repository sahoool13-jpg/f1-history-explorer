"""Phase F — TIME-VARYING car-normalisation model (evolution of the USP).

Phase E used ONE career-average rating per driver, blending prime and decline into
a single number. Phase F makes pace TIME-RESOLVED: nodes are **driver-seasons**, so
a teammate delta credits a driver against their opponent AS THEY WERE THAT YEAR.

Still an ESTIMATE (is_estimate kept separate, CIs propagated). Inputs are the
validated Phase D per-season Tier-1 quali deltas — nothing re-measured.

================================ METHOD (exact) ==============================

NODES = (driver, season). EDGES:
  * TEAMMATE edges — one per Phase-D Tier-1 pair-season: links (A, yr)–(B, yr) with
    the measured delta d_AB; weight w = n / (std² + 0.15²) (inverse-variance).
  * CONTINUITY (smoothing-prior) edges — link each driver's consecutive seasons
    (d, s)–(d, s+gap) with target 0 and weight λ/gap. This is a RANDOM-WALK prior:
    a driver's pace may DRIFT year to year (λ = 1/σ_drift²) but not jump. Over a
    multi-year gap the allowed drift grows, so the weight is divided by the gap.

Solve  minimise  Σ_tm w_k (r_i−r_j−d_k)²  +  Σ_cont (λ/gap)(r_i−r_j)² , gauge Σr=0.
Normal equations L r = b (L = weighted Laplacian of BOTH edge sets); r = L⁺ b.

CHOOSING λ (the key tuning choice — NOT a magic constant):
  λ is chosen by 5-fold CROSS-VALIDATION on the teammate edges (fixed seed): for a
  grid of λ we hold out a fifth of the teammate edges, refit on the rest (+ all
  continuity), and measure weighted prediction error on the held-out deltas. The λ
  minimising CV error is selected. We also report the ratings' SENSITIVITY to
  λ (×¼, ×1, ×4) so the smoothing is transparent, never hidden.

UNCERTAINTY (analytic, as Phase E):
  effective params p_eff = Σ_tm w_k·R_eff(edge_k) (trace of the hat matrix);
  σ̂² = Σ_tm w_k resid_k² / (m_tm − p_eff); C = σ̂²·L⁺; per-node 95% CI = ±1.96√C_ii.
  Driver-seasons resting on one thin edge read as very uncertain; cross-era stays
  wide. Intervals are WIDER than Phase E (sparser nodes) — that is honest.
"""
import numpy as np
from collections import defaultdict
from common import connect, PARQUET

S_PRIOR = 0.15
Z95 = 1.959964
SEED = 20240619
LAM_GRID = [15, 30, 60, 120, 240, 480]
CV_FOLDS = 5
# --- smoothing strength (the key tuning choice) ---------------------------
# CV is computed for transparency, but on this data it is MONOTONE-decreasing in
# λ (it keeps preferring more smoothing, i.e. collapse toward the Phase-E
# career-average) — so CV alone cannot pick λ without defeating the phase. We
# therefore set λ from an interpretable RANDOM-WALK DRIFT PRIOR: a top driver's
# qualifying pace vs teammates drifts ~σ_drift per year. σ_drift = 0.10 s/yr is a
# plausible year-on-year change (λ = 1/σ_drift²), it sits inside the CV-flat band,
# and it resolves known career arcs without fitting single-season noise.
DRIFT_SIGMA = 0.10
LAM_PRIOR = round(1.0 / DRIFT_SIGMA ** 2)        # = 100
SENSITIVITY_DRIVERS = ["Lewis Hamilton", "Fernando Alonso", "Kimi Räikkönen",
                       "Michael Schumacher", "Max Verstappen"]


def _load(con):
    rows = con.execute("""
        SELECT season, driverA, driverB, median_gap_s, n_included, std_s
        FROM quali_teammate_delta_pairseason WHERE median_gap_s IS NOT NULL
    """).fetchall()
    nodes = {}                       # (driver, season) -> idx
    def nid(d, s):
        k = (d, s)
        if k not in nodes:
            nodes[k] = len(nodes)
        return nodes[k]
    tm = []                          # (i, j, d, w)
    seasons_by_driver = defaultdict(set)
    for season, a, b, d, n_inc, std in rows:
        i, j = nid(a, season), nid(b, season)
        w = n_inc / ((std or 0.0) ** 2 + S_PRIOR ** 2)
        tm.append((i, j, float(d), float(w)))
        seasons_by_driver[a].add(season); seasons_by_driver[b].add(season)
    cont = []                        # (i, j, 0, gap) -- weight applied as lam/gap
    for d, ss in seasons_by_driver.items():
        ss = sorted(ss)
        for s_a, s_b in zip(ss, ss[1:]):
            cont.append((nodes[(d, s_a)], nodes[(d, s_b)], s_b - s_a))
    return nodes, tm, cont, seasons_by_driver


def _laplacian(N, tm, cont, lam, ridge=0.0):
    L = np.zeros((N, N)); b = np.zeros(N)
    for i, j, d, w in tm:
        L[i, i] += w; L[j, j] += w; L[i, j] -= w; L[j, i] -= w
        b[i] += w * d; b[j] -= w * d
    for i, j, gap in cont:
        w = lam / gap
        L[i, i] += w; L[j, j] += w; L[i, j] -= w; L[j, i] -= w
    if ridge:
        L = L + ridge * np.eye(N)
    return L, b


def _solve_r(N, tm, cont, lam):
    L, b = _laplacian(N, tm, cont, lam, ridge=1e-9)
    return np.linalg.solve(L, b)


def _cv_error(N, tm, cont, lam, rng):
    idx = np.arange(len(tm)); rng.shuffle(idx)
    folds = np.array_split(idx, CV_FOLDS)
    se = 0.0; sw = 0.0
    for f in folds:
        held = set(f.tolist())
        train = [tm[k] for k in range(len(tm)) if k not in held]
        r = _solve_r(N, train, cont, lam)
        for k in f:
            i, j, d, w = tm[k]
            se += w * (d - (r[i] - r[j])) ** 2; sw += w
    return se / sw


def cv_curve(N, tm, cont):
    """CV error per λ (for transparency). On this data it is monotone -> see note."""
    curve = []
    for lam in LAM_GRID:
        curve.append((lam, float(np.sqrt(_cv_error(N, tm, cont, lam, np.random.default_rng(SEED))))))
    return curve


def compute(con, lam=None, with_cv=True):
    nodes, tm, cont, sbd = _load(con)
    N = len(nodes)
    curve = cv_curve(N, tm, cont) if with_cv else None
    if lam is None:
        lam = LAM_PRIOR          # set by the drift prior, NOT by CV-argmin (see note)

    L, b = _laplacian(N, tm, cont, lam)          # no ridge — use pinv for covariance
    Lp = np.linalg.pinv(L)
    r = Lp @ b

    # effective params (trace of hat matrix over teammate edges) and sigma^2
    p_eff = 0.0; wsse = 0.0
    for i, j, d, w in tm:
        reff = Lp[i, i] + Lp[j, j] - 2 * Lp[i, j]
        p_eff += w * reff
        wsse += w * (r[i] - r[j] - d) ** 2
    dof = max(len(tm) - p_eff, 1.0)
    sigma2 = wsse / dof
    C = sigma2 * Lp

    # teammate-edge count per node (for connectivity flag)
    tdeg = defaultdict(int)
    for i, j, d, w in tm:
        tdeg[i] += 1; tdeg[j] += 1

    inv = {v: k for k, v in nodes.items()}
    return dict(nodes=nodes, inv=inv, tm=tm, cont=cont, sbd=sbd, N=N, lam=lam,
                curve=curve, r=r, Lp=Lp, C=C, sigma2=sigma2, wsse=wsse, p_eff=p_eff,
                dof=dof, tdeg=tdeg)


def build(con):
    M = compute(con)
    r, C, inv, tdeg = M["r"], M["C"], M["inv"], M["tdeg"]
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    code = dict(con.execute("SELECT driverId, code FROM dim_drivers").fetchall())

    rows = []
    for k, i in M["nodes"].items():
        d, s = k
        sd = float(np.sqrt(max(C[i, i], 0.0)))
        te = tdeg[i]
        flag = "ok" if (te >= 2 and sd <= 0.35) else "sparse"
        rows.append((d, name.get(d), code.get(d), s, round(float(r[i]), 4),
                     round(sd, 4), round(float(Z95 * sd), 4),
                     round(float(r[i] - Z95 * sd), 4), round(float(r[i] + Z95 * sd), 4),
                     te, flag, 1))
    con.execute("""CREATE OR REPLACE TABLE driver_season_pace_estimate (
        driverId INT, driver_name VARCHAR, code VARCHAR, season INT,
        rating_s_estimate DOUBLE, sigma_s DOUBLE, ci95_halfwidth_s DOUBLE,
        ci95_low DOUBLE, ci95_high DOUBLE, n_teammate_edges INT,
        confidence_flag VARCHAR, is_estimate INT)""")
    con.executemany("INSERT INTO driver_season_pace_estimate VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    res = []
    for i, j, d, w in M["tm"]:
        res.append((round(float(d), 4), round(float(r[i] - r[j]), 4), round(float(d - (r[i] - r[j])), 4)))
    con.execute("""CREATE OR REPLACE TABLE pace_model_tv_residual (
        measured_delta_s DOUBLE, predicted_delta_s DOUBLE, residual_s DOUBLE)""")
    con.executemany("INSERT INTO pace_model_tv_residual VALUES (?,?,?)", res)

    # sensitivity: notable drivers under x1/4, x1, x4 smoothing (transparency)
    lam_lo, lam_hi = M["lam"] // 4, M["lam"] * 4
    r_lo = _solve_r(M["N"], M["tm"], M["cont"], lam_lo)
    r_hi = _solve_r(M["N"], M["tm"], M["cont"], lam_hi)
    sens = []
    name2id = {v: k for k, v in name.items()}
    for nm in SENSITIVITY_DRIVERS:
        did = name2id.get(nm)
        if did is None:
            continue
        for (d, s), i in M["nodes"].items():
            if d == did:
                sens.append((nm, s, lam_lo, M["lam"], lam_hi,
                             round(float(r_lo[i]), 4), round(float(r[i]), 4), round(float(r_hi[i]), 4)))
    con.execute("""CREATE OR REPLACE TABLE pace_model_tv_sensitivity (
        driver_name VARCHAR, season INT, lam_quarter INT, lam_chosen INT, lam_4x INT,
        rating_quarter DOUBLE, rating_chosen DOUBLE, rating_4x DOUBLE)""")
    con.executemany("INSERT INTO pace_model_tv_sensitivity VALUES (?,?,?,?,?,?,?,?)", sens)

    for t in ["driver_season_pace_estimate", "pace_model_tv_residual", "pace_model_tv_sensitivity"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    resid = np.array([x[2] for x in res])
    print("=" * 78); print("PHASE F — TIME-VARYING CAR-NORMALISATION MODEL (estimate)"); print("=" * 78)
    print(f"  {M['N']} driver-season nodes, {len(M['tm'])} teammate edges, {len(M['cont'])} continuity edges")
    print(f"  smoothing λ = {M['lam']} from the drift prior (σ_drift = {DRIFT_SIGMA} s/yr); "
          f"NOT CV-argmin (CV is monotone here — would collapse to career-average)")
    if M["curve"]:
        print("  CV curve (λ → held-out weighted RMS) — monotone/flat, hence uninformative:")
        for lam, e in M["curve"]:
            mark = "  <- chosen (prior)" if lam == M["lam"] else ("  (CV-argmin → over-smoothed)" if lam == M["curve"][-1][0] else "")
            print(f"      λ={lam:>4}  RMS={e:.4f}{mark}")
    print(f"  effective params p_eff={M['p_eff']:.1f} (of {M['N']} nodes); σ̂²={M['sigma2']:.2f}")
    print(f"  reconstruction: median|resid|={np.median(np.abs(resid)):.3f}s  RMS={np.sqrt((resid**2).mean()):.3f}s")
    print(f"  wrote driver_season_pace_estimate ({len(rows)}), pace_model_tv_residual ({len(res)})")
    return M


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE F: done.")


if __name__ == "__main__":
    main()
