"""Run the Phase H racecraft model end-to-end.

Builds Phase A (results + teammate spine), Phase D (quali + race-pace deltas = the
pace baselines we regress out), Phase E/F/G (pace ratings — Phase G era pace is the
orthogonality reference in the gate), then the Phase H racecraft model, then the
Phase H gate. Exits non-zero on any gate FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import pace_model
import pace_model_tv
import pace_model_era
import pace_model_racecraft
import gate_phase_h

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    pace_model_tv.main()
    pace_model_era.main()
    gate_phase_h.main()   # builds the Phase H model, then gates; exits non-zero on FAIL
