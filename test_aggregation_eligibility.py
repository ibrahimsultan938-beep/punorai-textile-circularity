"""
CIRCULO AI - Aggregation Planner Eligibility & Feasibility Regression Test Suite
Validates:
1. LOT-I contributes 180 kg to eligible inventory when it satisfies all configured constraints and is unallocated.
2. When allocated, LOT-I (and LOT-E) are excluded with 'Already allocated to CIRC-2026-0002'.
3. Lots in CIRC-2026-0001 (LOT-A, LOT-B, LOT-D) are excluded with 'Already allocated to CIRC-2026-0001'.
4. Strict distinction between total eligible kilograms and feasible batch.
5. API endpoint /api/aggregate output for Recycler X reflects correct metrics and exclusion reasons.
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

def test_lot_i_and_eligible_inventory():
    print("\n--- Test 1: LOT-I Eligibility When Unallocated vs Allocated ---")
    conn = get_db()
    buyer = conn.execute("SELECT * FROM buyers WHERE id=1").fetchone()
    assert buyer["name"] == "Recycler X (Dhaka)"
    assert buyer["category"] == "cotton"
    assert buyer["accepted_grades"] == "A,B"
    assert buyer["max_contamination"] == 5.0
    assert buyer["min_qty"] == 1000.0

    lot_i = conn.execute("SELECT * FROM lots WHERE code='LOT-I'").fetchone()
    assert lot_i is not None, "LOT-I not found in database"
    assert lot_i["category"] == "cotton"
    assert lot_i["grade"] == "B"
    assert lot_i["contamination_pct"] == 4.0
    assert lot_i["qty_kg"] == 180.0

    # Test 1A: When unallocated, LOT-I satisfies all constraints and exclusion_reason is None
    lot_i_unalloc = dict(lot_i)
    lot_i_unalloc["allocated"] = 0
    reason_unalloc = exclusion_reason(lot_i_unalloc, buyer, conn)
    assert reason_unalloc is None, f"Expected None for unallocated LOT-I, got: {reason_unalloc}"
    print("PASS: When unallocated, LOT-I satisfies all Recycler X constraints (contributes 180 kg).")

    # Test 1B: When allocated to CIRC-2026-0002, exclusion_reason returns allocation code
    reason_alloc = exclusion_reason(lot_i, buyer, conn)
    assert reason_alloc == "Already allocated to CIRC-2026-0002", f"Expected allocation to CIRC-2026-0002, got: {reason_alloc}"
    print(f"PASS: When allocated in DB, LOT-I returns: '{reason_alloc}'.")

    conn.close()

def test_allocated_lots_exclusion():
    print("\n--- Test 2: Exclusion of Allocated Lots Across Batches ---")
    conn = get_db()
    buyer = conn.execute("SELECT * FROM buyers WHERE id=1").fetchone()

    # Lots allocated to batch CIRC-2026-0001
    for code in ["LOT-A", "LOT-B", "LOT-D"]:
        lot = conn.execute("SELECT * FROM lots WHERE code=?", (code,)).fetchone()
        assert lot["allocated"] == 1
        reason = exclusion_reason(lot, buyer, conn)
        assert reason == "Already allocated to CIRC-2026-0001", f"Expected CIRC-2026-0001 exclusion for {code}, got: {reason}"

    # Lots allocated to batch CIRC-2026-0002
    for code in ["LOT-E", "LOT-I"]:
        lot = conn.execute("SELECT * FROM lots WHERE code=?", (code,)).fetchone()
        assert lot["allocated"] == 1
        reason = exclusion_reason(lot, buyer, conn)
        assert reason == "Already allocated to CIRC-2026-0002", f"Expected CIRC-2026-0002 exclusion for {code}, got: {reason}"

    plan = plan_aggregation(conn, 1)
    eligible_codes = [l["code"] for l in plan["eligible"]]
    for code in ["LOT-A", "LOT-B", "LOT-D", "LOT-E", "LOT-I"]:
        assert code not in eligible_codes, f"Allocated lot {code} was erroneously included in eligible!"
    print("PASS: All allocated lots (CIRC-2026-0001 and CIRC-2026-0002) are strictly excluded from eligible inventory.")
    conn.close()

def test_api_aggregate_endpoint():
    print("\n--- Test 3: API Endpoint /api/aggregate Output for Recycler X ---")
    url = f"{BASE_URL}/api/aggregate"
    payload = json.dumps({"buyer_id": 1}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.getcode() == 200
        data = json.loads(resp.read().decode("utf-8"))

    assert data.get("ok") is True
    plan = data["plan"]
    assert plan["feasible"] is False
    assert plan["eligible_kg"] == 0.0
    assert plan["batch_kg"] == 0.0
    assert plan["shortfall_kg"] == 1000.0

    html = data["html"]
    assert "Feasible batch not currently possible" in html
    assert "Feasible batch weight: <b>0 kg</b>" in html
    assert "shortfall of <b>1,000 kg</b>" in html

    # Check that exclusion table renders allocated batch codes
    assert "Already allocated to CIRC-2026-0001" in html
    assert "Already allocated to CIRC-2026-0002" in html
    assert "badge b-alloc" in html

    # Check button is not rendered
    assert "Create Batch & Issue Material Passport" not in html
    print("PASS: /api/aggregate renders 0 kg eligible, 1000 kg shortfall, and includes accurate allocation reason badges.")

if __name__ == "__main__":
    test_lot_i_and_eligible_inventory()
    test_allocated_lots_exclusion()
    test_api_aggregate_endpoint()
    print("\n================ ALL REGRESSION TESTS PASSED ================\n")
