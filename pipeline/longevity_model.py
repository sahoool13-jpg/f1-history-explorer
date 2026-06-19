"""Phase I — the LONGEVITY / SUSTAINED-LEVEL axis.

Pace (G) says how fast a driver was; racecraft (H) says how well they converted it on
Sunday. Neither captures DURABILITY — the ability to STAY at a competitive level,
season after season, adapting as the sport changes. Phase I measures exactly that, and
only that. CONSTRUCTED axis — caveats are heavy, intervals honest.

============================ THE THREE TRAPS (and how we avoid them) ===========

1. RAW LENGTH REWARDS MEDIOCRITY — we do NOT count years or races. A season only
   counts to the extent the driver was COMPETITIVE that year, so a durable midfield
   journeyman does not float to the top on attendance alone.

2. OVER-ADJUSTMENT KILLS ORTHOGONALITY — we do NOT quality-weight so hard that
   longevity collapses into "good drivers score high" (that is just pace again). The
   competitiveness weight SATURATES: a clearly-competitive season counts ~fully
   whether the driver was elite or merely strong, so what survives is DURATION at a
   competitive level — a distinct dimension. (Verified: corr with pace ≈ 0.5, not 1.)

3. BREVITY != BADNESS — a brief-but-brilliant career scores MODERATE (high level, not
   sustained), never bottom. Low longevity means "did not sustain", NOT "lacked
   ability" — ability lives in the G/H axes. We flag this explicitly.

================================ METHOD (exact) ==============================

For each driver-season with a Phase-G era-normalised pace rating r_s (lower = faster,
gauged to the spanning backbone):

  competitiveness_s = sigma( (C0 - r_s) / KW )          # logistic, saturating in [0,1]
      r_s ≈ -0.2 (clearly above backbone) -> ~0.87  (near the front: counts fully)
      r_s ≈ +0.1 (grid median)            -> ~0.68  (midfield: counts substantially)
      r_s ≈ +0.8 (back of grid)           -> ~0.10  (back marker: counts little)

  presence_s = min(1, starts_s / races_in_season_s)     # partial/reserve year counts partially

  LONGEVITY = Sigma_s presence_s * competitiveness_s     # "effective competitive seasons"

So: long AND competitive -> high (Hamilton, Alonso); long midfield-journeyman -> much
lower (length discounted by weak seasons); brief but strong -> moderate (few seasons,
each counts); brief and weak -> low (Giovinazzi).

COVERAGE / LIMIT: Phase-G pace exists only where qualifying timing does (1994+), so
longevity is a MODERN-ERA axis — pre-1994 greats are out of scope, stated plainly.

UNCERTAINTY (two honest sources, added in quadrature):
  * statistical — propagate each season's G interval through the weight
    (d comp/d r = -comp(1-comp)/KW), summed over the career;
  * construction — recompute longevity across a grid of (C0, KW) and take the spread
    as a model-choice uncertainty. A constructed axis should wear its arbitrariness.
Active drivers are flagged: their longevity is "so far", not a final figure.
"""
import numpy as np
from common import connect, PARQUET

Z95 = 1.959964
C0 = 0.30                 # half-weight pace level (s slower than backbone)
KW = 0.25                 # logistic transition width (s)
GRID = [(0.20, 0.22), (0.20, 0.30), (0.30, 0.25), (0.40, 0.22), (0.40, 0.30)]  # construction sensitivity
LAST_SEASON = 2024        # dataset horizon -> active-driver flag


def _comp(r, c0=C0, k=KW):
    return 1.0 / (1.0 + np.exp((r - c0) / k))


def compute(con):
    G = con.execute("""SELECT driverId, season, rating_era_s_estimate, era_ci95_halfwidth_s
                       FROM driver_season_pace_era_estimate""").fetchall()
    bydrv = {}
    for d, s, r, ci in G:
        bydrv.setdefault(d, []).append((s, float(r), float(ci)))
    races_in = dict(con.execute("SELECT season, count(distinct raceId) FROM fact_races GROUP BY 1").fetchall())
    starts = {(d, s): c for d, s, c in
              con.execute("SELECT driverId, season, count(*) FROM fact_results GROUP BY 1,2").fetchall()}

    rows = {}
    season_rows = []
    for d, lst in bydrv.items():
        L = 0.0; var_stat = 0.0; mean_comp_num = 0.0; pres_tot = 0.0
        seasons = sorted(s for s, _, _ in lst)
        for s, r, ci in lst:
            pres = min(1.0, starts.get((d, s), 0) / max(races_in.get(s, 1), 1))
            comp = _comp(r)
            L += pres * comp
            sigma_r = ci / Z95
            dcomp = -comp * (1.0 - comp) / KW          # d comp / d r
            var_stat += (pres * dcomp * sigma_r) ** 2
            mean_comp_num += pres * comp; pres_tot += pres
            season_rows.append((d, s, round(r, 4), round(pres, 4), round(comp, 4)))
        # construction sensitivity: longevity across the (C0,KW) grid
        Lg = []
        for c0, k in GRID:
            Lg.append(sum(min(1.0, starts.get((d, s), 0) / max(races_in.get(s, 1), 1)) * _comp(r, c0, k)
                          for s, r, ci in lst))
        constr_lo, constr_hi = min(Lg), max(Lg)
        sigma_constr = (constr_hi - constr_lo) / 4.0
        sigma = float(np.sqrt(var_stat + sigma_constr ** 2))
        rows[d] = dict(n_seasons=len(lst), L=L, sigma=sigma,
                       mean_comp=(mean_comp_num / pres_tot if pres_tot else 0.0),
                       constr_lo=constr_lo, constr_hi=constr_hi,
                       active=int(max(seasons) >= LAST_SEASON))
    return rows, season_rows


def build(con):
    rows, season_rows = compute(con)
    name = dict(con.execute("SELECT driverId, full_name FROM dim_drivers").fetchall())
    code = dict(con.execute("SELECT driverId, code FROM dim_drivers").fetchall())

    out = []
    for d, m in rows.items():
        ci = Z95 * m["sigma"]
        out.append((d, name.get(d), code.get(d), m["n_seasons"],
                    round(m["L"], 4), round(ci, 4),
                    round(m["L"] - ci, 4), round(m["L"] + ci, 4),
                    round(m["mean_comp"], 4),
                    round(m["constr_lo"], 4), round(m["constr_hi"], 4),
                    m["active"], 1))
    con.execute("""CREATE OR REPLACE TABLE driver_longevity_estimate (
        driverId INT, driver_name VARCHAR, code VARCHAR, n_seasons INT,
        longevity_estimate DOUBLE, ci95_halfwidth DOUBLE, ci95_low DOUBLE, ci95_high DOUBLE,
        mean_competitiveness DOUBLE, construction_low DOUBLE, construction_high DOUBLE,
        is_active INT, is_estimate INT)""")
    con.executemany("INSERT INTO driver_longevity_estimate VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", out)

    con.execute("""CREATE OR REPLACE TABLE longevity_season_weight (
        driverId INT, season INT, rating_era_s DOUBLE, presence DOUBLE, competitiveness DOUBLE)""")
    con.executemany("INSERT INTO longevity_season_weight VALUES (?,?,?,?,?)", season_rows)

    for t in ["driver_longevity_estimate", "longevity_season_weight"]:
        con.execute(f"COPY {t} TO '{PARQUET / (t + '.parquet')}' (FORMAT PARQUET)")

    print("=" * 78); print("PHASE I — LONGEVITY / sustained competitive presence [constructed estimate]"); print("=" * 78)
    print(f"  {len(out)} drivers (Phase-G coverage, 1994+); "
          f"competitiveness = sigma((C0-r)/KW), C0={C0}, KW={KW}")
    print(f"  longevity = Sigma presence*competitiveness  (effective competitive seasons)")
    top = sorted(rows.items(), key=lambda kv: -kv[1]["L"])[:5]
    print("  top 5: " + ", ".join(f"{name[d].split()[-1]} {m['L']:.1f}" for d, m in top))
    print(f"  wrote driver_longevity_estimate ({len(out)}), longevity_season_weight ({len(season_rows)})")
    return rows


def main():
    con = connect()
    build(con)
    con.close()
    print("\nPHASE I: done.")


if __name__ == "__main__":
    main()
