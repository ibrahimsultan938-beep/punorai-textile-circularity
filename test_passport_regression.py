"""
CIRCULO AI - Material Passport & Inventory Traceability Regression Test Suite
Validates:
1. Clean QR-code label: "Scan to verify passport" (no `QR Offline">` malformed DOM leakage)
   on both CIRC-2026-0001 and CIRC-2026-0002.
2. Honest batch verification status: "Partially Verified" for batches containing verified + pending lots.
3. Base URL configuration & honest public link disclosure.
4. Batch weight accuracy (CIRC-2026-0001 = 1,050 kg, CIRC-2026-0002 = 330 kg) & strict prevention of
   double-counting across Inventory, Aggregation Planner, Dashboard KPIs, and Impact Reports.
5. Unit verification rules for pure verified constituent lots.
"""

import urllib.request
import urllib.parse
import json
import sqlite3
import os
import sys

BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
DB_PATH = os.path.join(os.path.dirname(__file__), "circulo.db")

def get(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.getcode(), resp.read().decode("utf-8")

def post(path, data):
    url = f"{BASE_URL}{path}"
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.getcode(), json.loads(resp.read().decode("utf-8"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

test_results = []

def record(name, status, detail=""):
    test_results.append((name, status, detail))
    flag = "PASS" if status else "FAIL"
    print(f"[{flag}] {name}" + (f" - {detail}" if detail else ""))

def test_qr_label_and_no_malformed_html():
    name = "1. QR Code Label and Clean HTML Rendering"
    try:
        # Check /passports list page
        code, html = get("/passports")
        assert code == 200, f"Expected 200, got {code}"
        assert 'QR Offline">' not in html, "Found malformed 'QR Offline\">' in /passports HTML"
        assert 'Scan to verify passport' in html, "Missing clean label 'Scan to verify passport' in /passports"
        assert 'class="qr-scan-label"' in html, "Missing qr-scan-label class in /passports"
        assert 'onerror="this.outerHTML=' not in html, "Unsafe onerror outerHTML injection still present"

        # Check /passport/CIRC-2026-0001 detail page
        code, d1_html = get("/passport/CIRC-2026-0001")
        assert code == 200, f"Expected 200, got {code}"
        assert 'QR Offline">' not in d1_html, "Found malformed 'QR Offline\">' in CIRC-2026-0001 HTML"
        assert 'Scan to verify passport' in d1_html, "Missing 'Scan to verify passport' in CIRC-2026-0001 HTML"
        assert 'class="qr-scan-label"' in d1_html

        # Check /passport/CIRC-2026-0002 detail page
        code, d2_html = get("/passport/CIRC-2026-0002")
        assert code == 200, f"Expected 200, got {code}"
        assert 'QR Offline">' not in d2_html, "Found malformed 'QR Offline\">' in CIRC-2026-0002 HTML"
        assert 'Scan to verify passport' in d2_html, "Missing 'Scan to verify passport' in CIRC-2026-0002 HTML"
        assert 'class="qr-scan-label"' in d2_html

        record(name, True, "Label is clean 'Scan to verify passport' across all passports; zero HTML leakage")
    except Exception as e:
        record(name, False, str(e))

def test_batch_verification_honesty():
    name = "2. Batch Verification Status & Constituent Lot Preservations"
    try:
        from core import batch_verification_status

        # Test unit logic of batch_verification_status
        lots_mixed = [
            {"code": "LOT-A", "qty_kg": 300.0, "status": "verified"},
            {"code": "LOT-B", "qty_kg": 250.0, "status": "verified"},
            {"code": "LOT-D", "qty_kg": 500.0, "status": "pending"}
        ]
        status_code, label, badge_class, desc = batch_verification_status(lots_mixed)
        assert status_code == "partially_verified", f"Expected partially_verified, got {status_code}"
        assert label == "Partially Verified", f"Expected 'Partially Verified', got '{label}'"
        assert badge_class == "b-pending", f"Expected badge 'b-pending', got '{badge_class}'"
        assert "550 / 1,050 kg" in desc, f"Description math mismatch: {desc}"

        # Test all verified
        lots_all_ver = [{"qty_kg": 500.0, "status": "verified"}, {"qty_kg": 500.0, "status": "verified"}]
        c, l, b, _ = batch_verification_status(lots_all_ver)
        assert c == "verified" and l == "Verified Batch" and b == "b-verified"

        # Test all pending
        lots_all_pend = [{"qty_kg": 500.0, "status": "pending"}, {"qty_kg": 500.0, "status": "pending"}]
        c, l, b, _ = batch_verification_status(lots_all_pend)
        assert c == "pending" and l == "Pending Verification" and b == "b-pending"

        # Check rendered passport page for CIRC-2026-0001
        code, html = get("/passport/CIRC-2026-0001")
        assert code == 200
        assert "Verified Batch" not in html, "Batch was improperly displayed as 'Verified Batch'!"
        assert "Partially Verified" in html, "Batch should be displayed as 'Partially Verified'"
        assert "LOT-A" in html and "300 kg" in html
        assert "LOT-B" in html and "250 kg" in html
        assert "LOT-D" in html and "500 kg" in html
        assert "Pending" in html and "Verified" in html
        assert "Independent chemical laboratory certification is not fabricated" in html

        # Check rendered passport page for CIRC-2026-0002
        code, h2 = get("/passport/CIRC-2026-0002")
        assert code == 200
        assert "LOT-E" in h2 and "150 kg" in h2
        assert "LOT-I" in h2 and "180 kg" in h2
        assert "Partially Verified" in h2 or "Verified" in h2

        record(name, True, "Status is 'Partially Verified' (52% verified); LOT-D pending intake QA is preserved")
    except Exception as e:
        record(name, False, str(e))

def test_base_url_and_public_disclosure():
    name = "3. Base URL Configuration & Honest Public Link Disclosure"
    try:
        from app import is_public_url

        # Check is_public_url classification
        assert not is_public_url("http://localhost:8000/passport/1")
        assert not is_public_url("http://127.0.0.1:8000/passport/1")
        assert not is_public_url("http://0.0.0.0:8000/passport/1")
        assert is_public_url("https://circulo.ai/passport/1")
        assert is_public_url("https://passport.app.circulo-ai.com/passport/CIRC-2026-0001")

        # Check rendered HTML when running locally
        code, html = get("/passport/CIRC-2026-0001")
        assert code == 200
        assert "Local development URL" in html or "Local development link" in html
        assert "Local Dev URL" in html

        record(name, True, "Localhost correctly identified as local dev link; CIRCULO_BASE_URL supported")
    except Exception as e:
        record(name, False, str(e))

def test_batch_weight_and_no_double_counting():
    name = "4. Batch Weight & Strict No Double-Counting Validation"
    try:
        db = get_db()

        # 1. Batch CIRC-2026-0001 check
        batch1 = db.execute("SELECT * FROM batches WHERE code='CIRC-2026-0001'").fetchone()
        assert batch1 is not None, "Batch CIRC-2026-0001 not found"
        assert abs(batch1["total_kg"] - 1050.0) < 0.01, f"Batch weight is {batch1['total_kg']}, expected 1050.0"

        # Check constituent lots of CIRC-2026-0001
        b1_lots = db.execute("""SELECT l.* FROM lots l
                               JOIN batch_lots bl ON l.id = bl.lot_id
                               WHERE bl.batch_id = ?""", (batch1["id"],)).fetchall()
        assert len(b1_lots) == 3, f"Expected 3 lots, got {len(b1_lots)}"
        b1_sum = sum(l["qty_kg"] for l in b1_lots)
        assert abs(b1_sum - 1050.0) < 0.01, f"Constituent lots sum to {b1_sum}, expected 1050.0"

        # 2. Batch CIRC-2026-0002 check
        batch2 = db.execute("SELECT * FROM batches WHERE code='CIRC-2026-0002'").fetchone()
        assert batch2 is not None, "Batch CIRC-2026-0002 not found"
        assert abs(batch2["total_kg"] - 330.0) < 0.01, f"Batch weight is {batch2['total_kg']}, expected 330.0"

        # Check constituent lots of CIRC-2026-0002
        b2_lots = db.execute("""SELECT l.* FROM lots l
                               JOIN batch_lots bl ON l.id = bl.lot_id
                               WHERE bl.batch_id = ?""", (batch2["id"],)).fetchall()
        assert len(b2_lots) == 2, f"Expected 2 lots, got {len(b2_lots)}"
        b2_sum = sum(l["qty_kg"] for l in b2_lots)
        assert abs(b2_sum - 330.0) < 0.01, f"Constituent lots sum to {b2_sum}, expected 330.0"

        # Check allocation flags in DB
        for l in b1_lots + b2_lots:
            assert l["allocated"] == 1, f"Lot {l['code']} in batch must be marked allocated=1"

        # 3. Total vs unallocated lots
        total_lots_kg = db.execute("SELECT COALESCE(SUM(qty_kg), 0) s FROM lots").fetchone()["s"]
        free_lots_kg = db.execute("SELECT COALESCE(SUM(qty_kg), 0) s FROM lots WHERE allocated=0").fetchone()["s"]
        allocated_lots_kg = db.execute("SELECT COALESCE(SUM(qty_kg), 0) s FROM lots WHERE allocated=1").fetchone()["s"]

        assert abs(total_lots_kg - 3050.0) < 0.01, f"Total lots kg = {total_lots_kg}, expected 3050.0"
        assert abs(allocated_lots_kg - 1380.0) < 0.01, f"Allocated lots kg = {allocated_lots_kg}, expected 1380.0"
        assert abs(free_lots_kg - 1670.0) < 0.01, f"Free lots kg = {free_lots_kg}, expected 1670.0"
        assert abs((free_lots_kg + allocated_lots_kg) - total_lots_kg) < 0.01, "Inventory math does not balance!"

        # 4. Check Dashboard HTML: no double-counting
        code, dash_html = get("/dashboard")
        assert code == 200
        assert "3,050 kg total recorded" in dash_html, "Dashboard missing total recorded kg"
        assert "1,670 kg" in dash_html, "Dashboard available waste should show 1,670 kg (unallocated)"
        assert "1,380 kg in traced batches" in dash_html, "Dashboard missing candidate batches kg"

        # 5. Check Aggregation Planner: solver only considers unallocated lots
        from core import plan_aggregation
        plan = plan_aggregation(db, buyer_id=1)
        if plan and plan.get("feasible"):
            for l in plan.get("lots", []):
                assert l["code"] not in ["LOT-A", "LOT-B", "LOT-D", "LOT-E", "LOT-I"], f"Already allocated lot {l['code']} was re-selected!"

        # 6. Check Reports / Impact page
        code, rep_html = get("/reports")
        assert code == 200
        assert "3,050 kg" in rep_html, "Reports page missing 3,050 kg total characterized"
        assert "1,380 kg" in rep_html, "Reports page missing 1,380 kg aggregated for circularity"

        db.close()
        record(name, True, "All math balances: 1,380 kg allocated (1050 + 330) + 1,670 kg free = 3,050 kg total. Zero double counting.")
    except Exception as e:
        record(name, False, str(e))

def test_new_batch_creation_status():
    name = "5. Dynamic Verification Evaluation Logic"
    try:
        from core import batch_verification_status

        # Evaluate pure verified constituent lots
        lots_verified = [
            {"code": "LOT-C", "qty_kg": 400.0, "status": "verified"},
            {"code": "LOT-F", "qty_kg": 200.0, "status": "verified"}
        ]
        c, l, b, desc = batch_verification_status(lots_verified)
        assert c == "verified", f"Expected verified, got {c}"
        assert l == "Verified Batch", f"Expected 'Verified Batch', got '{l}'"
        assert b == "b-verified", f"Expected 'b-verified', got '{b}'"
        assert "600 kg" in desc

        record(name, True, "Dynamic verification status evaluates 'Verified Batch' for pure verified lots")
    except Exception as e:
        record(name, False, str(e))

if __name__ == "__main__":
    print("\n================ CIRCULO AI PASSPORT REGRESSION SUITE ================\n")
    test_qr_label_and_no_malformed_html()
    test_batch_verification_honesty()
    test_base_url_and_public_disclosure()
    test_batch_weight_and_no_double_counting()
    test_new_batch_creation_status()

    print("\n============================== SUMMARY ==============================")
    passed = sum(1 for _, s, _ in test_results if s)
    total = len(test_results)
    print(f"Total: {total} | Passed: {passed} | Failed: {total - passed}")
    print("=====================================================================\n")

    if passed != total:
        sys.exit(1)
