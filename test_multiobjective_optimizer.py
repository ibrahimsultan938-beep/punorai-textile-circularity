import unittest
import sqlite3
import json
import urllib.request
import sys
import os

from core import (
    get_db,
    plan_aggregation,
    find_candidate_batches,
    exclusion_reason,
    plan_route,
    batch_verification_status
)
from app import render_plan

BASE_URL = os.environ.get("CIRCULO_BASE_URL", "http://127.0.0.1:8000")

def run_multiobjective_tests():
    print("================ CIRCULO AI MULTI-OBJECTIVE OPTIMIZER SUITE ================\n")
    passed = 0
    total = 0

    def check(name, condition, msg=""):
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"[PASS] {total}. {name}")
        else:
            print(f"[FAIL] {total}. {name}: {msg}")
            raise AssertionError(f"Test failed: {name} - {msg}")

    # 1. Multi-Objective Trade-Off Scoring in In-Memory Database
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    mem_conn.executescript("""
        CREATE TABLE buyers(id INTEGER PRIMARY KEY, name TEXT, category TEXT, accepted_grades TEXT,
          max_contamination REAL, min_qty REAL, max_qty REAL, lat REAL, lon REAL, location_name TEXT, service_radius_km REAL);
        CREATE TABLE lots(id INTEGER PRIMARY KEY, code TEXT, source_name TEXT, source_type TEXT,
          category TEXT, grade TEXT, colour TEXT, contamination_pct REAL, qty_kg REAL,
          lat REAL, lon REAL, location_name TEXT, status TEXT, allocated INTEGER DEFAULT 0);
        CREATE TABLE batches(id INTEGER PRIMARY KEY, code TEXT);
        CREATE TABLE batch_lots(batch_id INTEGER, lot_id INTEGER);
    """)

    mem_conn.execute("""INSERT INTO buyers(id, name, category, accepted_grades, max_contamination, min_qty, max_qty, lat, lon, location_name, service_radius_km)
      VALUES(1, 'EcoSpun Fibres (Dhaka)', 'cotton', 'A,B', 5.0, 1000.0, 5000.0, 23.8103, 90.4125, 'Dhaka', 60.0)""")

    # 4 unallocated cotton lots with diverse trade-offs
    # Lot 1: 400kg, 2.0% contam, verified, close (Dhaka)
    # Lot 2: 650kg, 3.5% contam, verified, close (Dhaka)
    # Lot 3: 500kg, 4.0% contam, pending, further (Gazipur)
    # Lot 4: 600kg, 1.5% contam, verified, medium (Ashulia)
    test_lots = [
        (1, "LOT-T1", "Alpha Mill", "factory", "cotton", "A", "white", 2.0, 400.0, 23.82, 90.42, "Dhaka", "verified", 0),
        (2, "LOT-T2", "Beta Fabrics", "factory", "cotton", "B", "off-white", 3.5, 650.0, 23.83, 90.43, "Dhaka", "verified", 0),
        (3, "LOT-T3", "Gamma Traders", "trader", "cotton", "B", "grey", 4.0, 500.0, 24.00, 90.42, "Gazipur", "pending", 0),
        (4, "LOT-T4", "Delta Knit", "factory", "cotton", "A", "white", 1.5, 600.0, 23.88, 90.26, "Ashulia", "verified", 0),
    ]
    mem_conn.executemany("INSERT INTO lots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", test_lots)
    mem_conn.commit()

    buyer = mem_conn.execute("SELECT * FROM buyers WHERE id=1").fetchone()
    eligible = [dict(r) for r in mem_conn.execute("SELECT * FROM lots").fetchall()]

    candidates = find_candidate_batches(mem_conn, buyer, eligible)
    check("Multi-Candidate Generation", len(candidates) >= 2, f"Expected at least 2 candidates, got {len(candidates)}")

    rec = candidates[0]
    check("Recommended Designation", rec.get("is_recommended") is True and rec.get("profile_id") == "recommended",
          f"Candidate 1 should be recommended, got: {rec}")

    check("Empirical Freight Calculation", rec["cost_per_kg"] > 0 and rec["route_km"] > 0 and rec["route_cost"] > 0,
          f"Invalid freight metrics: {rec['cost_per_kg']} BDT/kg, {rec['route_km']} km")

    check("Weighted Contamination Purity", 0.0 < rec["avg_contamination"] <= 5.0,
          f"Average contamination outside limits: {rec['avg_contamination']}")

    check("Physical QA Distinctions", rec["verified_pct"] > 0 and "v_label" in rec and "v_badge" in rec,
          f"Missing verification breakdown in candidate: {rec}")

    # Check that alternatives have clear rationales and individual lot IDs
    for alt in candidates[1:]:
        check(f"Alternative Profile Integrity ({alt['profile_name']})",
              alt.get("is_recommended") is False and len(alt["lot_ids"]) > 0 and len(alt["rationale"]) > 10,
              f"Malformed alternative candidate: {alt}")

    # Check Plan Aggregation on synthetic data
    plan_synthetic = plan_aggregation(mem_conn, 1)
    check("Synthetic Plan Aggregation Feasible", plan_synthetic["feasible"] is True, "Plan should be feasible")
    check("Synthetic Plan Returns Candidates", len(plan_synthetic["candidates"]) == len(candidates),
          f"Candidate mismatch: {len(plan_synthetic['candidates'])} vs {len(candidates)}")

    # Check HTML Rendering of Feasible Plan
    html_out = render_plan(plan_synthetic)
    check("UI Renders Recommended Batch Card", "Recommended (Balanced Optimal)" in html_out,
          "Missing recommended badge in HTML")
    check("UI Renders Multi-Objective Metric Tiles", "BDT/kg" in html_out and "Weighted Contam" in html_out,
          "Missing multi-objective metrics in HTML")
    check("UI Renders Candidate Batch Action CTA", "createBatch(" in html_out,
          "Missing createBatch CTA in rendered plan")

    mem_conn.close()

    # 2. Real Database State: Protection of Batches & Exclusion Prioritization
    real_conn = get_db("circulo.db")

    # Batches CIRC-2026-0001 (1,050 kg) and CIRC-2026-0002 (330 kg)
    b1 = real_conn.execute("SELECT * FROM batches WHERE code='CIRC-2026-0001'").fetchone()
    b2 = real_conn.execute("SELECT * FROM batches WHERE code='CIRC-2026-0002'").fetchone()
    check("Existing Batch 1 Preserved", b1 is not None and b1["total_kg"] == 1050.0, f"Batch 1 altered: {b1}")
    check("Existing Batch 2 Preserved", b2 is not None and b2["total_kg"] == 330.0, f"Batch 2 altered: {b2}")

    # All cotton lots (LOT-A, LOT-B, LOT-D, LOT-E, LOT-I) must be allocated
    alloc_rows = real_conn.execute("SELECT code FROM lots WHERE allocated=1 ORDER BY code").fetchall()
    alloc_codes = [r["code"] for r in alloc_rows]
    check("Allocated Lots Integrity", alloc_codes == ["LOT-A", "LOT-B", "LOT-D", "LOT-E", "LOT-I"],
          f"Unexpected allocated lots: {alloc_codes}")

    # Recycler X (buyer 1): 0 kg eligible, 1000 kg shortfall
    plan_x = plan_aggregation(real_conn, 1)
    check("Recycler X Feasible is False", plan_x["feasible"] is False, "Recycler X should not be feasible")
    check("Recycler X Shortfall Accuracy", plan_x["shortfall_kg"] == 1000.0 and plan_x["batch_kg"] == 0.0,
          f"Incorrect shortfall: {plan_x['shortfall_kg']}, batch_kg: {plan_x['batch_kg']}")
    check("Recycler X Shortfall Diagnostic Details",
          plan_x.get("shortfall_details") is not None and "Network deficit of 1,000 kg" in plan_x["shortfall_details"]["recommendation"],
          f"Missing shortfall details: {plan_x.get('shortfall_details')}")

    # Recycler Y (buyer 2): 200 kg eligible (LOT-F), 300 kg shortfall
    plan_y = plan_aggregation(real_conn, 2)
    check("Recycler Y Feasible is False", plan_y["feasible"] is False, "Recycler Y should not be feasible")
    check("Recycler Y Partial Volume Counted", plan_y["eligible_kg"] == 200.0 and plan_y["shortfall_kg"] == 300.0,
          f"Recycler Y eligible={plan_y['eligible_kg']}, shortfall={plan_y['shortfall_kg']}")
    check("Recycler Y Compatible Lot Table",
          len(plan_y["eligible"]) == 1 and plan_y["eligible"][0]["code"] == "LOT-F",
          f"Expected LOT-F in eligible, got: {plan_y['eligible']}")

    real_conn.close()

    # 3. Live Server Endpoint Tests
    req = urllib.request.Request(f"{BASE_URL}/api/aggregate",
                                 data=json.dumps({"buyer_id": 1}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        check("HTTP 200 from /api/aggregate (Buyer 1)", resp.getcode() == 200)
        res_data = json.loads(resp.read().decode("utf-8"))
        check("API Response ok Flag", res_data.get("ok") is True)
        plan_resp = res_data["plan"]
        check("API Shortfall Metric Agreement",
              plan_resp["shortfall_kg"] == 1000.0 and plan_resp["batch_kg"] == 0.0 and plan_resp["feasible"] is False,
              f"API plan mismatch: {plan_resp}")
        check("API Actionable Shortfall Diagnostic Rendered",
              "Aggregation Bottleneck Diagnostic" in res_data["html"] and "Deficit: 1,000 kg" in res_data["html"],
              "Shortfall diagnostic card missing in HTML")
        check("API Transparent Exclusion Allocated Badges Rendered",
              "b-alloc" in res_data["html"] and "Already allocated to CIRC-2026-0001" in res_data["html"],
              "Allocated exclusion badge missing in HTML")

    # Live Server Endpoint Test for Recycler Y (Buyer 2)
    req2 = urllib.request.Request(f"{BASE_URL}/api/aggregate",
                                  data=json.dumps({"buyer_id": 2}).encode("utf-8"),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        check("HTTP 200 from /api/aggregate (Buyer 2)", resp2.getcode() == 200)
        res_data2 = json.loads(resp2.read().decode("utf-8"))
        check("API Buyer 2 Shortfall Agreement",
              res_data2["plan"]["shortfall_kg"] == 300.0 and res_data2["plan"]["eligible_kg"] == 200.0,
              f"Buyer 2 plan mismatch: {res_data2['plan']}")
        check("API Buyer 2 Compatible Inventory Section",
              "Compatible Eligible Lots in Inventory" in res_data2["html"] and "LOT-F" in res_data2["html"],
              "Compatible inventory table missing in HTML")

    print("\n============================== SUMMARY ==============================")
    print(f"Total: {total} | Passed: {passed} | Failed: 0")
    print("=====================================================================")

if __name__ == "__main__":
    run_multiobjective_tests()
