# CIRCULO AI &mdash; Textile Circularity & Resource Recovery

**Solution for the Circular Future Challenge under ClimateSphere AI**  
*ClimateSphere AI: AI for decarbonization, resilience, water, energy, and the circular economy.*  
*Challenges: CarbonIQ &bull; Climate Shield &bull; AquaGuard &bull; Energy Brain &bull; **Circular Future** (Active Track)*

---

## Canonical Product Positioning

> **"An AI-powered textile circularity and resource recovery platform that helps Bangladesh's garment industry turn fragmented textile waste into traceable, buyer-compatible reusable resources."**

---

## The Industrial Problem in Bangladesh

Bangladesh is the world's second-largest ready-made garment (RMG) exporter, generating over **500,000 tonnes of post-industrial textile clips (jhoot)** annually across Gazipur, Ashulia, Narayanganj, and Chittagong.

While high-grade scrap moves through informal trading networks, textile circularity is blocked by three structural failures:
1. **Material Characterization Deficit**: Waste is mixed, unlabelled, and variable in purity.
2. **Extreme Supply Fragmentation**: Individual cutting rooms produce only 200–500 kg daily, whereas industrial mechanical and chemical recyclers require minimum 1,000+ kg uniform lots with &le;5% contamination.
3. **Traceability Void**: Spinners and international fashion brands face zero chain-of-custody verification.

CIRCULO AI solves this not as a generic marketplace, but as a combinatorial decision-support intelligence platform.

---

## Six Core Solution Pillars

1. **Textile Waste Inventory & Material Characterization**: Standardized profiling capturing fiber category, grade, color, contamination %, and mill origin. AI vision suggestion slot with mandatory physical verification.
2. **Explainable Combinatorial Aggregation**: Transparent subset-sum constraint solver that bundles fragmented 200–500 kg lots into uniform 1,000+ kg batches satisfying rigid recycler thresholds.
3. **Recycler Matching & Technical Criteria**: Algorithmic compatibility scoring evaluating buyer-specific technical thresholds (contamination tolerance, minimum tonnage, and price discovery benchmarks).
4. **Resource Recovery Reverse Logistics**: Clustered multi-stop pickup routing across Dhaka-Gazipur-Ashulia garment mills using Haversine network analysis and transparent freight cost modeling.
5. **Digital Material Passports & Traceability**: Unique batch codes, QR-verifiable passports, and immutable event logs ensuring verifiable circularity for textile mills and spinners.
6. **Evidence-Based Circularity Reporting**: Strictly empirical mass-balance reporting aligned with SDG 12 (Responsible Consumption & Production) with zero greenwashing disclosures.

---

## Run Locally (Zero Dependencies &bull; Python 3.9+ Standard Library)

```bash
cd circulo-ai
python app.py
# Open http://localhost:8000
```

- No `pip install` required. No API keys required.
- SQLite database (`circulo.db`) and demo data are initialized automatically.
- Multi-threaded HTTP server with thread-local SQLite proxy connections.

---

## 5-Minute ClimateSphere AI Judge Demo Workflow

1. **Platform Overview (`/`)**: Review the 500k-tonne textile waste challenge and CIRCULO AI's Circular Future alignment.
2. **Executive Dashboard (`/dashboard`)**: Monitor total characterized waste, unallocated recoverable resources, circular pipeline stages, and one-click demo reset.
3. **Waste Characterization (`/lots`)**: Inspect seeded factory lots across Gazipur and Ashulia; register a new lot with photo preview and contamination metrics.
4. **Combinatorial Aggregation (`/aggregation`)**: Select Recycler X (needs 1,000 kg cotton); run the subset-sum engine with 100% transparent inclusion and exclusion reason codes.
5. **Digital Material Passport (`/passports`)**: Form candidate batch and instantly issue a Digital Material Passport with QR code and event audit trail.
6. **Cluster Logistics (`/planning`)**: Inspect multi-stop pickup route with declared Haversine distance and transparent freight cost estimates.
7. **Empirical Circularity Reports (`/reports`)**: Review strictly measured mass-balance platform activity and environmental boundary disclosures (SDG 12 aligned; zero fabricated carbon credits).

---

## System Architecture

```
Browser Client (HTML5 / Modern CSS / Vanilla JS)
       │
       ▼
 app.py  (Standard library ThreadingHTTPServer, thread-local DB proxy, routing, UI templates, JSON APIs)
       │
       ▼
 core.py (SQLite schema, combinatorial subset-sum aggregation solver, buyer matcher,
          Haversine route heuristic, SVG charts, Digital Material Passport event trail)
       │
       ▼
 circulo.db (SQLite WAL mode) + uploads/
```

### AI Module Integration Seams
- **Vision Material Suggestion**: Plugs into `POST /api/lots` photo intake.
- **Aggregation Optimizer**: Plugs into `core.plan_aggregation` (subset-sum solver; ready for integer linear programming / ILP).
- **Recycler Matching**: Plugs into `core.match_buyers` (multi-constraint compatibility scoring).
- **Logistics Route Optimization**: Plugs into `core.plan_route` (nearest-neighbour heuristic; ready for live routing APIs).

---

## Methodology Honesty & Integrity Disclosures

- All factories, buyers, and price benchmarks are simulated demonstration records based on real Bangladesh garment cluster operations.
- Aggregation uses an exact, explainable combinatorial constraint solver &mdash; never a hardcoded mock.
- No carbon offset credits, greenhouse gas reduction figures, or avoided water volumes are claimed as certified credits in this demo. CIRCULO AI strictly reports empirical mass balance (kilograms characterized, aggregated, and routed). Certified lifecycle assessment (LCA) factors will only be incorporated once certified by accredited independent auditors.
- Fiber composition is declared by suppliers and physically verified at intake &mdash; never claimed as "certified by AI".
