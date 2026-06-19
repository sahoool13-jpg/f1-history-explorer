"""Run the Phase F time-varying car-normalisation model end-to-end.

Builds Phase A (base + teammate spine) and Phase D (Tier-1 quali deltas = the
input), Phase E (career-average model — needed for the Giovinazzi before/after in
the gate), then the time-resolved Phase F model, then the Phase F gate. Exits
non-zero on any gate FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import pace_model
import pace_model_tv
import gate_phase_f

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    pace_model_tv.main()
    gate_phase_f.main()   # exits non-zero on any FAIL
