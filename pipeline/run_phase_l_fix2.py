"""Run Phase L / FIX 2 (longevity sqrt) end-to-end.

Builds A-I (the three axes, racecraft unchanged from main), the J/K composite layer with
the sqrt-longevity transform, then the FIX 2 gate plus the J/K gates (no-regression).
Exits non-zero on any FAIL.
"""
import ingest, teammate_h2h, pace_deltas
import pace_model, pace_model_tv, pace_model_era
import pace_model_racecraft, longevity_model, quality_composite
import gate_phase_l_fix2, gate_phase_j, gate_phase_k

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
    gate_phase_l_fix2.main()   # FIX 2 specific
    gate_phase_j.main()        # no-regression
    gate_phase_k.main()        # no-regression
