"""Run the Phase G era-normalisation model end-to-end.

Builds Phase A (base + teammate spine) and Phase D (Tier-1 quali deltas), Phase E
(career-average — needed for the Giovinazzi E→F→G chain in the gate), Phase F
(time-resolved — the input), then the Phase G era-normalised model, then the
Phase G gate. Exits non-zero on any gate FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import pace_model
import pace_model_tv
import gate_phase_g

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    pace_model_tv.main()
    gate_phase_g.main()   # builds the Phase G model, then gates; exits non-zero on FAIL
