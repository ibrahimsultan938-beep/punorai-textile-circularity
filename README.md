# PunorAI — AI-Powered Textile Circularity Platform

**Turning Textile Waste into New Value.**

*Developed for the **Circular Future** Challenge under the **ClimateSphere AI** Ecosystem.*

---

## Overview

**PunorAI** is an AI-powered textile circularity and resource recovery platform that helps Bangladesh's ready-made garment (RMG) industry turn fragmented textile cutting waste into traceable, buyer-compatible circular feedstock.

Bangladesh generates over 500,000 tonnes of post-industrial garment waste annually. Individual cutting rooms produce fragmented 200–500 kg lots, while industrial spinners and mechanical/chemical recyclers require minimum 1,000+ kg uniform batches with strict contamination limits (≤5%).

PunorAI bridges this gap with:
1. **Material Characterization & Intake:** Standardized profiling capturing fiber category, grade, color, and contamination percentage.
2. **Combinatorial Multi-Lot Aggregation:** Deterministic subset-sum constraint optimizer bundling fragmented lots into uniform 1,000+ kg batches.
3. **Recycler Matching:** Multi-objective compatibility scoring evaluating buyer-specific technical thresholds.
4. **Reverse Logistics Planning:** Clustered multi-stop pickup routing across Dhaka-Gazipur-Ashulia with Haversine distance and freight cost modeling (120 BDT/km).
5. **Digital Material Passports:** QR-verifiable batch passports and auditable verification event logs ensuring chain-of-custody integrity.
6. **Evidence-Based Circularity Reporting:** Empirical mass-balance reporting aligned with SDG 12 (Responsible Consumption & Production) with transparent simulation boundaries.

---

## Quick Start (Zero Dependencies • Python 3.10+ Standard Library)

PunorAI requires **no external packages or `pip install`**. It runs entirely on the standard Python runtime:

```bash
# 1. Clone or navigate to the repository
cd PunorAI

# 2. Run the application
python app.py

# 3. Open in browser
# http://127.0.0.1:8000
```

---

## Running the Automated Test Suite

PunorAI includes a complete automated regression and verification test suite:

```bash
# Run all test suites
python run_all_tests.py
```

Included test suites:
- `test_punorai_rebrand.py`: Verifies brand identity, navigation routes, and UI integrity (69/69 checks).
- `test_multiobjective_optimizer.py`: Tests Pareto optimization, shortfall diagnostics, and freight costs (29/29 checks).
- `test_final_demo_fixes.py`: Tests unallocated inventory filtering and status badge logic.
- `test_aggregation_eligibility.py`: Tests multi-buyer eligibility and exclusion reason codes.
- `test_planner_exclusion_audit.py`: Validates strict exclusion of already-allocated lots.
- `test_passport_regression.py`: Validates QR code generation, event logs, and dynamic verification.
- `test_impact_analytics.py`: Audits empirical mass balances and category breakdown metrics.

---

## Project Structure

```
PunorAI/
├── app.py                           # Application server, HTTP routing, page templates & JSON APIs
├── core.py                          # Multi-objective Pareto optimizer, route heuristic & schema
├── circulo.db                       # SQLite database (seed inventory, batches & audit log)
├── run_all_tests.py                 # Master test suite runner
├── requirements.txt                 # Dependency documentation (Python 3.10+ stdlib)
├── .env.example                     # Environment configuration example
├── .gitignore                       # Git ignore configuration
├── static/
│   ├── app.js                       # Frontend UI controller & interactive maps
│   ├── style.css                    # PunorAI enterprise design system & animations
│   ├── leaflet.js                   # Local Leaflet mapping engine
│   └── leaflet.css                  # Leaflet stylesheet
├── uploads/
│   └── lot_1807.jpg                 # Sample lot intake photograph
└── test_*.py                        # Focused automated test suites
```

---

## Methodology Honesty & Integrity Disclosures

- All factories, buyers, and price benchmarks are simulated demonstration records based on real Bangladesh garment cluster operations.
- Aggregation uses an exact, explainable combinatorial constraint solver — never a hardcoded mock.
- No carbon offset credits, greenhouse gas reduction figures, or avoided water volumes are claimed as certified credits in this demo. PunorAI strictly reports empirical mass balance (kilograms characterized, aggregated, and routed). Certified lifecycle assessment (LCA) factors will only be incorporated once certified by accredited independent auditors.
- Fiber composition is declared by suppliers and physically verified at intake — never claimed as "certified by AI".
