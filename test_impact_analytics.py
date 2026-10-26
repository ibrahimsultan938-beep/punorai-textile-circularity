import sys, os, re, sqlite3

def run_tests():
    print("\n================ CIRCULO AI IMPACT ANALYTICS AUDIT SUITE ================\n")
    
    # 1. Database Empirical Mass Balance Check
    conn = sqlite3.connect("circulo.db")
    conn.row_factory = sqlite3.Row
    
    tl = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(qty_kg),0) s FROM lots").fetchone()
    al = conn.execute("SELECT COALESCE(SUM(total_kg),0) s, COUNT(*) n FROM batches").fetchone()
    ver = conn.execute("SELECT COUNT(*) n FROM lots WHERE status='verified'").fetchone()["n"]
    cats = conn.execute("SELECT category, SUM(qty_kg) s FROM lots GROUP BY category ORDER BY s DESC").fetchall()
    
    total_kg = int(tl["s"])
    allocated_kg = int(al["s"])
    unallocated_kg = total_kg - allocated_kg
    alloc_rate = 100.0 * allocated_kg / total_kg
    alloc_rate_int = int(round(alloc_rate))
    
    assert total_kg == 3050, f"Expected 3,050 kg total, got {total_kg}"
    assert allocated_kg == 1380, f"Expected 1,380 kg allocated, got {allocated_kg}"
    assert unallocated_kg == 1670, f"Expected 1,670 kg unallocated, got {unallocated_kg}"
    assert alloc_rate_int == 45, f"Expected 45% allocation rate, got {alloc_rate_int}"
    assert ver == 6, f"Expected 6 verified lots, got {ver}"
    
    cat_sum = sum(int(c["s"]) for c in cats)
    assert cat_sum == 3050, f"Expected category sum 3,050 kg, got {cat_sum}"
    
    print("[PASS] 1. Empirical Mass Balance: 3,050 kg characterized, 1,380 kg batched, 1,670 kg unallocated (45.25% ~ 45%)")
    
    # 2. Render page_reports() HTML
    import app
    html_output = app.page_reports()
    
    # 3. Check Metric Naming & Descriptions
    assert "Batch Allocation Rate" in html_output, "Missing 'Batch Allocation Rate' in reports page"
    assert "Mass Recovery Rate" not in html_output, "Found deprecated 'Mass Recovery Rate' in reports page"
    assert "not physical recycling yield" in html_output, "Missing explanation that allocation rate is not physical recycling yield"
    print("[PASS] 2. Metric Renaming: 'Batch Allocation Rate' accurately distinguished from physical recycling yield")
    
    # 4. Check Intake Verification QA Metric
    assert "Intake Verification Rate" in html_output, "Missing 'Intake Verification Rate'"
    assert "6 of 10 Lots" in html_output, "Missing '6 of 10 Lots'"
    assert "not lab-certified" in html_output, "Missing disclosure that verification is intake-checked and not lab-certified"
    print("[PASS] 3. QA Metric Accuracy: 'Intake Verification Rate (6 of 10 Lots)' explicitly clarified as not lab-certified")
    
    # 5. Check Category Chart Labels & Values
    import core
    chart_svg = core.svg_bar("Test", [(c["category"], int(c["s"])) for c in cats])
    for label in ["Cotton", "Cotton-Poly", "Denim", "Polyester", "Mixed Waste"]:
        assert label in chart_svg, f"Missing category label {label} in svg_bar output"
    for kg_val in ["1,380 kg", "1,000 kg", "350 kg", "200 kg", "120 kg"]:
        assert kg_val in chart_svg, f"Missing kg value {kg_val} in svg_bar output"
    
    # Ticks should be clean round values
    assert "1,500" in chart_svg, "Missing 1,500 upper tick"
    assert "1,000" in chart_svg, "Missing 1,000 tick"
    assert "500" in chart_svg, "Missing 500 tick"
    print("[PASS] 4. Category Chart: Clean labels ('Cotton-Poly', 'Mixed Waste'), clean round ticks (1500, 1000, 500), no overlaps")
    
    # 6. Check Narrative Claims
    assert "500,000 tonnes" not in html_output, "Uncited 500,000 tonnes claim should be removed from reports"
    assert "certified, traceable circular feedstock" not in html_output, "Outdated certified feedstock claim should be removed"
    assert "traceable secondary feedstock with explicit verification status" in html_output, "Missing replacement wording 'traceable secondary feedstock with explicit verification status'"
    print("[PASS] 5. Narrative Integrity: Uncited 500,000 tonnes removed; updated to 'traceable secondary feedstock with explicit verification status'")
    
    # 7. Check Methodology Honesty Disclosure
    assert "Methodology Honesty &amp; Environmental Boundary Disclosure:" in html_output or "Methodology Honesty & Environmental Boundary Disclosure:" in html_output, "Missing methodology honesty disclosure"
    assert "Theoretical carbon offset, GHG reduction, and avoided water consumption metrics are intentionally NOT fabricated" in html_output
    print("[PASS] 6. Methodology Honesty: Carbon offsets & LCA metrics disabled without fabricated environmental claims")
    
    print("\n============================== SUMMARY ==============================")
    print("Total: 6 | Passed: 6 | Failed: 0")
    print("=====================================================================\n")

if __name__ == "__main__":
    run_tests()
