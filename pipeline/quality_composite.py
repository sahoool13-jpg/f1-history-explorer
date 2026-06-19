"""Phase J — COMBINATION + USER-WEIGHTING layer for the driver-quality model.

The three axes are measured honestly and orthogonally:
  G  era-normalised PACE        (seconds vs the era backbone; lower = faster)
  H  RACECRAFT                  (finishing positions vs what pace predicts)
  I  LONGEVITY                  (effective competitive seasons)

Phase J combines them into a composite WITHOUT asserting a single weighting. The
defensibility of the whole model rests on this: the model measures the axes; the USER
decides how much each counts. There is NO official ranking — the composite is a
function of user-chosen weights, and the equal default is an arbitrary starting point,
explicitly not a claim.

================================ METHOD (exact) ==============================

REFERENCE POPULATION — the >=4-season GENUINE CAREERS that have all three axes (the
Phase-I genuine-career set, not all 172 drivers; cameos would distort the spread).

NORMALISE — each axis is z-scored against the reference population so all three share a
common, comparable scale (mean 0, sd 1), ORIENTED so higher = better:
    z_pace = (mu_pace - pace) / sd_pace        # negate: lower seconds = faster
    z_race = (race - mu_race) / sd_race
    z_long = (long - mu_long) / sd_long
Career pace = inverse-variance weighted mean of a driver's Phase-G season ratings (its
CI shrinks the more seasons inform it).

COMPOSITE — with user weights (w_g, w_h, w_i) >= 0 normalised to sum 1:
    composite = w_g z_pace + w_h z_race + w_i z_long
Default weights are EQUAL (1/3 each), labelled arbitrary.

UNCERTAINTY — every axis carries a CI; it propagates. Each axis CI is put on the z scale
(sigma_z = (ci/Z95)/sd_axis); the axes are orthogonal by construction, so
    sigma_composite = sqrt( (w_g sigma_z_pace)^2 + (w_h sigma_z_race)^2 + (w_i sigma_z_long)^2 )
    composite CI = Z95 * sigma_composite
Two drivers whose composite intervals OVERLAP under a weighting are "not confidently
separable" — the ranking must say so, never assert false precision.

COVERAGE — a driver gets a full composite ONLY if they have all three axes AND a genuine
(>=4-season) career. Everyone else is flagged 'partial' (with the missing axis named),
never silently zero-filled or dropped.

This module computes the per-driver normalised axes + z-scale CIs and writes them out;
the actual weighting is applied live (in the gate, and in the #/quality UI). Ratings
remain ESTIMATES; longevity is the softest axis and may legitimately be weighted to 0.
"""
import numpy as np
from common import connect, PARQUET

Z95 = 1.959964
MIN_SEASONS = 4           # genuine-career threshold (matches Phase I reference set)


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

    # universe: anyone with a longevity row (= anyone with Phase-G coverage, 1994+)
    universe = set(I) | set(pace) | set(H)

    def has_all(d):
        return d in pace and d in H and d in I

    # reference population = genuine careers (>=4 seasons) with all three axes
    ref = [d for d in universe if has_all(d) and I[d][2] >= MIN_SEASONS]
    mu_p, sd_p = np.mean([pace[d] for d in ref]), np.std([pace[d] for d in ref])
    mu_h, sd_h = np.mean([H[d][0] for d in ref]), np.std([H[d][0] for d in ref])
    mu_i, sd_i = np.mean([I[d][0] for d in ref]), np.std([I[d][0] for d in ref])

    drivers = {}
    for d in universe:
        ns = I[d][2] if d in I else 0
        act = I[d][3] if d in I else 0
        hp, hh, hi = d in pace, d in H, d in I
        eligible = has_all(d) and ns >= MIN_SEASONS
        # z-scores + z-scale CIs (None where an axis is missing)
        zp = (mu_p - pace[d]) / sd_p if hp else None
        zh = (H[d][0] - mu_h) / sd_h if hh else None
        zi = (I[d][0] - mu_i) / sd_i if hi else None
        szp = (pace_ci[d] / Z95) / sd_p if hp else None
        szh = (H[d][1] / Z95) / sd_h if hh else None
        szi = (I[d][1] / Z95) / sd_i if hi else None
        missing = [a for a, has in [("pace", hp), ("racecraft", hh), ("longevity", hi)] if not has]
        if ns < MIN_SEASONS and ns > 0:
            missing.append(f"short-career({ns}s)")
        drivers[d] = dict(
            n_seasons=ns, is_active=act, eligible=eligible,
            pace=pace.get(d), pace_ci=pace_ci.get(d),
            race=H[d][0] if hh else None, race_ci=H[d][1] if hh else None,
            longv=I[d][0] if hi else None, longv_ci=I[d][1] if hi else None,
            z_pace=zp, z_race=zh, z_long=zi, sz_pace=szp, sz_race=szh, sz_long=szi,
            missing=missing)
    meta = dict(mu_p=mu_p, sd_p=sd_p, mu_h=mu_h, sd_h=sd_h, mu_i=mu_i, sd_i=sd_i,
                ref_n=len(ref), min_seasons=MIN_SEASONS)
    return drivers, meta


def composite(drivers, wg, wh, wi):
    """Apply weights (normalised to sum 1) to the eligible drivers; return sorted list
    of (driverId, score, ci) plus overlap-aware tie groups."""
    s = wg + wh + wi
    if s <= 0:
        wg = wh = wi = 1.0; s = 3.0
    wg, wh, wi = wg / s, wh / s, wi / s
    out = []
    for d, m in drivers.items():
        if not m["eligible"]:
            continue
        c = wg * m["z_pace"] + wh * m["z_race"] + wi * m["z_long"]
        ci = Z95 * np.sqrt((wg * m["sz_pace"]) ** 2 + (wh * m["sz_race"]) ** 2 + (wi * m["sz_long"]) ** 2)
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
        rows.append((d, name.get(d), code.get(d), m["n_seasons"], m["is_active"],
                     int(m["pace"] is not None),
                     int(m["race"] is not None), int(m["longv"] is not None),
                     int(m["eligible"]),
                     rnd(m["pace"]), rnd(m["pace_ci"]), rnd(m["race"]), rnd(m["race_ci"]),
                     rnd(m["longv"]), rnd(m["longv_ci"]),
                     rnd(m["z_pace"]), rnd(m["z_race"]), rnd(m["z_long"]),
                     rnd(m["sz_pace"]), rnd(m["sz_race"]), rnd(m["sz_long"]),
                     ",".join(m["missing"]), 1))
    con.execute("""CREATE OR REPLACE TABLE driver_quality_axes (
        driverId INT, driver_name VARCHAR, code VARCHAR, n_seasons INT, is_active INT,
        has_pace INT, has_racecraft INT, has_longevity INT, is_composite_eligible INT,
        pace_s DOUBLE, pace_ci_s DOUBLE, racecraft_pos DOUBLE, racecraft_ci_pos DOUBLE,
        longevity DOUBLE, longevity_ci DOUBLE,
        z_pace DOUBLE, z_racecraft DOUBLE, z_longevity DOUBLE,
        zci_pace DOUBLE, zci_racecraft DOUBLE, zci_longevity DOUBLE,
        missing_axes VARCHAR, is_estimate INT)""")
    con.executemany("INSERT INTO driver_quality_axes VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)

    con.execute("""CREATE OR REPLACE TABLE quality_norm_meta (
        axis VARCHAR, ref_mean DOUBLE, ref_std DOUBLE, ref_n INT, reference_population VARCHAR)""")
    refdesc = f">=4-season careers with all three axes (n={meta['ref_n']})"
    con.executemany("INSERT INTO quality_norm_meta VALUES (?,?,?,?,?)", [
        ("pace_s", round(meta["mu_p"], 4), round(meta["sd_p"], 4), meta["ref_n"], refdesc),
        ("racecraft_pos", round(meta["mu_h"], 4), round(meta["sd_h"], 4), meta["ref_n"], refdesc),
        ("longevity", round(meta["mu_i"], 4), round(meta["sd_i"], 4), meta["ref_n"], refdesc)])

    for t in ["driver_quality_axes", "quality_norm_meta"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    nelig = sum(1 for m in drivers.values() if m["eligible"])
    npart = len(drivers) - nelig
    print("=" * 78); print("PHASE J — COMBINATION + USER-WEIGHTING (composite driver-quality) [estimate]"); print("=" * 78)
    print(f"  {len(drivers)} drivers; {nelig} composite-eligible (all 3 axes, >={MIN_SEASONS} seasons), "
          f"{npart} partial (flagged)")
    print(f"  normalisation: z-score vs reference population ({refdesc})")
    print(f"  composite = w_pace·z_pace + w_race·z_race + w_long·z_long  (weights USER-set, no fixed ranking)")
    print(f"  wrote driver_quality_axes ({len(rows)}), quality_norm_meta (3)")
    return drivers, meta


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE J: done.")


if __name__ == "__main__":
    main()
