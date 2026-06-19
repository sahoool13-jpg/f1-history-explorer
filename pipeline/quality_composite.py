"""Phase J/K — COMBINATION + USER-WEIGHTING layer for the driver-quality model.

The three axes are measured honestly and orthogonally:
  G  era-normalised PACE        (seconds vs the era backbone; lower = faster)
  H  RACECRAFT                  (finishing positions vs what pace predicts)
  I  LONGEVITY                  (effective competitive seasons)

Phase J combines them into a composite WITHOUT asserting a single weighting: the model
measures the axes; the USER decides how much each counts. Phase K refines the
combination with interval-aware shrinkage, a within-era option, and visible era stats.

================================ METHOD (exact) ==============================

REFERENCE POPULATION — the >=4-season GENUINE CAREERS that have all three axes (the
Phase-I genuine-career set, not all 172 drivers; cameos would distort the spread).

NORMALISE (two modes, both selectable in the UI; CROSS-ERA is the default):
  * CROSS-ERA — z-score each axis against the WHOLE reference population (mean 0, sd 1),
    oriented so higher = better. This keeps the real cross-era gradient (1990s fields
    were genuinely more spread out — "field compression"), comparing every driver to one
    fixed cross-era spine.
  * WITHIN-ERA — z-score each axis WITHIN the driver's era-third cohort (1994-2003 /
    2004-2013 / 2014-2024, by Phase-G career midpoint). Answers "standing among
    contemporaries"; flattens each era's mean to 0 by construction (so it ASSUMES equal
    era depth — offered as a user choice, never as the silent default).

INTERVAL-AWARE SHRINKAGE (empirical Bayes) — applied to BOTH modes. Each axis estimate
z carries measurement noise sigma_z; model z = theta + eps, eps ~ N(0, sigma_z^2),
theta ~ N(0, tau^2). Estimate tau^2 = Var(z) - mean(sigma_z^2) per axis, then
    z_shrunk = z * tau^2 / (tau^2 + sigma_z^2)          (toward 0 = population mean)
    sigma_shrunk = sqrt( tau^2 * sigma_z^2 / (tau^2 + sigma_z^2) )   (tighter posterior)
Wide-interval estimates (thin-data early-era racecraft) shrink hard toward 0; tight ones
barely move. This is ERA-NEUTRAL (it depends only on each driver's interval, not era):
it kills noise-as-signal without erasing the real field-compression pace gradient (pace
intervals are tight, so pace barely shrinks). Verified: era cohort means are preserved.

COMPOSITE — with user weights (w_g, w_h, w_i) >= 0 normalised to sum 1, on the SHRUNK
axes of the chosen mode:
    composite = w_g z_g_shrunk + w_h z_h_shrunk + w_i z_i_shrunk
    sigma_composite = sqrt( sum (w_axis * sigma_axis_shrunk)^2 )   (axes orthogonal)
    composite CI = Z95 * sigma_composite
Default weights EQUAL (1/3 each), labelled arbitrary. Overlapping composite intervals
read as "not confidently separable" — never asserted as a strict order.

COVERAGE — a driver gets a full composite ONLY if they have all three axes AND a genuine
(>=4-season) career. Everyone else is flagged 'partial' (missing axis named), never
zero-filled or dropped.

Ratings remain ESTIMATES; longevity is the softest axis and may legitimately be 0.
"""
import numpy as np
from common import connect, PARQUET

Z95 = 1.959964
MIN_SEASONS = 4           # genuine-career threshold (matches Phase I reference set)
ERA_CUTS = (2003, 2013)   # era-third boundaries (by Phase-G career midpoint)


def _cohort(mid):
    return "1994-2003" if mid <= ERA_CUTS[0] else ("2004-2013" if mid <= ERA_CUTS[1] else "2014-2024")


def _eb_shrink(zs, szs):
    """Empirical-Bayes shrink an array of z-estimates with per-item z-scale sigmas.
    Returns (shrunk z, shrunk sigma, tau2). Shrinks toward 0 (the population mean)."""
    z = np.asarray(zs, float); v = np.asarray(szs, float) ** 2
    tau2 = max(float(np.var(z) - np.mean(v)), 1e-3)
    b = tau2 / (tau2 + v)                      # shrink factor in [0,1]
    return z * b, np.sqrt(tau2 * v / (tau2 + v)), tau2


def _career_pace(con):
    """Inverse-variance weighted career pace (G) + its CI, per driver."""
    rows = con.execute("""SELECT driverId, rating_era_s_estimate, era_ci95_halfwidth_s
                          FROM driver_season_pace_era_estimate""").fetchall()
    by = {}
    for d, r, ci in rows:
        sig = max(ci / Z95, 1e-6)
        by.setdefault(d, []).append((float(r), sig))
    pace, pace_ci = {}, {}
    for d, lst in by.items():
        w = np.array([1.0 / s ** 2 for _, s in lst])
        rr = np.array([r for r, _ in lst])
        pace[d] = float((w * rr).sum() / w.sum())
        pace_ci[d] = float(Z95 * np.sqrt(1.0 / w.sum()))
    return pace, pace_ci


def compute(con):
    pace, pace_ci = _career_pace(con)
    H = {d: (float(v), float(ci)) for d, v, ci in con.execute(
        "SELECT driverId, racecraft_pos_estimate, ci95_halfwidth_pos FROM driver_racecraft_estimate").fetchall()}
    I = {d: (float(v), float(ci), int(ns), int(act)) for d, v, ci, ns, act in con.execute(
        "SELECT driverId, longevity_estimate, ci95_halfwidth, n_seasons, is_active "
        "FROM driver_longevity_estimate").fetchall()}
    gspan = {d: (lo, hi) for d, lo, hi in con.execute(
        "SELECT driverId, min(season), max(season) FROM driver_season_pace_era_estimate GROUP BY 1").fetchall()}

    universe = set(I) | set(pace) | set(H)

    def has_all(d):
        return d in pace and d in H and d in I

    def cohort(d):
        lo, hi = gspan.get(d, (2010, 2010))
        return _cohort((lo + hi) / 2.0)

    # reference population = genuine careers (>=4 seasons) with all three axes
    ref = [d for d in universe if has_all(d) and I[d][2] >= MIN_SEASONS]

    # ---- oriented raw axis values (higher = better) + raw measurement sigma -----
    # LONGEVITY is heavily right-skewed (a few 18-21y careers stretch the tail), so at
    # equal nominal weight it swings the top of the board far more than pace/craft. We
    # tame it with a sqrt transform BEFORE standardising (sqrt symmetrises it to skew~0;
    # log/cbrt over-correct), propagating its CI by the delta method:
    #   value -> sqrt(L),  sigma -> sigma_L / (2 sqrt(L)).
    # PACE is left-skewed but is NOT transformed: the axis exists to preserve the
    # seconds-magnitude signal; a monotone transform would discard it (no special pleading
    # -- we report pace's skew but justify keeping its magnitude). RACECRAFT is near
    # symmetric and is left as-is.
    def _sqrtL(L):
        Lc = max(L, 1e-3)
        return np.sqrt(Lc), 1.0 / (2.0 * np.sqrt(Lc))     # value, d/dL
    raw = {  # axis -> driver -> (value, sigma)
        "pace": {d: (-pace[d], pace_ci[d] / Z95) for d in ref},
        "race": {d: (H[d][0], H[d][1] / Z95) for d in ref},
        "long": {d: (_sqrtL(I[d][0])[0], (I[d][1] / Z95) * _sqrtL(I[d][0])[1]) for d in ref},
    }

    def standardize(axis, ids):
        """z-score axis over the given driver id set; returns (z dict, sigma_z dict)."""
        xs = np.array([raw[axis][d][0] for d in ids])
        mu, sd = float(xs.mean()), float(xs.std()) or 1.0
        z = {d: (raw[axis][d][0] - mu) / sd for d in ids}
        sz = {d: raw[axis][d][1] / sd for d in ids}
        return z, sz, mu, sd

    AX = ["pace", "race", "long"]
    cohorts = {d: cohort(d) for d in ref}
    by_cohort = {}
    for d in ref:
        by_cohort.setdefault(cohorts[d], []).append(d)

    norm = {"cross": {}, "within": {}}     # mode -> axis -> {z, sz, zs, szs, tau2}
    meta_norm = {"cross": {}, "within": {}}
    for axis in AX:
        # CROSS: standardize over whole ref, then EB shrink
        zc, szc, mu, sd = standardize(axis, ref)
        ids = list(ref)
        zs, szs, tau2 = _eb_shrink([zc[d] for d in ids], [szc[d] for d in ids])
        norm["cross"][axis] = dict(z=zc, sz=szc,
            zs={d: float(zs[i]) for i, d in enumerate(ids)},
            szs={d: float(szs[i]) for i, d in enumerate(ids)})
        meta_norm["cross"][axis] = dict(mu=mu, sd=sd, tau2=tau2)
        # WITHIN: standardize per cohort, then EB shrink over the pooled within-era z
        zw, szw = {}, {}
        for coh, ids_c in by_cohort.items():
            zci, szci, _, _ = standardize(axis, ids_c)
            zw.update(zci); szw.update(szci)
        ids = list(ref)
        zs, szs, tau2 = _eb_shrink([zw[d] for d in ids], [szw[d] for d in ids])
        norm["within"][axis] = dict(z=zw, sz=szw,
            zs={d: float(zs[i]) for i, d in enumerate(ids)},
            szs={d: float(szs[i]) for i, d in enumerate(ids)})
        meta_norm["within"][axis] = dict(tau2=tau2)

    drivers = {}
    for d in universe:
        ns = I[d][2] if d in I else 0
        act = I[d][3] if d in I else 0
        hp, hh, hi = d in pace, d in H, d in I
        eligible = has_all(d) and ns >= MIN_SEASONS
        missing = [a for a, has in [("pace", hp), ("racecraft", hh), ("longevity", hi)] if not has]
        if ns < MIN_SEASONS and ns > 0:
            missing.append(f"short-career({ns}s)")
        rec = dict(n_seasons=ns, is_active=act, eligible=eligible,
                   cohort=cohort(d) if eligible else None,
                   pace=pace.get(d), pace_ci=pace_ci.get(d),
                   race=H[d][0] if hh else None, race_ci=H[d][1] if hh else None,
                   longv=I[d][0] if hi else None, longv_ci=I[d][1] if hi else None,
                   missing=missing)
        if eligible:
            for mode in ("cross", "within"):
                rec[mode] = dict(
                    zs=[norm[mode][a]["zs"][d] for a in AX],
                    szs=[norm[mode][a]["szs"][d] for a in AX],
                    z=[norm[mode][a]["z"][d] for a in AX],      # unshrunk z (transparency)
                    sz=[norm[mode][a]["sz"][d] for a in AX])    # unshrunk sigma (for CI compare)
        drivers[d] = rec
    meta = dict(ref_n=len(ref), min_seasons=MIN_SEASONS, norm=meta_norm,
                cohort_counts={c: len(v) for c, v in by_cohort.items()})
    return drivers, meta


def composite(drivers, wg, wh, wi, mode="cross"):
    """Weighted composite (weights normalised to sum 1) on the SHRUNK axes of `mode`.
    Returns sorted [(driverId, score, ci)]."""
    s = wg + wh + wi
    if s <= 0:
        wg = wh = wi = 1.0; s = 3.0
    w = [wg / s, wh / s, wi / s]
    out = []
    for d, m in drivers.items():
        if not m["eligible"]:
            continue
        zs, szs = m[mode]["zs"], m[mode]["szs"]
        c = sum(w[k] * zs[k] for k in range(3))
        ci = Z95 * np.sqrt(sum((w[k] * szs[k]) ** 2 for k in range(3)))
        out.append((d, float(c), float(ci)))
    out.sort(key=lambda x: -x[1])
    return out


def build(con):
    drivers, meta = compute(con)
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    code = dict(con.execute("SELECT driverId, code FROM dim_drivers").fetchall())

    def rnd(x, n=4):
        return None if x is None else round(float(x), n)

    rows = []
    for d, m in drivers.items():
        e = m["eligible"]
        cz = m["cross"]["zs"] if e else [None] * 3
        cs = m["cross"]["szs"] if e else [None] * 3
        wz = m["within"]["zs"] if e else [None] * 3
        ws = m["within"]["szs"] if e else [None] * 3
        rows.append((d, name.get(d), code.get(d), m["n_seasons"], m["is_active"],
                     m["cohort"], int(m["pace"] is not None), int(m["race"] is not None),
                     int(m["longv"] is not None), int(e),
                     rnd(m["pace"]), rnd(m["race"]), rnd(m["longv"]),
                     rnd(cz[0]), rnd(cz[1]), rnd(cz[2]), rnd(cs[0]), rnd(cs[1]), rnd(cs[2]),
                     rnd(wz[0]), rnd(wz[1]), rnd(wz[2]), rnd(ws[0]), rnd(ws[1]), rnd(ws[2]),
                     ",".join(m["missing"]), 1))
    con.execute("""CREATE OR REPLACE TABLE driver_quality_axes (
        driverId INT, driver_name VARCHAR, code VARCHAR, n_seasons INT, is_active INT,
        cohort VARCHAR, has_pace INT, has_racecraft INT, has_longevity INT,
        is_composite_eligible INT, pace_s DOUBLE, racecraft_pos DOUBLE, longevity DOUBLE,
        zc_pace DOUBLE, zc_race DOUBLE, zc_long DOUBLE,
        szc_pace DOUBLE, szc_race DOUBLE, szc_long DOUBLE,
        zw_pace DOUBLE, zw_race DOUBLE, zw_long DOUBLE,
        szw_pace DOUBLE, szw_race DOUBLE, szw_long DOUBLE,
        missing_axes VARCHAR, is_estimate INT)""")
    con.executemany("INSERT INTO driver_quality_axes VALUES "
                    "(" + ",".join(["?"] * 27) + ")", rows)

    con.execute("""CREATE OR REPLACE TABLE quality_norm_meta (
        mode VARCHAR, axis VARCHAR, tau2 DOUBLE, ref_n INT, reference_population VARCHAR)""")
    refdesc = f">=4-season careers with all three axes (n={meta['ref_n']})"
    mrows = []
    for mode in ("cross", "within"):
        for axis in ("pace", "race", "long"):
            mrows.append((mode, axis, round(meta["norm"][mode][axis]["tau2"], 4),
                          meta["ref_n"], refdesc))
    con.executemany("INSERT INTO quality_norm_meta VALUES (?,?,?,?,?)", mrows)

    for t in ["driver_quality_axes", "quality_norm_meta"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    nelig = sum(1 for m in drivers.values() if m["eligible"])
    npart = len(drivers) - nelig
    print("=" * 78); print("PHASE J/K — COMBINATION + USER-WEIGHTING (composite driver-quality) [estimate]"); print("=" * 78)
    print(f"  {len(drivers)} drivers; {nelig} composite-eligible (all 3 axes, >={MIN_SEASONS} seasons), "
          f"{npart} partial (flagged)")
    print(f"  cohorts: " + ", ".join(f"{c} {n}" for c, n in sorted(meta["cohort_counts"].items())))
    tp = meta["norm"]["cross"]
    print(f"  EB shrink (cross) tau^2: pace {tp['pace']['tau2']:.2f}  race {tp['race']['tau2']:.2f}  "
          f"long {tp['long']['tau2']:.2f}  (lower tau^2 = more shrink; race is the noisy axis)")
    print(f"  modes: CROSS-ERA (default, keeps field-compression) + WITHIN-ERA (peers); both EB-shrunk")
    print(f"  wrote driver_quality_axes ({len(rows)}), quality_norm_meta ({len(mrows)})")
    return drivers, meta


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE J/K: done.")


if __name__ == "__main__":
    main()
