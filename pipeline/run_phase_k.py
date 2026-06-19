"""Run the Phase K composite refinement end-to-end.

Builds Phase A–I (the three axes), the J/K composite layer (interval-aware shrinkage +
within-era mode), then BOTH the Phase J gate (combination still holds on the shrunk
baseline) and the Phase K gate (shrinkage era-neutrality, within-era, radar data), then
regenerates the web data. Exits non-zero on any FAIL.
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
import gate_phase_k

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
    gate_phase_j.main()   # combination holds on the shrunk baseline
    gate_phase_k.main()   # shrinkage era-neutrality + within-era + radar data
