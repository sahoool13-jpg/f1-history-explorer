"""Run the Phase I longevity model end-to-end.

Builds Phase A (results + span), Phase D (pace deltas), Phase E/F/G (per-season era
pace = the competitiveness signal), Phase H (racecraft — orthogonality reference),
then the Phase I longevity model, then the Phase I gate. Exits non-zero on any FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import pace_model
import pace_model_tv
import pace_model_era
import pace_model_racecraft
import longevity_model
import gate_phase_i

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    pace_model_tv.main()
    pace_model_era.main()
    pace_model_racecraft.main()
    longevity_model.main()
    gate_phase_i.main()   # builds longevity + gates; exits non-zero on FAIL
