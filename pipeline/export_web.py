"""Phase C — export the validated Phase A/B artifacts to a self-contained JS data
file for the "Lift and Coast" static front-end.

Writes web/data.js assigning `window.LAC_DATA`. Inlined (not fetched) so the site
works straight from file:// and from any static host (e.g. GitHub Pages) with no
server. Regenerate with: python3 pipeline/export_web.py
"""
import json
from common import connect, ROOT
from points_systems import POINTS_TABLES, SEASON_TABLE

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
               CAST(c.points AS DOUBLE), CAST(c.wins AS INT)
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
            },
            "invariance": inv[yr],
            "flips": flips,
            "anyChange": len(flips) > 0,
            "hasTie": has_tie,
        })

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
        },
    }

    WEB.mkdir(exist_ok=True)
    payload = {"meta": meta, "seasons": seasons}
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
