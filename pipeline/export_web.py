"""Phase C — export the validated Phase A/B artifacts to a self-contained JS data
file for the "Lift and Coast" static front-end.

Writes web/data.js assigning `window.LAC_DATA`. Inlined (not fetched) so the site
works straight from file:// and from any static host (e.g. GitHub Pages) with no
server. Regenerate with: python3 pipeline/export_web.py
"""
import json
from common import connect, ROOT
from points_systems import POINTS_TABLES, SEASON_TABLE
import pace_model  # Phase E model solve (for effective-resistance pairwise CIs)
import numpy as np

WEB = ROOT / "web"


def label_for_table(key):
    pts = POINTS_TABLES[key]["points"]
    fl = " +FL" if POINTS_TABLES[key]["fl_rule"] != "none" else ""
    return "-".join(str(p) for p in pts) + fl


def build(con):
    q = lambda s: con.execute(s).fetchall()

    # champion's main constructor + season points + wins, per season
    champ_meta = {r[0]: r for r in q("""
        WITH finals AS (SELECT season, max(round) mr FROM fact_races GROUP BY season),
        champ AS (
            SELECT r.season, ds.driverId, ds.points, ds.wins
            FROM driver_standings ds JOIN fact_races r USING (raceId)
            JOIN finals f ON f.season=r.season AND f.mr=r.round
            WHERE CAST(ds.position AS INT)=1
        ),
        champ_con AS (  -- each driver's top-scoring constructor that season (rn=1)
            SELECT season, driverId, constructor_name,
                   row_number() OVER (PARTITION BY season, driverId ORDER BY pts DESC) rn
            FROM (
                SELECT ra.season, r.driverId, c.constructor_name,
                       sum(CAST(r.points AS DOUBLE)) pts
                FROM results r JOIN fact_races ra USING (raceId)
                JOIN dim_constructors c USING (constructorId)
                GROUP BY ra.season, r.driverId, c.constructor_name
            )
        )
        SELECT c.season, d.full_name, d.code, cc.constructor_name,
               CAST(c.points AS DOUBLE), CAST(c.wins AS INT), c.driverId
        FROM champ c JOIN dim_drivers d USING (driverId)
        JOIN champ_con cc ON cc.season=c.season AND cc.driverId=c.driverId AND cc.rn=1
    """)}

    clinch = {r[0]: r for r in q("SELECT * FROM f1_clinch")}
    tm = {r[0]: r for r in q("SELECT * FROM f1_champion_teammate")}

    # season runner-up (final-standings P2) — a validated-artifact read, not a recompute
    runner = {r[0]: (r[1], round(r[2], 1)) for r in q("""
        WITH finals AS (SELECT season, max(round) mr FROM fact_races GROUP BY season)
        SELECT r.season, d.full_name, CAST(ds.points AS DOUBLE)
        FROM driver_standings ds JOIN fact_races r USING (raceId)
        JOIN finals f ON f.season=r.season AND f.mr=r.round
        JOIN dim_drivers d USING (driverId)
        WHERE CAST(ds.position AS INT)=2
    """)}

    inv = {}
    for season, _, tk, ch, changes, is_tie, tp in q("SELECT * FROM f1_points_invariance"):
        inv.setdefault(season, []).append(
            {"table": label_for_table(tk), "key": tk, "champ": ch,
             "changes": bool(changes), "tie": bool(is_tie),
             "own": tk == SEASON_TABLE[season], "pts": round(tp, 1)})

    # ---- Phase D pace deltas (presentation only — read the validated artifacts) ----
    dname = {r[0]: (r[1], r[2], r[3]) for r in
             q("SELECT driverId, full_name, code, surname FROM dim_drivers")}
    cname = {r[0]: r[1] for r in q("SELECT constructorId, constructor_name FROM dim_constructors")}

    quali_ps = {}   # (season,cid,dA,dB) -> quali delta (A-B; negative => A faster). Tier 1.
    for r in q("""SELECT season, constructorId, driverA, driverB, median_gap_s, mean_gap_s,
                         n_included, n_valid, a_faster_races, n_incident
                  FROM quali_teammate_delta_pairseason"""):
        quali_ps[(r[0], r[1], r[2], r[3])] = {
            "median": r[4], "mean": r[5], "n": r[6], "races": r[7],
            "aFaster": r[8], "incidents": r[9]}

    race_ps = {}    # (season,cid,dA,dB) -> race-pace delta (A-B s/lap). Tier 2.
    for r in q("""SELECT season, constructorId, driverA, driverB, median_delta_s, mean_delta_s,
                         n_ok_races, n_low_races FROM racepace_teammate_pairseason"""):
        race_ps[(r[0], r[1], r[2], r[3])] = {
            "median": r[4], "mean": r[5], "nOk": r[6], "nLow": r[7]}

    def pair_block(key):
        """Native A<B orientation: quali/race deltas with sign A-B (neg => A faster)."""
        qd, rd = quali_ps.get(key), race_ps.get(key)
        season, cid, dA, dB = key
        out = {
            "year": season, "constructor": cname.get(cid),
            "aId": dA, "aName": dname[dA][0], "aCode": dname[dA][1], "aSur": dname[dA][2],
            "bId": dB, "bName": dname[dB][0], "bCode": dname[dB][1], "bSur": dname[dB][2],
            "quali": None, "race": None,
        }
        if qd and qd["median"] is not None:
            out["quali"] = {"median": round(qd["median"], 3), "mean": round(qd["mean"], 3),
                            "n": qd["n"], "races": qd["races"], "aFaster": qd["aFaster"],
                            "incidents": qd["incidents"], "tier": 1}
        if rd and rd["nOk"] is not None:
            out["race"] = {"median": (round(rd["median"], 3) if rd["median"] is not None else None),
                           "nOk": rd["nOk"], "nLow": rd["nLow"], "tier": 2}
        return out

    pairings = [pair_block(k) for k in (set(quali_ps) | set(race_ps))]
    pairings.sort(key=lambda p: (p["year"], p["constructor"] or "", p["aSur"]))

    def champ_delta(season, champ_id):
        """Champion-oriented primary-teammate delta (negative => champion faster)."""
        cands = [k for k in (set(quali_ps) | set(race_ps)) if k[0] == season and champ_id in (k[2], k[3])]
        if not cands:
            return None
        def races(k):
            qd = quali_ps.get(k); rd = race_ps.get(k)
            return ((qd["races"] if qd else 0), (rd["nOk"] if rd else 0))
        key = max(cands, key=races)
        season_, cid, dA, dB = key
        tm_id = dB if champ_id == dA else dA
        sign = 1 if champ_id == dA else -1     # flip A-B to champion perspective
        qd, rd = quali_ps.get(key), race_ps.get(key)
        block = {"vs": dname[tm_id][0], "vsCode": dname[tm_id][1], "vsSur": dname[tm_id][2],
                 "multiple": len(cands) > 1, "quali": None, "race": None}
        if qd and qd["median"] is not None:
            champ_faster = qd["aFaster"] if champ_id == dA else (qd["races"] - qd["aFaster"])
            block["quali"] = {"median": round(sign * qd["median"], 3), "mean": round(sign * qd["mean"], 3),
                              "n": qd["n"], "races": qd["races"], "champFaster": champ_faster, "tier": 1}
        if rd and rd["nOk"] is not None:
            block["race"] = {"median": (round(sign * rd["median"], 3) if rd["median"] is not None else None),
                             "nOk": rd["nOk"], "nLow": rd["nLow"], "tier": 2}
        return block

    seasons = []
    for yr in sorted(champ_meta):
        cm = champ_meta[yr]
        cl = clinch[yr]
        t = tm[yr]
        flips = sorted({i["champ"] for i in inv[yr] if i["changes"]})
        has_tie = any(i["tie"] for i in inv[yr])
        seasons.append({
            "year": yr,
            "champion": cm[1], "code": cm[2], "constructor": cm[3],
            "points": round(cm[4], 1), "wins": cm[5],
            "runnerUp": (runner.get(yr) or [None, None])[0],
            "runnerUpPoints": (runner.get(yr) or [None, None])[1],
            "clinch": {
                "round": cl[2], "race": cl[3], "totalRounds": cl[4],
                "racesRemaining": cl[5], "wentToFinale": bool(cl[6]),
                "closestMargin": round(cl[7], 1),
            },
            "teammate": {
                "names": t[2], "n": t[3],
                "qualiAvailable": yr >= 1994 and t[4] > 0,
                "qRaces": t[4], "qWins": t[5], "qLosses": t[6],
                "rRaces": t[7], "rWins": t[8], "rLosses": t[9],
                "champPoints": round(t[10], 1), "tmPoints": round(t[11], 1),
                "outQualified": bool(t[12]), "outRaced": bool(t[13]),
                "delta": champ_delta(yr, cm[6]),
            },
            "invariance": inv[yr],
            "flips": flips,
            "anyChange": len(flips) > 0,
            "hasTie": has_tie,
        })

    # ---- Phase E car-normalisation MODEL (estimate; read validated artifacts) ----
    # per-driver data span from the Tier-1 quali pair-seasons (the model's input)
    span = {}
    for did, mn, mx, ns in q("""
        SELECT d, min(season), max(season), count(DISTINCT season) FROM (
            SELECT driverA AS d, season FROM quali_teammate_delta_pairseason WHERE median_gap_s IS NOT NULL
            UNION ALL
            SELECT driverB AS d, season FROM quali_teammate_delta_pairseason WHERE median_gap_s IS NOT NULL
        ) GROUP BY d"""):
        span[did] = (mn, mx, ns)

    model_rows = q("""SELECT driverId, driver_name, code, rating_s_estimate, sigma_s,
        ci95_halfwidth_s, ci95_low, ci95_high, n_teammates, n_observations,
        component, confidence_flag, rankable FROM driver_pace_model_estimate""")
    model_drivers = []
    for (did, nm, cd, rating, sigma, ci, lo, hi, nt, nob, comp, flag, rankable) in model_rows:
        sp = span.get(did, (None, None, 0))
        model_drivers.append({
            "id": did, "name": nm, "code": cd,
            "rating": rating, "sigma": sigma, "ci95": ci, "ciLow": lo, "ciHigh": hi,
            "nTeammates": nt, "nObs": nob, "component": comp, "flag": flag,
            "rankable": bool(rankable), "dataFrom": sp[0], "dataTo": sp[1], "nSeasons": sp[2],
        })

    # effective-resistance pairwise 95% CIs among rankable drivers (for the compare tool)
    M = pace_model.compute(con)
    Lp, idx, sigma2 = M["Lp"], M["idx"], M["sigma2"]
    rankable_ids = [d["id"] for d in model_drivers if d["rankable"] and d["id"] in idx]
    pairwise = {}
    for ii in range(len(rankable_ids)):
        for jj in range(ii + 1, len(rankable_ids)):
            a, b = rankable_ids[ii], rankable_ids[jj]
            reff = pace_model.effective_resistance(Lp, idx, a, b)
            ci = 1.959964 * float(np.sqrt(sigma2 * reff))
            key = f"{min(a,b)}_{max(a,b)}"
            pairwise[key] = round(ci, 3)

    resid = [r[0] for r in q("SELECT residual_s FROM pace_model_residual")]

    # ---- Phase F TIME-VARYING model: per-driver career-arc trajectories -------
    # teammate(s) per (driver, season) — context for the hover, read from the
    # measured Tier-1 input (displayed as evidence, not recomputed).
    tm_ctx = {}
    for season, a, b, n in q("""SELECT season, driverA, driverB, n_included
                                FROM quali_teammate_delta_pairseason WHERE median_gap_s IS NOT NULL"""):
        tm_ctx.setdefault((a, season), []).append((dname[b][1], dname[b][0], n))
        tm_ctx.setdefault((b, season), []).append((dname[a][1], dname[a][0], n))

    tv_rows = q("""SELECT driverId, driver_name, code, season, rating_s_estimate,
                          ci95_halfwidth_s, ci95_low, ci95_high, n_teammate_edges, confidence_flag
                   FROM driver_season_pace_estimate ORDER BY driverId, season""")
    trajectories = {}
    for (did, nm, cd, season, rating, ci, lo, hi, ne, flag) in tv_rows:
        tj = trajectories.setdefault(did, {"id": did, "name": nm, "code": cd, "seasons": []})
        tms = sorted(tm_ctx.get((did, season), []), key=lambda x: -x[2])
        tj["seasons"].append({
            "season": season, "rating": rating, "ci95": ci, "ciLow": lo, "ciHigh": hi,
            "nEdges": ne, "flag": flag,
            "tm": [{"code": c, "name": n, "n": k} for (c, n, k) in tms],
        })
    for tj in trajectories.values():
        ss = [s["season"] for s in tj["seasons"]]
        tj["from"], tj["to"], tj["nSeasons"] = min(ss), max(ss), len(ss)
    # picker list, long arcs first
    arc_drivers = sorted(({"id": t["id"], "name": t["name"], "code": t["code"],
                           "from": t["from"], "to": t["to"], "nSeasons": t["nSeasons"]}
                          for t in trajectories.values() if t["nSeasons"] >= 2),
                         key=lambda d: (-d["nSeasons"], d["name"]))
    tv_resid = [r[0] for r in q("SELECT residual_s FROM pace_model_tv_residual")]

    model = {
        "drivers": model_drivers,
        "pairwise": pairwise,
        "trajectories": trajectories,
        "arcDrivers": arc_drivers,
        "meta": {
            "nDrivers": len([d for d in model_drivers if d["component"] == "giant"]),
            "nEdges": M["n_edges"] if "n_edges" in M else len(M["edges"]),
            "nRankable": len(rankable_ids),
            "sigma2": round(float(sigma2), 2),
            "eraFrom": 1994, "eraTo": 2024,
            "medianResidual": round(float(np.median(np.abs(resid))), 3),
            "tvNodes": len(tv_rows),
            "tvMedianResidual": round(float(np.median(np.abs(tv_resid))), 3),
            "tvLambda": 100, "tvDriftSigma": 0.10,
        },
    }

    # ---- Phase J: composite driver-quality axes (user-weighted, no fixed ranking) ----
    qa = q("""SELECT driverId, driver_name, code, n_seasons, is_active,
                     z_pace, z_racecraft, z_longevity, zci_pace, zci_racecraft, zci_longevity,
                     pace_s, racecraft_pos, longevity, missing_axes
              FROM driver_quality_axes WHERE is_composite_eligible=1
              ORDER BY z_pace+z_racecraft+z_longevity DESC""")
    quality_drivers = [{
        "name": r[1], "code": r[2], "nSeasons": r[3], "active": bool(r[4]),
        "z": [round(r[5], 3), round(r[6], 3), round(r[7], 3)],
        "sz": [round(r[8], 3), round(r[9], 3), round(r[10], 3)],
        "raw": [round(r[11], 3), round(r[12], 2), round(r[13], 1)],
    } for r in qa]
    qpart = q("""SELECT driver_name, code, n_seasons, missing_axes,
                        has_pace, has_racecraft, has_longevity
                 FROM driver_quality_axes
                 WHERE is_composite_eligible=0 AND n_seasons>=2 AND missing_axes != ''
                 ORDER BY n_seasons DESC, driver_name LIMIT 40""")
    quality_partial = [{
        "name": r[0], "code": r[1], "nSeasons": r[2], "missing": r[3],
        "has": [bool(r[4]), bool(r[5]), bool(r[6])],
    } for r in qpart]
    nmeta = {r[0]: {"mean": r[1], "std": r[2]} for r in
             q("SELECT axis, ref_mean, ref_std FROM quality_norm_meta")}
    quality = {
        "axes": [
            {"key": "pace", "label": "Pace", "unit": "s vs era backbone (G)",
             "note": "qualifying pace, car- & era-normalised; lower = faster"},
            {"key": "racecraft", "label": "Racecraft", "unit": "positions vs pace (H)",
             "note": "Sunday conversion beyond what pace predicts; orthogonal to pace"},
            {"key": "longevity", "label": "Longevity", "unit": "effective seasons (I)",
             "note": "sustained competitive presence; the softest, most constructed axis"},
        ],
        "drivers": quality_drivers,
        "partial": quality_partial,
        "norm": nmeta,
        "refN": q("SELECT ref_n FROM quality_norm_meta LIMIT 1")[0][0],
        "z95": 1.959964,
    }

    meta = {
        "tables": [{"key": k, "label": label_for_table(k),
                    "seasons": f"{v['seasons'][0]}–{v['seasons'][-1]}",
                    "source": v["source"]}
                   for k, v in POINTS_TABLES.items()],
        "totals": {
            "seasons": len(seasons),
            "races": q("SELECT count(*) FROM fact_races")[0][0],
            "drivers": q("SELECT count(*) FROM dim_drivers")[0][0],
            "constructors": q("SELECT count(*) FROM dim_constructors")[0][0],
            "finaleTitles": sum(1 for s in seasons if s["clinch"]["wentToFinale"]),
            "scoringSensitive": sum(1 for s in seasons if s["anyChange"]),
            "tieSeasons": sum(1 for s in seasons if s["hasTie"]),
            "qualiDeltaPairings": sum(1 for p in pairings if p["quali"]),
            "racePacePairings": sum(1 for p in pairings if p["race"]),
        },
    }

    WEB.mkdir(exist_ok=True)
    payload = {"meta": meta, "seasons": seasons, "pairings": pairings, "model": model,
               "quality": quality}
    out = WEB / "data.js"
    with open(out, "w") as f:
        f.write("/* GENERATED by pipeline/export_web.py — do not edit by hand. */\n")
        f.write("window.LAC_DATA = ")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print(f"wrote {out.relative_to(ROOT)}  ({out.stat().st_size:,} bytes, "
          f"{len(seasons)} seasons)")


def main():
    con = connect()
    build(con)
    con.close()


if __name__ == "__main__":
    main()
