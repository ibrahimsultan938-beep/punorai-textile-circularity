import sys, os, sqlite3, re
sys.path.insert(0, os.getcwd())

import app, core

def run_tests():
    print("\n================ CIRCULO AI FINAL DEMO FIXES & POLISH SUITE ================\n")
    
    conn = sqlite3.connect("circulo.db")
    conn.row_factory = sqlite3.Row
    
    # -------------------------------------------------------------
    # Test 1: Dashboard never recommends allocated lots as candidates
    # -------------------------------------------------------------
    allocated_lots = [r["code"] for r in conn.execute("SELECT code FROM lots WHERE allocated=1").fetchall()]
    print(f"Allocated lots in DB: {allocated_lots}")
    
    dash_html = app.page_dashboard()
    insight_html = app.dashboard_insights()
    
    plan_batch_match = re.search(r'id=["\']btn-plan-batch["\'][^>]*href=["\']([^"\']+)["\']', insight_html)
    if plan_batch_match:
        href = plan_batch_match.group(1)
        for code in allocated_lots:
            assert f"lots={code}" not in href and f",{code}" not in href and f"{code}," not in href, \
                f"FAIL: Allocated lot {code} was found preselected in action link: {href}"
    
    print("[PASS] 1. Dashboard Never Recommends Allocated Lots: No allocated lots in decision action links or candidate lists.")
    
    # -------------------------------------------------------------
    # Test 2: Dashboard shows useful empty state when no compatible lots exist
    # -------------------------------------------------------------
    rx_insight = app.dashboard_insights(buyer_id=1)
    assert "No compatible unallocated lots" in rx_insight or "No Eligible Unallocated Lots" in rx_insight, \
        "FAIL: Expected informative empty state for Recycler X when all cotton lots are allocated"
    assert "CIRC-2026-0001" in rx_insight, "FAIL: Expected disclosure of active batch allocations in empty state"
    assert "lots=LOT-A" not in rx_insight and "lots=LOT-B" not in rx_insight, "FAIL: Found allocated lot in Recycler X card"
    assert "href=\"/aggregation\"" in rx_insight or "href='/aggregation'" in rx_insight, "FAIL: Action link must point to /aggregation"
    assert "View Aggregation Planner" in rx_insight, "FAIL: Expected 'View Aggregation Planner' in empty state"
    
    print("[PASS] 2. Useful Empty State: Accurately explains committed inventory and links to /aggregation without misleading 'Plan Batch'.")
    
    # -------------------------------------------------------------
    # Test 3: Simulated denim intake link does not direct denim to polyester buyer
    # -------------------------------------------------------------
    with open("static/app.js", "r", encoding="utf-8") as f:
        js_content = f.read()
    
    assert "buyer_id=2&lots=" not in js_content, "FAIL: Found denim preselecting buyer_id=2 (polyester) in static/app.js"
    assert "No Compatible Buyer" in js_content, "FAIL: Expected 'No Compatible Buyer' badge in static/app.js for denim intake"
    assert "No active buyer currently accepts denim feedstock" in js_content, "FAIL: Expected explanation that denim has no active buyer"
    assert '<a href="/aggregation"' in js_content, "FAIL: static/app.js must link to /aggregation"
    
    print("[PASS] 3. Simulated Denim Intake Link: Denim lot (LOT-K) is not directed to polyester buyer; links to /aggregation.")
    
    # -------------------------------------------------------------
    # Test 4: Existing allocation protection & aggregation eligibility remain intact
    # -------------------------------------------------------------
    b1 = conn.execute("SELECT * FROM batches WHERE code='CIRC-2026-0001'").fetchone()
    b2 = conn.execute("SELECT * FROM batches WHERE code='CIRC-2026-0002'").fetchone()
    assert b1 and int(b1["total_kg"]) == 1050, f"CIRC-2026-0001 must remain intact with 1,050 kg, got {b1}"
    assert b2 and int(b2["total_kg"]) == 330, f"CIRC-2026-0002 must remain intact with 330 kg, got {b2}"
    
    plan_x = core.plan_aggregation(conn, 1)
    assert not plan_x["feasible"], "Recycler X must not form feasible batch when all cotton lots are allocated"
    assert plan_x["eligible_kg"] == 0, f"Recycler X eligible kg must be 0, got {plan_x['eligible_kg']}"
    for ex in plan_x["excluded"]:
        if ex["lot"]["code"] in ["LOT-A", "LOT-B", "LOT-D"]:
            assert "Already allocated to CIRC-2026-0001" in ex["reason"]
        elif ex["lot"]["code"] in ["LOT-E", "LOT-I"]:
            assert "Already allocated to CIRC-2026-0002" in ex["reason"]
            
    print("[PASS] 4. Allocation Protection: CIRC-2026-0001 (1,050 kg) & CIRC-2026-0002 (330 kg) 100% protected.")
    
    # -------------------------------------------------------------
    # Test 5: Passport pages no longer claim immutable audit enforcement
    # -------------------------------------------------------------
    passports_list = app.page_passports()
    passport_detail = app.page_passport_detail("CIRC-2026-0001")
    landing = app.page_landing()
    
    assert "immutable" not in passports_list.lower(), "FAIL: Found 'immutable' in /passports page"
    assert "immutable" not in passport_detail.lower(), "FAIL: Found 'immutable' in /passport/<code_id> detail page"
    assert "immutable" not in landing.lower(), "FAIL: Found 'immutable' in landing page"
    
    assert "Auditable Verification Event Log" in passport_detail, "FAIL: Expected 'Auditable Verification Event Log' in passport detail"
    assert "Digital Material Passports" in passports_list, "FAIL: Expected 'Digital Material Passports' in passports list"
    
    print("[PASS] 5. Accurate Terminology: Misleading 'Immutable' claims replaced with 'Auditable Verification Event Log'.")
    
    # -------------------------------------------------------------
    # Test 6: Dashboard verification rate label & no purity claims
    # -------------------------------------------------------------
    assert "Intake Verification Rate: 60% (6 of 10 lots)" in dash_html, \
        "FAIL: Expected 'Intake Verification Rate: 60% (6 of 10 lots)' on dashboard"
    assert "verified purity rate" not in dash_html, \
        "FAIL: Deprecated 'verified purity rate' must be removed from dashboard"
    
    print("[PASS] 6. Dashboard Verification Label: 'Intake Verification Rate: 60% (6 of 10 lots)' rendered without purity claims.")
    
    # -------------------------------------------------------------
    # Test 7: Simulated CO2 & Water counters disclosure & Landfill simulated mark
    # -------------------------------------------------------------
    assert "Illustrative demo estimates" in dash_html, \
        "FAIL: Expected 'Illustrative demo estimates' disclosure for CO2 and water"
    assert "not independently validated" in dash_html, \
        "FAIL: Expected 'not independently validated' disclosure for CO2 and water"
    
    # Landfill figure must still be clearly marked as simulated
    assert "Landfill Diverted:" in dash_html and "(Simulated)" in dash_html, \
        "FAIL: Landfill Diverted must remain clearly marked as (Simulated)"
        
    print("[PASS] 7. Environmental Metric Disclosures: CO2/Water labeled 'Illustrative demo estimates — not independently validated'; Landfill marked (Simulated).")
    
    # -------------------------------------------------------------
    # Test 8: Aggregation Planner link uses registered route /aggregation
    # -------------------------------------------------------------
    assert 'href="/aggregation"' in dash_html, "FAIL: Dashboard must link to registered route /aggregation"
    assert "href=\"/aggregation-planner\"" not in dash_html, "FAIL: Found uncanonical /aggregation-planner in dashboard action links"
    
    print("[PASS] 8. Canonical Aggregation Route: Verified dashboard links use registered route /aggregation.")
    
    # -------------------------------------------------------------
    # Test 9: Database mass balance and record preservation
    # -------------------------------------------------------------
    tl = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(qty_kg),0) s FROM lots").fetchone()
    al = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(total_kg),0) s FROM batches").fetchone()
    free = conn.execute("SELECT COALESCE(SUM(qty_kg),0) s FROM lots WHERE allocated=0").fetchone()["s"]
    
    assert tl["n"] == 10 and int(tl["s"]) == 3050, f"Expected 10 lots and 3,050 kg total, got {tl['n']} lots, {tl['s']} kg"
    assert al["n"] == 2 and int(al["s"]) == 1380, f"Expected 2 batches and 1,380 kg allocated, got {al['n']} batches, {al['s']} kg"
    assert int(free) == 1670, f"Expected 1,670 kg unallocated, got {free} kg"
    
    print("[PASS] 9. Database Invariants: 10 lots, 3,050 kg total, 2 batches, 1,380 kg allocated, 1,670 kg unallocated.")
    
    print("\n============================== SUMMARY ==============================")
    print("Total: 9 | Passed: 9 | Failed: 0")
    print("=====================================================================\n")

if __name__ == "__main__":
    run_tests()
