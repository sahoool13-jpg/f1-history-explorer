"""Run the Phase J combination layer end-to-end.

Builds Phase A–I (the three axes: G pace, H racecraft, I longevity), then the Phase J
composite/normalisation layer, then the Phase J gate. Exits non-zero on any FAIL.
"""
import ingest
import teammate_h2h
import pace_deltas
import pace_model
import pace_model_tv
import pace_model_era
import pace_model_racecraft
import longevity_model
import quality_composite
import gate_phase_j

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    pace_model_tv.main()
    pace_model_era.main()
    pace_model_racecraft.main()
    longevity_model.main()
    quality_composite.main()
    gate_phase_j.main()   # builds composite axes + gates; exits non-zero on FAIL
