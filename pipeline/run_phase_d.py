"""Run the Phase D pace-&-deltas pipeline end-to-end.

Phase D builds on Phase A's relational base and teammate spine, so this re-runs
those first (the DuckDB file is a disposable build artifact), then computes the
pace deltas, then runs the Phase D gate. Exits non-zero on any gate FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import gate_phase_d

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    gate_phase_d.main()   # exits non-zero on any FAIL
