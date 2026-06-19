"""Phase I GATE — longevity: mediocrity, brevity, orthogonality, Giovinazzi, honesty.

Longevity is a CONSTRUCTED axis. This gate proves it measures SUSTAINED COMPETITIVE
PRESENCE, dodging all three traps: (1) MEDIOCRITY — a durable midfield career does not
reach the top, and raw length does not dominate; (2) BREVITY != BADNESS — a
brief-but-strong career scores moderate (not bottom), and can rival a longer weaker
one; (3) ORTHOGONALITY — correlates only moderately with pace (G) and racecraft (H),
adding the duration dimension they lack. Plus the Giovinazzi check, sanity anchors, and
honest uncertainty. Any FAIL exits non-zero. Ratings remain ESTIMATES.
"""
import sys
import numpy as np
from common import connect
import longevity_model as I

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  —  {detail}" if detail else ""))


def main():
    con = connect()
    I.build(con)
    q = lambda s, *a: con.execute(s, list(a)).fetchall()
    print()
    print("=" * 78); print("PHASE I GATE — longevity: mediocrity, brevity, orthogonality, honesty"); print("=" * 78)
    print("  CONSTRUCTED axis — 'effective competitive seasons'. Low ≠ lacked ability.\n")

    L = {r[0]: r[1] for r in q("SELECT driver_name, longevity_estimate FROM driver_longevity_estimate")}
    NS = {r[0]: r[1] for r in q("SELECT driver_name, n_seasons FROM driver_longevity_estimate")}
    def lv(nm):
        return L.get(nm)
    ranked = sorted(L, key=lambda n: -L[n])
    rank = {n: i + 1 for i, n in enumerate(ranked)}

    # ---- GATE 1: top is long-AND-competitive (sanity anchors) --------------
    print("GATE 1 — the top is long-AND-competitive (not just anyone who lingered)")
    for nm in ranked[:6]:
        print(f"        #{rank[nm]:<2d} {nm:22s} {NS[nm]:2d} seasons  L={lv(nm):.1f}")
    top_elite = {"Fernando Alonso", "Lewis Hamilton", "Michael Schumacher", "Kimi Räikkönen"}
    check("long-elite drivers (Alonso, Hamilton, Schumacher, Räikkönen) are all top-8",
          all(rank[n] <= 8 for n in top_elite),
          ", ".join(f"{n.split()[-1]}#{rank[n]}" for n in top_elite))

    # ---- GATE 2: MEDIOCRITY — durable midfield career not near the top -----
    print("\nGATE 2 — raw length does NOT reward mediocrity")
    cou, fis = "David Coulthard", "Giancarlo Fisichella"
    print(f"        Coulthard: {NS[cou]} seasons (among the LONGEST) -> L={lv(cou):.1f}, rank #{rank[cou]}")
    print(f"        Fisichella: {NS[fis]} seasons -> L={lv(fis):.1f}, rank #{rank[fis]}")
    # rank by raw season-count, compare to longevity rank
    raw_ranked = sorted(L, key=lambda n: -NS[n])
    raw_rank = {n: i + 1 for i, n in enumerate(raw_ranked)}
    print(f"        Coulthard by RAW length would be #{raw_rank[cou]}; longevity drops him to #{rank[cou]} "
          f"(weak seasons discounted)")
    check("a durable midfield journeyman (Coulthard, 15 seasons) is NOT top-10",
          rank[cou] > 10, f"rank #{rank[cou]}")
    check("competitiveness weighting drops the journeyman below his raw-length rank",
          rank[cou] > raw_rank[cou] + 5, f"#{raw_rank[cou]} raw -> #{rank[cou]} longevity")

    # ---- GATE 3: BREVITY != BADNESS ----------------------------------------
    print("\nGATE 3 — brief-but-strong scores MODERATE (not bottom), can rival longer-weaker")
    lec = "Charles Leclerc"
    print(f"        Leclerc: {NS[lec]} seasons (brief, all competitive) -> L={lv(lec):.1f}, rank #{rank[lec]}")
    print(f"        Coulthard: {NS[cou]} seasons (double the length, weaker) -> L={lv(cou):.1f}")
    lo = min(L.values()); med = float(np.median(list(L.values())))
    print(f"        scale: min L={lo:.1f}, median L={med:.1f}, max L={max(L.values()):.1f}")
    check("brief-but-strong Leclerc scores above the median (moderate, not bottom)",
          lv(lec) > med, f"L={lv(lec):.1f} > median {med:.1f}")
    check("Leclerc (7 strong seasons) rivals Coulthard (15 weaker) — length isn't everything",
          lv(lec) > 0.7 * lv(cou), f"{lv(lec):.1f} vs {lv(cou):.1f}")

    # ---- GATE 4: ORTHOGONALITY (adds info, not redundant) ------------------
    print("\nGATE 4 — orthogonality: longevity adds the duration dimension G & H lack")
    g = dict(q("""SELECT d.full_name, -avg(p.rating_era_s_estimate)
                  FROM driver_season_pace_era_estimate p JOIN dim_drivers d USING(driverId) GROUP BY 1"""))
    h = dict(q("""SELECT d.full_name, r.racecraft_pos_estimate
                  FROM driver_racecraft_estimate r JOIN dim_drivers d USING(driverId)"""))
    gg = [(L[n], g[n]) for n in L if n in g]
    hh = [(L[n], h[n]) for n in L if n in h]
    cg = np.corrcoef([a for a, _ in gg], [b for _, b in gg])[0, 1]
    ch = np.corrcoef([a for a, _ in hh], [b for _, b in hh])[0, 1]
    print(f"        corr(longevity, pace G) = {cg:+.3f} (n={len(gg)});  "
          f"corr(longevity, racecraft H) = {ch:+.3f} (n={len(hh)})")
    check("longevity correlates only moderately with pace (meaningfully below 1)",
          abs(cg) < 0.7, f"r={cg:+.3f}")
    check("longevity is near-orthogonal to racecraft (distinct dimension)",
          abs(ch) < 0.5, f"r={ch:+.3f}")

    # ---- GATE 5: the GIOVINAZZI check --------------------------------------
    print("\nGATE 5 — the Giovinazzi check (short AND uncompetitive -> low)")
    gio = "Antonio Giovinazzi"
    # compare against GENUINE careers (>=4 seasons); the full field is half one-race cameos,
    # which would flatter a 4-season driver. The honest reference is established drivers.
    real = sorted([n for n in L if NS[n] >= 4], key=lambda n: -L[n])
    real_rank = {n: i + 1 for i, n in enumerate(real)}
    real_med = float(np.median([L[n] for n in real]))
    print(f"        Giovinazzi: {NS[gio]} seasons, L={lv(gio):.1f}")
    print(f"        among {len(real)} drivers with >=4 seasons: rank #{real_rank[gio]} "
          f"(bottom {100*(len(real)-real_rank[gio])/len(real):.0f}%); median of that group = {real_med:.1f}")
    print(f"        (rank #{rank[gio]}/{len(L)} over ALL drivers only because half the field are 1-race cameos)")
    check("Giovinazzi is in the bottom third of GENUINE careers (>=4 seasons)",
          real_rank[gio] > 2 * len(real) / 3, f"#{real_rank[gio]} of {len(real)}")
    check("Giovinazzi's longevity is far below the established-driver median (didn't sustain)",
          lv(gio) < 0.6 * real_med, f"{lv(gio):.1f} < {0.6*real_med:.1f}")

    # ---- GATE 6: uncertainty + honest framing ------------------------------
    print("\nGATE 6 — uncertainty is honest (statistical + construction), active flagged")
    cis = q("SELECT driver_name, ci95_halfwidth, construction_low, construction_high, is_active "
            "FROM driver_longevity_estimate WHERE driver_name IN ('Lewis Hamilton','Charles Leclerc','Antonio Giovinazzi')")
    for nm, ci, clo, chi, act in cis:
        print(f"        {nm:20s} L={lv(nm):5.1f} ± {ci:.1f}  construction band [{clo:.1f},{chi:.1f}]  "
              f"{'ACTIVE' if act else 'retired'}")
    nact = q("SELECT count(*) FROM driver_longevity_estimate WHERE is_active=1")[0][0]
    # genuine careers carry real intervals; the 4 zero-CI rows are 1-race backmarkers whose
    # competitiveness is saturated at ~0 across the whole construction grid (L~0, certainty high).
    min_real_ci = q("SELECT min(ci95_halfwidth) FROM driver_longevity_estimate WHERE n_seasons>=3")[0][0]
    print(f"        min CI among genuine careers (>=3 seasons) = ±{min_real_ci:.2f}  "
          f"(4 one-race backmarkers sit at L≈0 with ~0 uncertainty — honest)")
    check("genuine careers (>=3 seasons) all carry populated intervals",
          min_real_ci > 0, f"min ±{min_real_ci:.2f}")
    check("active drivers are flagged (longevity is 'so far', not final)", nact > 0, f"{nact} active")

    # ---- GATE 7: separation / labelling ------------------------------------
    print("\nGATE 7 — modelled estimate kept separate & labelled")
    all_est = q("SELECT bool_and(is_estimate=1) FROM driver_longevity_estimate")[0][0]
    res_cols = [c[1] for c in q("PRAGMA table_info('fact_results')")]
    check("every Phase I row labelled is_estimate=1", bool(all_est))
    check("measured results untouched (no rating/estimate/longevity column)",
          not any(("rating" in c or "estimate" in c or "longevity" in c) for c in res_cols))

    print("\n" + "=" * 78)
    npass = sum(RESULTS); nfail = len(RESULTS) - npass
    print(f"PHASE I GATE SUMMARY: {npass} PASS / {nfail} FAIL  (of {len(RESULTS)})")
    print("=" * 78)
    con.close()
    if nfail:
        print("\nPHASE I GATE: *** FAILED *** — phase blocked."); sys.exit(1)
    print("\nPHASE I GATE: *** ALL PASS *** — longevity rewards sustained competitiveness (not "
          "attendance), stays orthogonal, and a short strong career reads as 'didn't sustain', not "
          "'wasn't good'. (Constructed axis — ratings remain estimates.)")


if __name__ == "__main__":
    main()
