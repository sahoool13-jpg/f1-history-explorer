"""Run Phase L / FIX 1 (racecraft grid-opportunity) end-to-end.

Builds A-I with the CONVERSION racecraft metric (finish_gap - grid_gap), the composite
layer, then the FIX 1 gate (prints the z^2/v branch decision + full BEFORE/AFTER board),
then J/K gates (Option-C-aware no-regression), then regenerates the web data. Exits
non-zero on any FAIL.
"""
import ingest, teammate_h2h, pace_deltas
import pace_model, pace_model_tv, pace_model_era
import pace_model_racecraft, longevity_model, quality_composite
import gate_phase_l_fix1, gate_phase_j, gate_phase_k
import export_web

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    pace_deltas.main()
    pace_model.main()
    pace_model_tv.main()
    pace_model_era.main()
    pace_model_racecraft.main()      # conversion metric (default)
    longevity_model.main()
    quality_composite.main()         # composite tables on conversion racecraft
    gate_phase_l_fix1.main()         # branch decision + BEFORE/AFTER board (ends conversion)
    gate_phase_j.main()              # Option-C-aware no-regression
    gate_phase_k.main()              # no-regression
    export_web.main()                # regenerate web/data.js
