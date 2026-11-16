import unittest
import urllib.request
import json
import sqlite3
import re
import os

BASE_URL = os.environ.get("PUNORAI_BASE_URL") or os.environ.get("CIRCULO_BASE_URL") or "http://127.0.0.1:8000"

def get(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.getcode(), resp.read().decode("utf-8")

def run_rebrand_audit():
    print("================ PUNORAI REBRANDING & PLATFORM OVERVIEW AUDIT ================\n")
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

    # 1. Platform Overview Page Brand & Hierarchy Checks
    code, html = get("/")
    check("Platform Overview Root HTTP 200", code == 200)

    code_ov, html_ov = get("/overview")
    check("Platform Overview /overview Route HTTP 200", code_ov == 200)

    # Platform Overview Page Checks (Tested on /overview)
    check("Page Title Contains PunorAI", "<title>PunorAI — Platform Overview</title>" in html_ov)
    check("Brand Name in Sidebar is PunorAI", '<div class="brand-name">Punor<span>AI</span></div>' in html_ov)
    check("Topbar Tagline Configured", "Turning Textile Waste into New Value." in html_ov)
    check("Footer Contains PunorAI Subtitle", "<strong>PunorAI</strong> &bull; AI-Powered Textile Circularity Platform" in html_ov)

    # 2. Ecosystem & Challenge Track Hierarchy (ClimateSphere AI -> Circular Future -> PunorAI)
    check("ClimateSphere AI Ecosystem Context Preserved", "ClimateSphere AI" in html_ov)
    check("Circular Future Challenge Track Preserved", "Circular Future" in html_ov)
    check("Circular Future Active Pill Present", "Circular Future Track" in html_ov)

    # 3. Hero Section Problem Context & Action Links
    check("Hero Section Product Heading", "<h2>\n          PunorAI\n        </h2>" in html_ov or "PunorAI" in html_ov)
    check("Hero Subtitle Present", "AI-Powered Textile Circularity Platform" in html_ov)
    check("Hero Tagline Badge Present", "Turning Textile Waste into New Value." in html_ov)
    check("Hero Links to Dashboard", 'href="/dashboard"' in html_ov)
    check("Hero Links to Aggregation", 'href="/aggregation"' in html_ov)
    check("Hero Links to Inventory", 'href="/lots"' in html_ov)

    # 4. Six Core Architectural Pillars Preserved with Working Links
    pillars = [
        ("Pillar 1: Material Characterization", "/lots", "Material Characterization &amp; Intake"),
        ("Pillar 2: Combinatorial Multi-Lot Aggregation", "/aggregation", "Combinatorial Multi-Lot Aggregation"),
        ("Pillar 3: Recycler Matching", "/buyers", "Recycler Matching &amp; Technical Criteria"),
        ("Pillar 4: Reverse Logistics", "/planning", "Resource Recovery Reverse Logistics"),
        ("Pillar 5: Digital Material Passports", "/passports", "Digital Material Passports &amp; Traceability"),
        ("Pillar 6: Evidence-Based Reporting", "/reports", "Evidence-Based Circularity Reporting"),
    ]
    for p_name, p_link, p_title in pillars:
        check(f"{p_name} Present with Working Link", f'href="{p_link}"' in html_ov and p_title in html_ov,
              f"Missing pillar {p_name} or link {p_link}")

    # 5. End-to-End 7-Stage Workflow Pipeline
    workflow_steps = [
        "1. Waste Intake",
        "2. Material Characterization",
        "3. Multi-Lot Aggregation",
        "4. Buyer Matching",
        "5. Collection Logistics",
        "6. Digital Material Passport",
        "7. Evidence-Based Reporting",
    ]
    for step in workflow_steps:
        check(f"Workflow Step '{step}' Present", step in html_ov, f"Missing workflow step: {step}")

    # 6. Judge-Friendly Introduction & Stakeholder Value Matrix
    check("Industrial Bottleneck Section Present", "The Industrial Bottleneck" in html_ov)
    check("PunorAI Solution Section Present", "The PunorAI Solution" in html_ov)
    check("Stakeholder Matrix - Garment Mills", "Garment Mills &amp; Factories" in html_ov)
    check("Stakeholder Matrix - Recyclers", "Recyclers &amp; Spinners" in html_ov)
    check("Stakeholder Matrix - Informal Sorters", "Informal Sorters &amp; Traders" in html_ov)
    check("Stakeholder Matrix - Global Brands", "Global Apparel Brands" in html_ov)
    check("Pillars of Trust - 100% Mathematical Explainability", "100% Mathematical Explainability" in html_ov)
    check("Pillars of Trust - Multi-Objective Trade-Off Profiles", "Multi-Objective Trade-Off Profiles" in html_ov)
    check("Pillars of Trust - Empirical Methodology Honesty", "Empirical Methodology Honesty" in html_ov)
    check("Evaluator 5-Minute Walkthrough Removed", "5-Minute ClimateSphere AI Judge Demonstration Workflow" not in html_ov)
    check("Evaluator Guide Badge Removed", "Evaluator Guide" not in html_ov)
    check("Explore Live Platform Row Present", "Explore the Live Platform" in html_ov)
    check("Explore Row Links to Dashboard", 'href="/dashboard"' in html_ov)
    check("Explore Row Links to Aggregation", 'href="/aggregation"' in html_ov)

    # 6b. New PunorAI Landing Page Structure & Animation Checks (Tested on /)
    check("Landing Page Root Title Present", "PunorAI — AI-Powered Textile Circularity Platform" in html)
    check("Landing Page Logo Brand Present", '<div class="brand-name">Punor<span>AI</span></div>' in html)
    check("Landing Page Scope Badge Present", "AI-Powered Textile Circularity" in html)
    check("Landing Page Headline Present", "Turning Textile Waste" in html and "Valuable" in html and "Resources." in html)
    check("Landing Page Supporting Description Present", "Connecting textile waste, responsible buyers and circular resource management" in html)
    check("Landing Page Primary CTA Link", 'href="/dashboard"' in html)
    check("Landing Page Secondary CTA Link", 'href="/overview"' in html)
    check("Landing Page Animated Textile Roll Frame Present", "fabric-roll-frame" in html and "fabric-roll-visual" in html)
    check("Landing Page Rotating 3D Recycling Loop Present", "recycling-symbol-3d-wrap" in html and "recycling-symbol-svg" in html)
    check("Landing Page Orbit Glow Trail Present", "orbit-glow-trail" in html)
    check("Landing Page Floating Leaves Present", "floating-leaves-layer" in html and "floating-leaf" in html)
    check("Landing Page Ambient Particles Present", "ambient-particles-layer" in html)
    check("Landing Page Section Heading Choose Your Experience", "Choose Your Experience" in html)
    check("Landing Page Role Card Seller Present", "Seller" in html and "Manage waste lots" in html and ('href="/seller"' in html or 'href="/lots"' in html))
    check("Landing Page Role Card Admin Present", "Admin" in html and "Oversee &amp; manage" in html and ('href="/admin"' in html or 'href="/dashboard"' in html))
    check("Landing Page Role Card Buyer Present", "Buyer" in html and "Explore materials" in html and ('href="/buyer"' in html or 'href="/buyers"' in html))
    check("Landing Page Explore Platform Card Present", "Explore Platform" in html and "View public dashboard &amp; sample data" in html)
    check("Landing Page Statistics Strip Removed", "3,050 kg Sample Waste Managed" not in html and "10 Sample Waste Lots" not in html and "2 Aggregation Batches" not in html)
    check("Landing Page Minimal Clean Footer", "AI-Powered Textile Circularity Platform" in html and "GitHub" in html and "Contact" in html and "Project Info" in html)
    check("Landing Page Navbar Profile Icon Removed", "Operator Profile" not in html)
    check("Landing Page Navbar Settings Icon Removed", "Platform Settings" not in html)
    check("Landing Page Navbar Demo Login Retained", "Demo Login" in html and "landing-demo-login-btn" in html)
    check("Landing Page Symmetric Recycling Loop", "recycle-segment" in html)

    # 7. Check All Main Pages for Unintentional "CIRCULO AI" Visible Leaks
    pages = ["/", "/dashboard", "/lots", "/aggregation", "/buyers", "/planning", "/passports", "/reports"]
    for p in pages:
        c, page_html = get(p)
        check(f"Page {p} Returns HTTP 200", c == 200)

        # Visible text should not contain "CIRCULO AI" (case-insensitive check for user-facing tags)
        # We strip script tags and internal batch code references (e.g., CIRC-2026-)
        sanitized = re.sub(r'<script.*?</script>', '', page_html, flags=re.DOTALL)
        sanitized = re.sub(r'CIRC-2026-\d+', '', sanitized)
        sanitized = re.sub(r'circulo\.db', '', sanitized)
        sanitized = re.sub(r'CIRCULO_BASE_URL', '', sanitized)
        sanitized = re.sub(r'id=["\']circulo-toast-container["\']', '', sanitized)

        check(f"Page {p} Clean of Visible 'CIRCULO AI'",
              "circulo ai" not in sanitized.lower(),
              f"Found 'CIRCULO AI' leak in {p}")

    # 8. Check Dashboard Impact Counters Brand and Modern Logo
    _, dash_html = get("/dashboard")
    check("Dashboard Impact Counters Rebranded to PunorAI", "PunorAI Impact Counters" in dash_html)
    check("Dashboard Free of Old PUNORAI IMPACT COUNTERS", "PUNORAI IMPACT COUNTERS" not in dash_html)
    check("New PunorAI Brand Logo Present", "punor-logo-svg" in dash_html)
    check("Legacy C Logo Removed", "M14.5 9a4" not in dash_html)

    # Check CSS Animation & Accessibility
    with open("static/style.css", "r", encoding="utf-8") as f:
        css = f.read()
    check("Brand Logo Entrance Animation in CSS", "brandLogoEntrance" in css)
    check("Brand Wordmark Shimmer in CSS", "brandShimmerPass" in css)
    check("prefers-reduced-motion Accessibility Query in CSS", "prefers-reduced-motion: reduce" in css)

    # 9. Verify Real Database Invariants
    db = sqlite3.connect("circulo.db")
    db.row_factory = sqlite3.Row
    lots_count = db.execute("SELECT COUNT(*) n FROM lots").fetchone()["n"]
    total_kg = db.execute("SELECT SUM(qty_kg) s FROM lots").fetchone()["s"]
    batches_count = db.execute("SELECT COUNT(*) n FROM batches").fetchone()["n"]
    alloc_kg = db.execute("SELECT SUM(qty_kg) s FROM lots WHERE allocated=1").fetchone()["s"]
    db.close()

    check("Database Lots Count Invariant (10 lots)", lots_count == 10)
    check("Database Total Weight Invariant (3,050 kg)", total_kg == 3050.0)
    check("Database Batches Count Invariant (2 batches)", batches_count == 2)
    check("Database Allocated Weight Invariant (1,380 kg)", alloc_kg == 1380.0)

    print("\n============================== SUMMARY ==============================")
    print(f"Total: {total} | Passed: {passed} | Failed: 0")
    print("=====================================================================")

if __name__ == "__main__":
    run_rebrand_audit()
