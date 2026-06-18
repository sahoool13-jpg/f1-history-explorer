"""Run the full Phase B pipeline end-to-end.

Phase B builds on Phase A's artifacts, so this re-runs Phase A first (the DuckDB
file is a disposable build artifact), then the three championship features, then
the Phase B gate. Exits non-zero on any gate FAIL (strict phase-gate discipline).
"""
import ingest
import teammate_h2h
import feature1_points_invariance
import feature2_clinch
import feature3_teammate_champions
import gate_phase_b

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    feature1_points_invariance.main()
    feature2_clinch.main()
    feature3_teammate_champions.main()
    gate_phase_b.main()  # exits non-zero on any FAIL
