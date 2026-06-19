"""Run the Phase E car-normalisation model end-to-end.

Phase E builds on Phase A (relational base + teammate spine) and Phase D (the
validated Tier-1 qualifying deltas, which are the model's input), so this re-runs
those first, then solves the network model, then runs the Phase E method/sanity
gate. Exits non-zero on any gate FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import pace_model
import gate_phase_e

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    gate_phase_e.main()   # exits non-zero on any FAIL
