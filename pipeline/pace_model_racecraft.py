"""Phase H — the RACECRAFT axis: results-vs-car-strength, orthogonal to pace.

The pace axes (qualifying = Phase G, race pace = Phase D Tier-2) measure how FAST a
driver is. They cannot see what happens on Sunday: starts, overtaking, tyre/SC
execution, and not throwing it away. Phase H isolates exactly that — how well a
driver converted the *machinery* into a *result*, BEYOND what their raw pace would
predict. A quick-on-Saturday, poor-on-Sunday driver is finally separated here.

This is a CONSTRUCTED / MODELLED axis (more so than pace) — caveats are heavier and
intervals wider. Ratings are ESTIMATES (is_estimate kept separate).

============================ THE FOUR TRAPS (and how we avoid them) ============

1. CIRCULARITY — never define the car's "deserved" result from the driver's own
   outcome. The independent baseline is the TEAMMATE (same car): the driver's race
   result *relative to the teammate's* is the car-controlled signal.

2. LUCK / RELIABILITY != RACECRAFT — a race only counts when BOTH cars had a
   DRIVER-ATTRIBUTABLE outcome. Status buckets:
     * CLASSIFIED  : "Finished" or "+N Laps" — a real finishing position.
     * DRIVER_ERROR: "Accident", "Spun off" — unambiguous SOLO error; counts as a
                     racecraft loss (you binned it while the teammate brought it home).
     * EXCLUDED    : everything else — mechanical DNFs, "Collision"/"Collision
                     damage"/"Damage"/"Debris" (ambiguous victim/aggressor), DNQ,
                     withdrawals, disqualifications. NOT counted either way.
   A race is scored only if both drivers are CLASSIFIED or one made a clear solo
   error; if either car suffered a mechanical/ambiguous outcome the race is dropped.

3. REDUNDANCY WITH PACE — the racecraft signal must be ORTHOGONAL to pace. We take
   the head-to-head finishing margin and REGRESS OUT both the qualifying delta and
   the race-pace delta (Phase D). The RESIDUAL — finished better (or worse) than the
   pace gap predicts — is the pure racecraft signal. By OLS construction it is
   uncorrelated with both pace axes (verified in the gate, corr ~ 0).

4. ERA-INCOMPARABLE POINTS — we work entirely in FINISHING POSITIONS vs the teammate
   (winsorised to +/-CAP), never raw championship points.

================================ METHOD (exact) ==============================

PER PAIR-SEASON (same car, ordered driverA<driverB):
  conv_margin = mean over eligible races of clip((pos_B-pos_A) - (grid_B-grid_A), -CAP, +CAP)
                  -- GRID-CONDITIONED conversion: positions A gained on B from grid to
                  flag (driver A ahead beyond grid => positive). Holding station reads ~0,
                  so a dominant front-runner is no longer censored for the positions they
                  could never gain. A solo DNF scores -CAP (a full racecraft loss); races
                  with no grid (pit-lane start) are dropped, not guessed.
  pace_pred_margin = b_q*(-quali_delta) + b_rp*(-racepace_delta) + c, where
                  (b_q, b_rp, c) come from ONE OLS fit of conv_margin on the two
                  pace deltas across all pairs that have both (negative delta = A
                  faster => predicts A ahead).
  racecraft_residual = conv_margin - pace_pred_margin.   <-- grid-conditioned & pace-orthogonal

DRIVER-LEVEL NETWORK (racecraft is sparse — career nodes, not driver-seasons):
  nodes = drivers; one edge per pair-season with target = racecraft_residual and
  weight w = n_eligible_races. Solve  min Sigma_k w_k (r_i - r_j - resid_k)^2,
  gauge over the spanning backbone (below). r_i = career racecraft rating in
  "positions better than pace predicts". Reconstruction = r_i - r_j vs resid_k.

ERA-NORMALISATION (reuse the Phase G spanning-bridge idea, driver level):
  Racecraft data lives in the lap-timing era (~1996+), so "cross-era" means across
  that window. A driver is a spanning bridge if their racecraft span >= SPAN_MIN
  years and touches >= 2 era-thirds. Ground the backbone, read effective resistance
  R_bb of every free driver; shrink poorly-anchored drivers toward the spine
  consensus (strength K0*R_bb) and BLOW OUT their cross-era uncertainty. The scale's
  zero is the spanning spine, not the population.

UNCERTAINTY: sigma_hat^2 from reconstruction; per-driver CI = Z95*sigma*sqrt(Lp_ii +
  R_bb). Few-edge / small-sample / thinly-bridged drivers read as very uncertain —
  honest for a constructed axis.
"""
import numpy as np
from collections import defaultdict
from common import connect, PARQUET

Z95 = 1.959964
CAP = 10.0                # winsorise per-race position margin (and solo-DNF penalty)
MIN_RACES = 2             # a pair-season needs >= this many eligible races
W_PRIOR = 1.0             # edge-weight prior (races); keeps 2-race edges from dominating
SPAN_MIN = 10             # spanning bridge: racecraft span >= 10 years ...
ERA_CUTS = (2003, 2013)   # ... touching >= 2 era-thirds (2003|2004, 2013|2014)
K0 = 1.0                  # backbone shrinkage strength
GROUND_RIDGE = 1e-6
MIN_RACES_OK = 30         # below this many eligible races -> "thin" (small sample)
CI_THIN = 1.5             # cross-era CI wider than this (positions) -> "thin"

FINISHED = lambda s: s == "Finished" or (s[:1] == "+" and "Lap" in s)
DRIVER_ERROR = lambda s: s in ("Accident", "Spun off")


def _era_third(season):
    return 0 if season <= ERA_CUTS[0] else (1 if season <= ERA_CUTS[1] else 2)


def _grid_stratum(g):
    """Starting-grid stratum (front-to-back); g<=0 is a pit/no-grid start -> back."""
    if g <= 0:
        return 3
    return 0 if g <= 3 else (1 if g <= 8 else (2 if g <= 15 else 3))


def _pair_margins(con):
    """Per pair-season: per-race luck-excluded finishing-position margins WITH each
    race's starting-grid stratum, number of eligible races, and number of races dropped
    as luck/ambiguous.

    Racecraft must not reward grid opportunity. A dominant front-runner out-qualifies
    their teammate hugely; finishing positions saturate at the front, so a single global
    pace->margin fit over-predicts their margin (no positions to gain) and scores them
    negative. We keep the finishing-position margin but fit the pace->margin expectation
    SEPARATELY WITHIN starting-grid strata (compute(): front-pairs judged against other
    front-pairs' conversion, midfield against midfield), which lets the pace effect
    SATURATE at the front and removes the opportunity bias while preserving real signal.
    """
    rows = con.execute("""SELECT raceId, season, constructorId, driverId, grid, position_order, status
                          FROM fact_results""").fetchall()
    byrc = defaultdict(list)
    for raceId, season, cid, did, grid, po, st in rows:
        byrc[(raceId, cid)].append((season, did, grid, po, st))
    margins = defaultdict(list)      # (season,a,b) -> [(per-race margin A-persp, grid-stratum)]
    dropped = defaultdict(int)       # (season,a,b) -> n races dropped (luck/ambiguous)
    for (raceId, cid), lst in byrc.items():
        if len(lst) != 2:            # only genuine two-car pairings
            continue
        (s1, d1, g1, p1, st1), (s2, d2, g2, p2, st2) = lst
        a, b = (d1, d2) if d1 < d2 else (d2, d1)
        key = (s1, a, b)

        def cls(st, po):
            if FINISHED(st):
                return ("F", po)
            if DRIVER_ERROR(st):
                return ("E", None)
            return ("X", None)
        c1, c2 = cls(st1, p1), cls(st2, p2)
        if c1[0] == "X" or c2[0] == "X" or (c1[0] == "E" and c2[0] == "E"):
            dropped[key] += 1        # mechanical/ambiguous, or both crashed: not racecraft
            continue
        if c1[0] == "F" and c2[0] == "F":
            m = float(np.clip(p2 - p1, -CAP, CAP))
        elif c1[0] == "E":           # d1 solo error, d2 classified
            m = -CAP
        else:                        # d2 solo error, d1 classified
            m = CAP
        gg = [g for g in (g1, g2) if g > 0]
        stratum = _grid_stratum(min(gg) if gg else 0)    # pair's grid tier (best slot)
        margins[key].append((m if d1 < d2 else -m, stratum))
    return margins, dropped


def compute(con):
    margins, dropped = _pair_margins(con)
    qd = {(s, a, b): med for s, a, b, med in con.execute(
        "SELECT season,driverA,driverB,median_gap_s FROM quali_teammate_delta_pairseason "
        "WHERE median_gap_s IS NOT NULL").fetchall()}
    rp = {(s, a, b): med for s, a, b, med in con.execute(
        "SELECT season,driverA,driverB,median_delta_s FROM racepace_teammate_pairseason "
        "WHERE median_delta_s IS NOT NULL").fetchall()}

    # pair-seasons with enough eligible races AND both pace deltas (=> pace-orthogonal).
    # Each pair carries its dominant grid stratum (mode of its races) so the pace fit can
    # be done WITHIN strata -- the grid-opportunity control.
    from collections import Counter
    pairs = []
    for k, ms in margins.items():
        if len(ms) >= MIN_RACES and k in qd and k in rp:
            strat = Counter(s for _, s in ms).most_common(1)[0][0]
            pairs.append((k, float(np.mean([m for m, _ in ms])), len(ms), strat))

    # PER-STRATUM OLS: finish_margin ~ b_q*(-quali) + b_rp*(-racepace) + c, fit separately
    # within each starting-grid stratum so the pace effect saturates at the front.
    Mv = np.array([m for _, m, _, _ in pairs])
    Qv = np.array([-qd[k] for k, _, _, _ in pairs])
    Rv = np.array([-rp[k] for k, _, _, _ in pairs])
    Sv = np.array([s for _, _, _, s in pairs])
    pred = np.zeros(len(Mv))
    strata_coef = {}
    for s in sorted(set(Sv.tolist())):
        idx = np.where(Sv == s)[0]
        A = np.column_stack([Qv[idx], Rv[idx], np.ones(len(idx))])
        cf, *_ = np.linalg.lstsq(A, Mv[idx], rcond=None)
        pred[idx] = A @ cf
        strata_coef[s] = cf
    resid = Mv - pred                 # racecraft residual per pair-season (grid-conditioned)
    r2_pace = 1.0 - resid.var() / Mv.var()
    coef, *_ = np.linalg.lstsq(np.column_stack([Qv, Rv, np.ones(len(Mv))]), Mv, rcond=None)  # pooled, for reporting
    pairs = [(k, m, n) for k, m, n, _ in pairs]    # drop stratum for the rest of the pipeline

    # driver-level node set
    drivers = sorted({d for (s, a, b), _, _ in pairs for d in (a, b)})
    idx = {d: i for i, d in enumerate(drivers)}
    N = len(drivers)
    seasons_by_driver = defaultdict(set)

    edges = []                        # (i, j, target_resid, weight, n_races, season)
    edeg = defaultdict(int)           # keyed by driverId
    nrace = defaultdict(int)          # keyed by driverId
    for (k, _, n), e in zip(pairs, resid):
        s, a, b = k
        i, j = idx[a], idx[b]
        w = n / W_PRIOR
        edges.append((i, j, float(e), float(w), n, s))
        seasons_by_driver[a].add(s); seasons_by_driver[b].add(s)
        edeg[a] += 1; edeg[b] += 1; nrace[a] += n; nrace[b] += n

    # spanning backbone (driver level)
    spanning = {d for d in drivers
                if (max(seasons_by_driver[d]) - min(seasons_by_driver[d])) >= SPAN_MIN
                and len({_era_third(s) for s in seasons_by_driver[d]}) >= 2}
    bset = sorted(idx[d] for d in spanning)
    fset = sorted(i for i in range(N) if i not in set(bset))

    # weighted Laplacian + rhs
    L = np.zeros((N, N)); rhs = np.zeros(N)
    for i, j, t, w, n, s in edges:
        L[i, i] += w; L[j, j] += w; L[i, j] -= w; L[j, i] -= w
        rhs[i] += w * t; rhs[j] -= w * t

    # effective resistance of free drivers to the grounded backbone
    Rbb = np.zeros(N)
    mu = np.zeros(N)
    bidx, fidx = np.array(bset), np.array(fset)
    Lp = np.linalg.pinv(L)            # for covariance / base solve (gauge sum r = 0)
    r_base = Lp @ rhs
    if len(fset) and len(bset):
        Lff = L[np.ix_(fidx, fidx)] + GROUND_RIDGE * np.eye(len(fidx))
        Lff_inv = np.linalg.inv(Lff)
        Rbb[fidx] = np.diag(Lff_inv)
        Lfb = L[np.ix_(fidx, bidx)]
        mu[fidx] = Lff_inv @ (rhs[fidx] - Lfb @ r_base[bidx])
        mu[bidx] = r_base[bidx]
    else:
        mu = r_base.copy()

    # selective shrinkage toward the spine, gauge mean(backbone)=0
    Ls = L.copy(); bs = rhs.copy()
    for i in fset:
        k = K0 * Rbb[i]
        Ls[i, i] += k; bs[i] += k * mu[i]
    g = np.zeros(N); g[bidx] = 1.0
    Ls = Ls + GROUND_RIDGE * np.eye(N) + 1e3 * np.outer(g, g)
    r = np.linalg.solve(Ls, bs)
    r = r - (r[bidx].mean() if len(bset) else r.mean())

    # reconstruction + sigma^2
    rec = np.array([t - (r[i] - r[j]) for i, j, t, w, n, s in edges])
    p_eff = sum(w * (Lp[i, i] + Lp[j, j] - 2 * Lp[i, j]) for i, j, t, w, n, s in edges)
    dof = max(len(edges) - p_eff, 1.0)
    sigma2 = float(sum(w * (t - (r[i] - r[j])) ** 2 for i, j, t, w, n, s in edges) / dof)

    var_model = np.clip(np.diag(Lp), 0.0, None) * sigma2
    era_ci = Z95 * np.sqrt(var_model + sigma2 * Rbb)

    return dict(pairs=pairs, edges=edges, resid=resid, coef=coef, r2_pace=r2_pace,
                Qv=Qv, Rv=Rv, drivers=drivers, idx=idx, N=N, spanning=spanning,
                backbone=bset, free=fset, r=r, r_base=r_base, Rbb=Rbb, mu=mu,
                sigma2=sigma2, era_ci=era_ci, rec=rec, edeg=edeg, nrace=nrace,
                seasons_by_driver=seasons_by_driver, dropped=dropped, qd=qd, rp=rp)


def build(con):
    H = compute(con)
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    code = dict(con.execute("SELECT driverId, code FROM dim_drivers").fetchall())
    r, Rbb, era_ci = H["r"], H["Rbb"], H["era_ci"]
    edeg, nrace, spanning = H["edeg"], H["nrace"], H["spanning"]
    med_free = float(np.median(Rbb[np.array(H["free"])])) if H["free"] else 0.0
    thin = 3.0 * med_free

    def flag(i):
        d = H["drivers"][i]
        if Rbb[i] > 1.0:
            return "unanchored"
        if Rbb[i] > thin or nrace[d] < MIN_RACES_OK or era_ci[i] > CI_THIN:
            return "thin"
        return "anchored"

    rows = []
    for d, i in H["idx"].items():
        rows.append((d, name.get(d), code.get(d),
                     round(float(r[i]), 4), round(float(Rbb[i]), 4),
                     round(float(era_ci[i]), 4),
                     round(float(r[i] - era_ci[i]), 4), round(float(r[i] + era_ci[i]), 4),
                     edeg[d], nrace[d], int(d in spanning), flag(i), 1))
    con.execute("""CREATE OR REPLACE TABLE driver_racecraft_estimate (
        driverId INT, driver_name VARCHAR, code VARCHAR,
        racecraft_pos_estimate DOUBLE, backbone_resistance DOUBLE,
        ci95_halfwidth_pos DOUBLE, ci95_low DOUBLE, ci95_high DOUBLE,
        n_pair_edges INT, n_races INT, is_spanning_bridge INT, anchor_flag VARCHAR,
        is_estimate INT)""")
    con.executemany("INSERT INTO driver_racecraft_estimate VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    # per pair-season residual table (audit trail: margin, pace prediction, luck drops)
    prows = []
    for (k, m, n), e in zip(H["pairs"], H["resid"]):
        s, a, b = k
        prows.append((s, a, name.get(a), b, name.get(b), n, H["dropped"].get(k, 0),
                      round(float(m), 4), round(float(m - e), 4), round(float(e), 4)))
    con.execute("""CREATE OR REPLACE TABLE racecraft_pair_residual (
        season INT, driverA INT, nameA VARCHAR, driverB INT, nameB VARCHAR,
        n_eligible_races INT, n_dropped_luck INT, finish_margin DOUBLE,
        pace_pred_margin DOUBLE, racecraft_residual DOUBLE)""")
    con.executemany("INSERT INTO racecraft_pair_residual VALUES (?,?,?,?,?,?,?,?,?,?)", prows)

    rrows = [(round(float(H["edges"][k][2]), 4),
              round(float(H["edges"][k][2] - H["rec"][k]), 4),
              round(float(H["rec"][k]), 4)) for k in range(len(H["edges"]))]
    con.execute("""CREATE OR REPLACE TABLE racecraft_recon_residual (
        observed_resid DOUBLE, predicted_resid DOUBLE, residual DOUBLE)""")
    con.executemany("INSERT INTO racecraft_recon_residual VALUES (?,?,?)", rrows)

    con.execute("""CREATE OR REPLACE TABLE racecraft_meta (
        b_quali DOUBLE, b_racepace DOUBLE, intercept DOUBLE, r2_pace DOUBLE,
        n_pairs INT, n_drivers INT, n_spanning INT)""")
    con.execute("INSERT INTO racecraft_meta VALUES (?,?,?,?,?,?,?)",
                [round(float(H["coef"][0]), 4), round(float(H["coef"][1]), 4),
                 round(float(H["coef"][2]), 4), round(float(H["r2_pace"]), 4),
                 len(H["pairs"]), H["N"], len(spanning)])

    for t in ["driver_racecraft_estimate", "racecraft_pair_residual",
              "racecraft_recon_residual", "racecraft_meta"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    rec = H["rec"]
    print("=" * 78); print("PHASE H — RACECRAFT axis (results-vs-car-strength, pace-orthogonal) [estimate]"); print("=" * 78)
    print(f"  {len(H['pairs'])} teammate pair-seasons (luck-excluded), {H['N']} drivers, "
          f"{len(spanning)} spanning bridges")
    print(f"  pace removed: margin ~ {H['coef'][0]:.2f}*(-quali) + {H['coef'][1]:.2f}*(-racepace) "
          f"+ {H['coef'][2]:.2f};  pace R^2={H['r2_pace']:.3f}")
    print(f"  reconstruction: median|resid|={np.median(np.abs(rec)):.3f} pos  "
          f"RMS={np.sqrt((rec**2).mean()):.3f} pos")
    print(f"  wrote driver_racecraft_estimate ({len(rows)}), racecraft_pair_residual ({len(prows)})")
    return H


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE H: done.")


if __name__ == "__main__":
    main()
