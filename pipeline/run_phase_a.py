"""Run the full Phase A pipeline end-to-end: ingest -> teammate H2H -> gate.

Exits non-zero if the gate fails (strict phase-gate discipline).
"""
import ingest
import teammate_h2h
import gate

if __name__ == "__main__":
    ingest.main()
    teammate_h2h.main()
    gate.main()  # exits non-zero on any FAIL
