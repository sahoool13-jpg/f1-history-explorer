"""Phase E — CAR-NORMALISATION model (the USP).

The first phase that MODELS rather than measures. It estimates a relative driver
QUALIFYING-PACE rating with the car removed, by solving the teammate-delta
network. EVERYTHING here is an ESTIMATE, not a measured fact — there is no
ground-truth "skill" column. Outputs are labelled, uncertainty is propagated and
shown, and modelled numbers are kept structurally separate from the validated
Phase D measurements.

================================ METHOD (exact) ==============================

NODES = drivers (career-average pace). EDGES = Phase D **Tier-1 teammate
qualifying deltas** (the cleanest, car-controlled signal) — one edge per teammate
pair-season. The car cancels within a teammate pair, so each edge observes the
*driver* pace difference:

        r_A - r_B  ≈  d_AB                              (seconds; lower r = faster)

d_AB = median qualifying-time gap (driverA - driverB) from
quali_teammate_delta_pairseason. We solve all edges simultaneously by WEIGHTED
LEAST SQUARES — a chained teammate comparison (A>B, B>C ⇒ A>C) propagated across
the connected network:

        minimise  Σ_k w_k (r_i - r_j - d_k)^2 ,   gauge  Σ r = 0

Weight w_k = 1 / Var(d_k), Var(d_k) = (std_k² + s_prior²) / n_k  (inverse-variance;
s_prior = 0.15 s = inherent single-session noise, so a 1-race edge is not
over-trusted). Normal equations L r = b (L = weighted graph Laplacian); solve
r = L⁺ b (Moore-Penrose pseudoinverse → unique mean-zero, gauge-fixed solution).

UNCERTAINTY — analytic error propagation (stated):
  σ̂² = Σ w_k resid_k² / dof,  dof = n_obs-(n_nodes-1).  σ̂²≈1 ⇒ noise model
  calibrated; σ̂²>1 ⇒ real unmodelled scatter (career form / teammate-specific
  effects) — we SCALE the covariance by it, widening every interval honestly.
  C = σ̂²·L⁺ ; per-driver 1σ = sqrt(C_ii) (vs field mean).  Pairwise
  Var(r_i-r_j) = σ̂²·R_eff(i,j) — the EFFECTIVE RESISTANCE: short high-sample
  chains (direct modern teammates) → tight; long weak cross-era chains → wide.
  A fixed-seed BOOTSTRAP re-solves on resampled edges as an independent check.

CONNECTIVITY: only the largest connected component is mutually comparable; other
components are flagged not-comparable. Degree-1 / high-σ drivers are flagged
'sparse' and must not be presented as confidently ranked.
"""
import numpy as np
from collections import defaultdict
from common import connect, PARQUET

S_PRIOR = 0.15
Z95 = 1.959964
BOOT_N = 400
SEED = 20240619
# a driver is "rankable" (confident headline) only if well-connected:
RANKABLE_MIN_TEAMMATES = 3
RANKABLE_MIN_OBS = 5


def _components(nodes, adj):
    seen, comps = set(), []
    for nd in nodes:
        if nd in seen:
            continue
        stack, comp = [nd], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); comp.append(x)
            stack.extend(adj[x] - seen)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def _solve(edges, n):
    L = np.zeros((n, n)); b = np.zeros(n)
    for i, j, d, w in edges:
        L[i, i] += w; L[j, j] += w; L[i, j] -= w; L[j, i] -= w
        b[i] += w * d; b[j] -= w * d
    Lp = np.linalg.pinv(L)
    r = Lp @ b
    wsse = sum(w * (r[i] - r[j] - d) ** 2 for i, j, d, w in edges)
    dof = max(len(edges) - (n - 1), 1)
    return r, Lp, wsse / dof, wsse, dof


def compute(con):
    """Solve the network; return everything needed by build() and the gate."""
    rows = con.execute("""
        SELECT season, constructorId, driverA, driverB, median_gap_s, n_included, std_s
        FROM quali_teammate_delta_pairseason WHERE median_gap_s IS NOT NULL
    """).fetchall()
    nodes = set(); adj = defaultdict(set); raw = []
    for season, cid, a, b, d, n_inc, std in rows:
        w = n_inc / ((std or 0.0) ** 2 + S_PRIOR ** 2)
        raw.append((a, b, float(d), float(w), season, cid, n_inc))
        nodes.add(a); nodes.add(b); adj[a].add(b); adj[b].add(a)

    comps = _components(nodes, adj)
    giant = set(comps[0])
    node_list = sorted(giant)
    idx = {d: k for k, d in enumerate(node_list)}
    edges = [(idx[a], idx[b], d, w) for a, b, d, w, *_ in raw if a in giant and b in giant]
    giant_raw = [e for e in raw if e[0] in giant and e[1] in giant]

    r, Lp, sigma2, wsse, dof = _solve(edges, len(node_list))
    C = sigma2 * Lp

    deg = defaultdict(set); nobs = defaultdict(int)
    for a, b, *_ in giant_raw:
        deg[a].add(b); deg[b].add(a); nobs[a] += 1; nobs[b] += 1

    rng = np.random.default_rng(SEED)
    boot = np.zeros((BOOT_N, len(node_list))); m = len(edges)
    for t in range(BOOT_N):
        samp = [edges[k] for k in rng.integers(0, m, m)]
        try:
            boot[t] = _solve(samp, len(node_list))[0]
        except np.linalg.LinAlgError:
            boot[t] = r
    boot_sd = boot.std(axis=0)

    return dict(raw=raw, comps=comps, giant=giant, node_list=node_list, idx=idx,
                edges=edges, giant_raw=giant_raw, adj=adj, r=r, Lp=Lp, C=C,
                sigma2=sigma2, wsse=wsse, dof=dof, deg=deg, nobs=nobs, boot_sd=boot_sd)


def effective_resistance(Lp, idx, a, b):
    i, j = idx[a], idx[b]
    return Lp[i, i] + Lp[j, j] - 2 * Lp[i, j]


def build(con):
    M = compute(con)
    r, C, idx, node_list = M["r"], M["C"], M["idx"], M["node_list"]
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    code = dict(con.execute("SELECT driverId, code FROM dim_drivers").fetchall())

    out = []
    for d in node_list:
        i = idx[d]; sd = float(np.sqrt(max(C[i, i], 0.0)))
        degree = len(M["deg"][d]); nob = M["nobs"][d]
        rankable = degree >= RANKABLE_MIN_TEAMMATES and nob >= RANKABLE_MIN_OBS
        flag = "ok" if rankable and sd <= 0.30 else ("sparse" if degree <= 1 or sd > 0.30 else "limited")
        out.append((d, name.get(d), code.get(d), round(float(r[i]), 4), round(sd, 4),
                    round(float(Z95 * sd), 4), round(float(r[i] - Z95 * sd), 4),
                    round(float(r[i] + Z95 * sd), 4), round(float(M["boot_sd"][i]), 4),
                    degree, nob, "giant", flag, int(rankable), 1))

    for comp in M["comps"][1:]:
        comp = set(comp); cl = sorted(comp); ci = {d: k for k, d in enumerate(cl)}
        ce = [(ci[a], ci[b], d, w) for a, b, d, w, *_ in M["raw"] if a in comp and b in comp]
        rr = _solve(ce, len(cl))[0] if ce else np.zeros(len(cl))
        for d in cl:
            out.append((d, name.get(d), code.get(d), round(float(rr[ci[d]]), 4),
                        None, None, None, None, None, len(M["adj"][d] & comp), len(ce),
                        "isolated", "not_comparable", 0, 1))

    con.execute("""CREATE OR REPLACE TABLE driver_pace_model_estimate (
        driverId INT, driver_name VARCHAR, code VARCHAR,
        rating_s_estimate DOUBLE,        -- ESTIMATE: pace vs field mean, car removed; lower = faster
        sigma_s DOUBLE, ci95_halfwidth_s DOUBLE, ci95_low DOUBLE, ci95_high DOUBLE,
        bootstrap_sigma_s DOUBLE, n_teammates INT, n_observations INT,
        component VARCHAR, confidence_flag VARCHAR, rankable INT, is_estimate INT)""")
    con.executemany("INSERT INTO driver_pace_model_estimate VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", out)

    res = []
    for (i, j, d, w), raw in zip(M["edges"], M["giant_raw"]):
        a, b, dd, ww, season, cid, n_inc = raw
        pred = float(r[i] - r[j])
        res.append((season, cid, a, b, round(float(d), 4), round(pred, 4),
                    round(float(d) - pred, 4), n_inc, 1))
    con.execute("""CREATE OR REPLACE TABLE pace_model_residual (
        season INT, constructorId INT, driverA INT, driverB INT,
        measured_delta_s DOUBLE, predicted_delta_s DOUBLE, residual_s DOUBLE,
        n_included INT, is_estimate INT)""")
    con.executemany("INSERT INTO pace_model_residual VALUES (?,?,?,?,?,?,?,?,?)", res)

    for t in ["driver_pace_model_estimate", "pace_model_residual"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    resid = np.array([x[6] for x in res])
    print("=" * 78); print("PHASE E — CAR-NORMALISATION MODEL (estimate)"); print("=" * 78)
    print(f"  giant component: {len(node_list)} drivers, {len(M['edges'])} teammate-delta edges; "
          f"{sum(len(c) for c in M['comps'][1:])} isolated (not comparable)")
    print(f"  residual scale  σ̂² = {M['sigma2']:.2f}  (>1 ⇒ career-average leaves real scatter; "
          f"intervals scaled up accordingly)")
    print(f"  reconstruction: median|resid|={np.median(np.abs(resid)):.3f}s  RMS={np.sqrt((resid**2).mean()):.3f}s")
    rankable_rows = sorted([o for o in out if o[13] == 1], key=lambda o: o[3])
    print(f"\n  RANKABLE (well-connected) estimated qualifying pace — top 10 (ESTIMATE ± 95% CI, s):")
    for o in rankable_rows[:10]:
        print(f"    {o[1]:24} {o[3]:+.3f} ± {o[5]:.3f}   (teammates={o[9]}, obs={o[10]})")
    sparse = sorted([o for o in out if o[12] == "sparse"], key=lambda o: o[4] or 0, reverse=True)[:3]
    print(f"\n  examples of LOW-CONFIDENCE/sparse (wide CI, not confidently rankable):")
    for o in sparse:
        print(f"    {o[1]:24} {o[3]:+.3f} ± {o[5]:.3f}   (teammates={o[9]}, obs={o[10]}, {o[12]})")
    print(f"\n  wrote driver_pace_model_estimate ({len(out)}), pace_model_residual ({len(res)})")
    return M


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE E: done.")


if __name__ == "__main__":
    main()
