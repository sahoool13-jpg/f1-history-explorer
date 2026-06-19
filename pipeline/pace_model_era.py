"""Phase G — ERA-NORMALISATION via spanning-driver bridges.

Phase F made pace time-resolved (driver-season nodes, teammate edges, a random-walk
continuity prior). It is car-normalised and time-resolved, but its scale is only as
trustworthy as the chain of teammate links that ties a given driver-season back to
the rest of the field. A driver who only ever shared a car inside a WEAK, LOCALLY
ISOLATED cluster can float to an inflated level on the strength of intra-cluster
deltas alone — nothing pulls that cluster onto the cross-era scale.

Phase G fixes the *anchoring*, not the relative structure, and it does so WITHOUT
ever assuming an era is strong or weak. The cross-era scale is allowed to EMERGE
from real overlapping careers:

================================ METHOD (exact) ==============================

SPANNING BACKBONE.  A driver is a *spanning bridge* if their teammate record spans
>= SPAN_MIN years AND touches teammates in >= 2 of three era-thirds
(1950-2003 / 2004-2013 / 2014-2024 boundaries at 2003|2004 and 2013|2014). These
are the drivers whose own continuous careers physically connect distant eras
(Coulthard 1994-2008, Webber 2002-2013, Alonso 2001-2024, ...). Their driver-season
nodes form the BACKBONE. Everyone else is FREE.

EFFECTIVE RESISTANCE TO THE BACKBONE.  On the full weighted Laplacian L (teammate +
continuity edges, exactly Phase F), ground the backbone nodes and read the diagonal
of the inverse over the free block:  R_bb = diag( (L_ff)^-1 ).  R_bb is small when a
driver-season is tied to the spine by many short paths, and explodes when it hangs
off one thin bridge — or is in a component the spine never reaches at all (e.g.
Marussia 2013-14, who only ever raced each other). R_bb is the honest measure of
"how confidently can this be placed on the cross-era scale".

SPINE CONSENSUS.  Harmonic extension of the backbone ratings to the free nodes:
solve L_ff mu_f = b_f - L_fb r_backbone. mu_i is "where the real chains, followed
back to the spine, say this node sits" — derived purely from measured deltas, never
from an assumed era strength.

SELECTIVE SHRINKAGE (the era-normalisation).  Re-solve with a per-node prior that
pulls each free node toward its spine consensus with strength proportional to how
poorly it is anchored:
    minimise   Sigma_tm w (r_i-r_j-d)^2  +  Sigma_cont (lam/gap)(r_i-r_j)^2
             +  Sigma_free  K0 * R_bb_i * (r_i - mu_i)^2 ,   gauge: mean over backbone = 0.
Well-anchored nodes (small R_bb) are left to the data; thinly-bridged pockets are
pulled onto the spine. Crucially this re-references a pocket's ABSOLUTE level while
PRESERVING the within-pocket teammate deltas (reconstruction is unchanged), so it
de-inflates the floating level of an isolated cluster's leader without rewriting who
beat whom. The gauge zeroes the scale on the spanning spine, not on the population
mix, so the cross-era zero is the empirically-bridged backbone.

UNCERTAINTY.  Cross-era CI = Z95 * sigma_hat * sqrt( C_ii/sigma2 + R_bb_i ): the
Phase-F intra-model variance PLUS the backbone-anchoring resistance. Thinly-bridged
or disconnected nodes blow out so wide they make no cross-era claim — exactly where
the spanning bridges run thin. We do NOT shrink uncertainty just because the prior
moved the point estimate; the prior is acknowledged ignorance, not new measurement.

Everything is an ESTIMATE (is_estimate kept separate). Inputs trace to the validated
Phase D Tier-1 deltas via the Phase F solve; nothing is re-measured.
"""
import numpy as np
from collections import defaultdict
from common import connect, PARQUET
import pace_model_tv as F

Z95 = 1.959964
SPAN_MIN = 10                 # spanning driver: career-span >= 10 years
ERA_CUTS = (2003, 2013)       # era-thirds boundaries (2003|2004, 2013|2014)
K0 = 1.0                      # shrinkage strength (robust: see gate sensitivity)
GROUND_RIDGE = 1e-6           # numerical grounding for disconnected free components
THIN_MULT = 3.0              # R_bb > THIN_MULT * median(free) => "thin" anchoring
DISCONNECT_R = 1.0           # R_bb > 1.0 => effectively disconnected, no cross-era claim


def _era_third(season):
    return 0 if season <= ERA_CUTS[0] else (1 if season <= ERA_CUTS[1] else 2)


def _spanning_drivers(sbd):
    """Drivers whose teammate record spans >= SPAN_MIN yrs AND >= 2 era-thirds."""
    out = set()
    for d, ss in sbd.items():
        ss = sorted(ss)
        if (ss[-1] - ss[0]) >= SPAN_MIN and len({_era_third(s) for s in ss}) >= 2:
            out.add(d)
    return out


def _full_laplacian(M):
    """Weighted Laplacian L and rhs b of teammate + continuity edges (Phase F)."""
    N = M["N"]
    L = np.zeros((N, N)); b = np.zeros(N)
    for i, j, d, w in M["tm"]:
        L[i, i] += w; L[j, j] += w; L[i, j] -= w; L[j, i] -= w
        b[i] += w * d; b[j] -= w * d
    for i, j, gap in M["cont"]:
        w = M["lam"] / gap
        L[i, i] += w; L[j, j] += w; L[i, j] -= w; L[j, i] -= w
    return L, b


def compute(con):
    M = F.compute(con, with_cv=False)
    nodes, inv, sbd = M["nodes"], M["inv"], M["sbd"]
    N, r_f, C_f, sigma2 = M["N"], M["r"], M["C"], M["sigma2"]

    spanning = _spanning_drivers(sbd)
    backbone = sorted(i for (d, s), i in nodes.items() if d in spanning)
    free = sorted(i for (d, s), i in nodes.items() if d not in spanning)
    bidx, fidx = np.array(backbone), np.array(free)

    L, b = _full_laplacian(M)

    # effective resistance of every free node to the GROUNDED backbone set
    Lff = L[np.ix_(fidx, fidx)] + GROUND_RIDGE * np.eye(len(fidx))
    Lff_inv = np.linalg.inv(Lff)
    Rbb = np.zeros(N)
    Rbb[fidx] = np.diag(Lff_inv)            # backbone nodes are the reference => 0

    # spine consensus mu (harmonic extension of backbone ratings to free nodes)
    Lfb = L[np.ix_(fidx, bidx)]
    mu = r_f.copy()
    mu[fidx] = Lff_inv @ (b[fidx] - Lfb @ r_f[bidx])

    # selective shrinkage re-solve, gauged to backbone mean = 0
    Ls = L.copy(); bs = b.copy()
    for i in free:
        k = K0 * Rbb[i]
        Ls[i, i] += k; bs[i] += k * mu[i]
    g = np.zeros(N); g[bidx] = 1.0
    Ls = Ls + GROUND_RIDGE * np.eye(N) + 1e3 * np.outer(g, g)   # soft sum_backbone r = 0
    r = np.linalg.solve(Ls, bs)
    r = r - r[bidx].mean()                  # exact backbone-zero gauge
    # Phase F ratings re-referenced to the SAME backbone-zero gauge, so that the
    # F -> G difference is pure selective shrinkage, not a change of zero-point.
    r_f_bb = r_f - r_f[bidx].mean()

    # cross-era uncertainty: Phase-F intra-model variance + backbone-anchoring resistance
    med_free = float(np.median(Rbb[fidx]))
    thin_thr = THIN_MULT * med_free
    var_model = np.clip(np.diag(C_f), 0.0, None)             # Phase F per-node variance
    era_var = var_model + sigma2 * Rbb                        # add anchoring resistance
    era_ci = Z95 * np.sqrt(era_var)

    inv = {v: k for k, v in nodes.items()}
    return dict(M=M, nodes=nodes, inv=inv, sbd=sbd, N=N, spanning=spanning,
                backbone=backbone, free=free, L=L, b=b, Rbb=Rbb, mu=mu,
                r_f=r_f, r_f_bb=r_f_bb, r=r, sigma2=sigma2, era_ci=era_ci,
                var_model=var_model, med_free=med_free, thin_thr=thin_thr)


def _flag(Rbb_i, thin_thr):
    if Rbb_i > DISCONNECT_R:
        return "unanchored"          # disconnected from the spine: no cross-era claim
    if Rbb_i > thin_thr:
        return "thin"                # thinly bridged: wide cross-era interval
    return "anchored"


def build(con):
    G = compute(con)
    nodes, inv, Rbb, r, r_f = G["nodes"], G["inv"], G["Rbb"], G["r"], G["r_f_bb"]
    era_ci, thin_thr = G["era_ci"], G["thin_thr"]
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    code = dict(con.execute("SELECT driverId, code FROM dim_drivers").fetchall())
    spanning = G["spanning"]

    rows = []
    for (d, s), i in nodes.items():
        flag = _flag(Rbb[i], thin_thr)
        rows.append((d, name.get(d), code.get(d), s,
                     round(float(r[i]), 4), round(float(r_f[i]), 4),
                     round(float(Rbb[i]), 4), round(float(era_ci[i]), 4),
                     round(float(r[i] - era_ci[i]), 4), round(float(r[i] + era_ci[i]), 4),
                     int(d in spanning), flag, 1))
    con.execute("""CREATE OR REPLACE TABLE driver_season_pace_era_estimate (
        driverId INT, driver_name VARCHAR, code VARCHAR, season INT,
        rating_era_s_estimate DOUBLE, rating_phasef_s DOUBLE,
        backbone_resistance DOUBLE, era_ci95_halfwidth_s DOUBLE,
        era_ci95_low DOUBLE, era_ci95_high DOUBLE,
        is_spanning_bridge INT, anchor_flag VARCHAR, is_estimate INT)""")
    con.executemany(
        "INSERT INTO driver_season_pace_era_estimate VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    # reconstruction residuals under the era-normalised ratings
    res = []
    for i, j, d, w in G["M"]["tm"]:
        res.append((round(float(d), 4), round(float(r[i] - r[j]), 4),
                    round(float(d - (r[i] - r[j])), 4)))
    con.execute("""CREATE OR REPLACE TABLE pace_model_era_residual (
        measured_delta_s DOUBLE, predicted_delta_s DOUBLE, residual_s DOUBLE)""")
    con.executemany("INSERT INTO pace_model_era_residual VALUES (?,?,?)", res)

    # era-bridge density: spanning drivers straddling each era boundary
    sbd = G["sbd"]
    bridge_rows = []
    for cut in ERA_CUTS:
        straddle = [d for d in spanning if min(sbd[d]) <= cut and max(sbd[d]) >= cut + 1]
        bridge_rows.append((cut, cut + 1, len(straddle)))
    con.execute("""CREATE OR REPLACE TABLE era_bridge_density (
        era_lo_last INT, era_hi_first INT, n_spanning_bridges INT)""")
    con.executemany("INSERT INTO era_bridge_density VALUES (?,?,?)", bridge_rows)

    for t in ["driver_season_pace_era_estimate", "pace_model_era_residual",
              "era_bridge_density"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    resid = np.array([x[2] for x in res])
    print("=" * 78); print("PHASE G — ERA-NORMALISATION via spanning-driver bridges (estimate)"); print("=" * 78)
    print(f"  {len(spanning)} spanning bridge drivers; "
          f"{len(G['backbone'])} backbone / {len(G['free'])} free driver-season nodes")
    print(f"  shrinkage K0={K0} toward spine consensus, gauge: mean(backbone)=0")
    print(f"  R_bb(free): median={G['med_free']:.4f}  thin>{G['thin_thr']:.4f}  "
          f"({int((Rbb[np.array(G['free'])] > G['thin_thr']).sum())} thin, "
          f"{int((Rbb > DISCONNECT_R).sum())} unanchored)")
    print(f"  reconstruction: median|resid|={np.median(np.abs(resid)):.3f}s  "
          f"RMS={np.sqrt((resid**2).mean()):.3f}s")
    print(f"  wrote driver_season_pace_era_estimate ({len(rows)}), "
          f"pace_model_era_residual ({len(res)}), era_bridge_density ({len(bridge_rows)})")
    return G


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE G: done.")


if __name__ == "__main__":
    main()
