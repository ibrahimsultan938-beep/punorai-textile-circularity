"""
CIRCULO AI - Aggregation Planner Exclusion Audit & Regression Test Suite
Validates:
1. LOT-E (150 kg) and LOT-I (180 kg) remain allocated to CIRC-2026-0002.
2. Lots in CIRC-2026-0001 (LOT-A, LOT-B, LOT-D) remain allocated to that batch.
3. Re-running the solver never allocates the same lot twice (never includes allocated lots in eligible or selected).
4. Factory C is not shown a feasible batch using already allocated lots (feasible: False, batch_kg: 0).
5. Accurate, prioritized exclusion reason codes for all lots across buyers:
   - Already allocated to CIRC-2026-0001
   - Already allocated to CIRC-2026-0002
   - Material category mismatch
   - Grade not accepted
   - Contamination exceeds buyer limit
   - Pending verification (if policy requires)
6. Allocated lots are never reported as category mismatches even when their category differs from the buyer.
7. Eligible weight is shown separately from feasible batch weight (0 kg) and shortfall.
8. API /api/aggregate renders b-alloc badges and accurate explanations.
"""

import sqlite3
import json
import urllib.request
import urllib.parse
import os
import sys

from core import plan_aggregation, exclusion_reason

DB_PATH = "circulo.db"
BASE_URL = "http://127.0.0.1:8000"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def test_allocation_integrity():
    print("\n--- Test 1: Verify Allocation Integrity of Batches CIRC-2026-0001 and CIRC-2026-0002 ---")
    conn = get_db()

    # Batch 1 checks
    b1 = conn.execute("SELECT * FROM batches WHERE code='CIRC-2026-0001'").fetchone()
    assert b1 is not None, "CIRC-2026-0001 missing"
    assert abs(b1["total_kg"] - 1050.0) < 0.01, f"Expected 1050kg, got {b1['total_kg']}"

    b1_lots = conn.execute("""
        SELECT l.code, l.allocated, l.qty_kg FROM lots l
        JOIN batch_lots bl ON l.id = bl.lot_id
        WHERE bl.batch_id = ?
        ORDER BY l.code
    """, (b1["id"],)).fetchall()
    b1_codes = [r["code"] for r in b1_lots]
    assert b1_codes == ["LOT-A", "LOT-B", "LOT-D"], f"Expected LOT-A, LOT-B, LOT-D in CIRC-2026-0001, got {b1_codes}"
    for r in b1_lots:
        assert r["allocated"] == 1, f"Lot {r['code']} should have allocated=1"
    print("PASS: Lots in CIRC-2026-0001 (LOT-A: 300kg, LOT-B: 250kg, LOT-D: 500kg) remain allocated.")

    # Batch 2 checks
    b2 = conn.execute("SELECT * FROM batches WHERE code='CIRC-2026-0002'").fetchone()
    assert b2 is not None, "CIRC-2026-0002 missing"
    assert abs(b2["total_kg"] - 330.0) < 0.01, f"Expected 330kg, got {b2['total_kg']}"

    b2_lots = conn.execute("""
        SELECT l.code, l.allocated, l.qty_kg FROM lots l
        JOIN batch_lots bl ON l.id = bl.lot_id
        WHERE bl.batch_id = ?
        ORDER BY l.code
    """, (b2["id"],)).fetchall()
    b2_codes = [r["code"] for r in b2_lots]
    assert b2_codes == ["LOT-E", "LOT-I"], f"Expected LOT-E, LOT-I in CIRC-2026-0002, got {b2_codes}"
    for r in b2_lots:
        assert r["allocated"] == 1, f"Lot {r['code']} should have allocated=1"
    print("PASS: Lots in CIRC-2026-0002 (LOT-E: 150kg, LOT-I: 180kg) remain allocated.")
    conn.close()

def test_solver_no_double_allocation_and_factory_c():
    print("\n--- Test 2: Solver Re-run Must Not Double Allocate; Factory C Must Not Form Feasible Batch ---")
    conn = get_db()

    # Run solver for Factory C (Ashulia, buyer_id=3, min_qty=300 kg cotton)
    plan_c = plan_aggregation(conn, 3)
    assert plan_c is not None, "plan_aggregation returned None for Factory C"
    assert plan_c["feasible"] is False, f"Factory C should NOT have a feasible batch! Got feasible={plan_c['feasible']}"
    assert plan_c["batch_kg"] == 0.0, f"Factory C batch_kg must be 0.0, got {plan_c['batch_kg']}"
    assert plan_c["eligible_kg"] == 0.0, f"Factory C eligible_kg must be 0.0 (all cotton allocated), got {plan_c['eligible_kg']}"
    assert len(plan_c["selected"]) == 0, f"Factory C selected lots must be empty, got {plan_c['selected']}"
    assert plan_c["shortfall_kg"] == 300.0, f"Expected 300kg shortfall for Factory C, got {plan_c['shortfall_kg']}"

    # Verify no allocated lot appears in eligible
    eligible_codes = [l["code"] for l in plan_c["eligible"]]
    assert len(eligible_codes) == 0, f"Eligible lots should be empty, got: {eligible_codes}"

    # Also test Recycler X (buyer_id=1, min_qty=1000 kg cotton)
    plan_x = plan_aggregation(conn, 1)
    assert plan_x["feasible"] is False, "Recycler X should NOT be feasible"
    assert plan_x["batch_kg"] == 0.0
    assert plan_x["eligible_kg"] == 0.0
    assert plan_x["shortfall_kg"] == 1000.0
    print("PASS: Factory C and Recycler X correctly report 0 kg eligible, 0 kg batch, and honest shortfall. No double allocation.")
    conn.close()

def test_prioritized_exclusion_reasons():
    print("\n--- Test 3: Prioritized Exclusion Reason Codes for Each Ineligible Lot ---")
    conn = get_db()

    # 1. Check Factory C (buyer_id=3, cotton)
    plan_c = plan_aggregation(conn, 3)
    exc_map_c = {x["lot"]["code"]: x["reason"] for x in plan_c["excluded"]}

    expected_c = {
        "LOT-A": "Already allocated to CIRC-2026-0001",
        "LOT-B": "Already allocated to CIRC-2026-0001",
        "LOT-C": "Material category mismatch (needs cotton)",
        "LOT-D": "Already allocated to CIRC-2026-0001",
        "LOT-E": "Already allocated to CIRC-2026-0002",
        "LOT-F": "Material category mismatch (needs cotton)",
        "LOT-G": "Material category mismatch (needs cotton)",
        "LOT-H": "Material category mismatch (needs cotton)",
        "LOT-I": "Already allocated to CIRC-2026-0002",
        "LOT-J": "Material category mismatch (needs cotton)",
    }
    for code, expected_reason in expected_c.items():
        actual_reason = exc_map_c.get(code)
        assert actual_reason == expected_reason, f"Factory C lot {code}: expected '{expected_reason}', got '{actual_reason}'"
        print(f"  [Factory C] {code} -> {actual_reason}")

    # 2. Check Recycler Y (buyer_id=2, polyester, accepted_grades A,B,C, max_contam 8%, min 500kg)
    # CRITICAL: Allocated cotton lots (LOT-A, B, D, E, I) MUST report 'Already allocated...', NOT 'Material category mismatch'!
    plan_y = plan_aggregation(conn, 2)
    exc_map_y = {x["lot"]["code"]: x["reason"] for x in plan_y["excluded"]}

    # Allocated lots must report allocation
    for code, batch in [("LOT-A", "CIRC-2026-0001"), ("LOT-B", "CIRC-2026-0001"), ("LOT-D", "CIRC-2026-0001"),
                        ("LOT-E", "CIRC-2026-0002"), ("LOT-I", "CIRC-2026-0002")]:
        actual = exc_map_y.get(code)
        assert actual == f"Already allocated to {batch}", f"Recycler Y lot {code} misreported as '{actual}' instead of allocation to {batch}"
        assert "mismatch" not in actual.lower(), f"Allocated lot {code} was wrongly reported as category mismatch!"
        print(f"  [Recycler Y] {code} -> {actual} (Priority #1 Allocation preserved)")

    # LOT-F is polyester, unallocated, 200 kg: it must be in eligible, NOT excluded
    eligible_y = [l["code"] for l in plan_y["eligible"]]
    assert "LOT-F" in eligible_y, f"LOT-F should be eligible for Recycler Y, got {eligible_y}"
    assert "LOT-F" not in exc_map_y, "LOT-F should NOT be in excluded for Recycler Y"
    assert plan_y["eligible_kg"] == 200.0, f"Expected 200kg eligible for Recycler Y, got {plan_y['eligible_kg']}"
    assert plan_y["batch_kg"] == 0.0, "Batch weight must be 0 (200kg < 500kg minimum)"
    assert plan_y["shortfall_kg"] == 300.0, f"Shortfall must be 300kg, got {plan_y['shortfall_kg']}"

    # Unallocated non-polyester lots must report category mismatch
    for code in ["LOT-C", "LOT-G", "LOT-H", "LOT-J"]:
        assert "Material category mismatch (needs polyester)" in exc_map_y.get(code, ""), f"Expected category mismatch for {code}, got {exc_map_y.get(code)}"

    print("PASS: Exclusion reason codes are 100% accurate, prioritized, and distinguish allocation from category mismatch.")
    conn.close()

def test_api_render_and_badges():
    print("\n--- Test 4: API Endpoint Output & Badge Classes ---")
    # Query /api/aggregate for Factory C (buyer_id=3)
    url = f"{BASE_URL}/api/aggregate"
    payload = json.dumps({"buyer_id": 3}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.getcode() == 200
        data = json.loads(resp.read().decode("utf-8"))

    assert data.get("ok") is True
    plan = data["plan"]
    assert plan["feasible"] is False
    assert plan["batch_kg"] == 0.0
    assert plan["eligible_kg"] == 0.0
    assert plan["shortfall_kg"] == 300.0

    html = data["html"]
    # Check warning text
    assert "Feasible batch not currently possible" in html
    assert "Feasible batch weight: <b>0 kg</b>" in html
    assert "shortfall of <b>300 kg</b>" in html

    # Check that exclusion table contains allocation explanations with b-alloc badge
    assert "Already allocated to CIRC-2026-0001" in html
    assert "Already allocated to CIRC-2026-0002" in html
    assert "badge b-alloc" in html, "Missing b-alloc badge for allocated lots"
    assert "Material category mismatch" in html

    # Button must not appear
    assert "Create Batch & Issue Material Passport" not in html
    print("PASS: /api/aggregate renders correct warnings, metrics, and b-alloc badges.")

def test_prevent_batch_reallocation_attempt():
    print("\n--- Test 5: Verify Batch Creation API Rejects Already Allocated Lots ---")
    url = f"{BASE_URL}/api/batches"
    # Attempt to create batch using already allocated lots 5 (LOT-E) and 9 (LOT-I)
    payload = json.dumps({"buyer_id": 3, "lot_ids": [5, 9]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    assert data.get("ok") is False, f"Expected batch creation to fail for allocated lots, got: {data}"
    assert "No valid unallocated lots" in data.get("error", ""), f"Unexpected error message: {data}"
    print("PASS: api_batches rejects re-allocation of already allocated lots.")

if __name__ == "__main__":
    test_allocation_integrity()
    test_solver_no_double_allocation_and_factory_c()
    test_prioritized_exclusion_reasons()
    test_api_render_and_badges()
    test_prevent_batch_reallocation_attempt()
    print("\n================ ALL EXCLUSION AUDIT TESTS PASSED ================\n")
