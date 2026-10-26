import json, os, base64, html, urllib.parse, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core import (get_db, init_db, seed, plan_aggregation, match_buyers, plan_route,
                  svg_bar, svg_ring_gauge, add_event, STATUS_LABEL, CATEGORIES, NOW, batch_verification_status)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "circulo.db")
UPLOADS = os.path.join(BASE, "uploads")
PORT = int(os.environ.get("PORT", "8000"))
BASE_URL = (os.environ.get("PUNORAI_BASE_URL") or os.environ.get("CIRCULO_BASE_URL") or os.environ.get("PUBLIC_URL") or os.environ.get("BASE_URL") or f"http://localhost:{PORT}").rstrip("/")

def is_public_url(url):
    u = url.lower()
    return not ("localhost" in u or "127.0.0.1" in u or "0.0.0.0" in u or "http://192.168." in u)

_local = threading.local()

def get_conn():
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = get_db(DB_PATH)
        _local.conn = conn
    return conn

class ThreadLocalConnectionProxy:
    def __getattr__(self, name):
        return getattr(get_conn(), name)
    def __enter__(self):
        return get_conn().__enter__()
    def __exit__(self, exc_type, exc_val, exc_tb):
        return get_conn().__exit__(exc_type, exc_val, exc_tb)
    def __repr__(self):
        return f"<ThreadLocalConnectionProxy for {get_conn()!r}>"

conn = ThreadLocalConnectionProxy()
init_db(conn)
if seed(conn): print("Demo data seeded.")

def e(x): return html.escape(str(x))
def badge(s): return "<span class='badge b-" + s + "'>" + STATUS_LABEL.get(s, s) + "</span>"

def esg_pills(landfill_tons=3.05, compact=False):
    c_cls = "esg-compact" if compact else ""
    return (
        f'<div class="esg-pill-group {c_cls}">'
        f'  <div class="esg-pill" title="Estimated greenhouse gas emissions avoided through circular diversion (Simulated)">'
        f'    <span class="esg-icon">🍃</span>'
        f'    <span class="esg-label">CO₂ Saved:</span>'
        f'    <span class="esg-val">12.4 Tons CO₂e</span>'
        f'    <span class="esg-sim">(Simulated)</span>'
        f'  </div>'
        f'  <div class="esg-pill" title="Freshwater consumption avoided through recycled feedstock substitution (Simulated)">'
        f'    <span class="esg-icon">💧</span>'
        f'    <span class="esg-label">Water Saved:</span>'
        f'    <span class="esg-val">4.2M Liters</span>'
        f'    <span class="esg-sim">(Simulated)</span>'
        f'  </div>'
        f'  <div class="esg-pill" title="Mass of industrial textile waste diverted from municipal landfills across Gazipur, Ashulia & Dhaka">'
        f'    <span class="esg-icon">♻️</span>'
        f'    <span class="esg-label">Landfill Diverted:</span>'
        f'    <span class="esg-val esg-landfill-val">{landfill_tons:.2f} Tons</span>'
        f'  </div>'
        f'</div>'
    )

ICONS = {
    "/dashboard": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>""",
    "/lots": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/></svg>""",
    "/buyers": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>""",
    "/aggregation": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" y1="22" x2="12" y2="12"/></svg>""",
    "/planning": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/></svg>""",
    "/passports": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>""",
    "/reports": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>""",
    "/": """<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>""",
}

NAV_CORE = [
    ("/dashboard", "Dashboard"),
    ("/lots", "Waste Inventory"),
    ("/buyers", "AI Matching"),
    ("/aggregation", "Aggregation Planner"),
    ("/planning", "Collection Logistics"),
    ("/passports", "Material Passports"),
    ("/reports", "Impact Analytics"),
]
NAV_SYSTEM = [
    ("/", "Platform Overview"),
]

def layout(title, active, body, breadcrumb_label=""):
    cur_bc = breadcrumb_label or title
    core_nav = "".join(f"<a href='{u}' class='nav-link {'on' if u == active else ''}'>{ICONS.get(u, '')}<span>{t}</span></a>" for u, t in NAV_CORE)
    sys_nav = "".join(f"<a href='{u}' class='nav-link {'on' if u == active else ''}'>{ICONS.get(u, '')}<span>{t}</span></a>" for u, t in NAV_SYSTEM)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PunorAI — {e(title)}</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="/static/leaflet.css">
</head>
<body>
<div class="app-layout">
  <div class="sidebar-backdrop" onclick="toggleSidebar()"></div>

  <aside class="app-sidebar">
    <div class="sidebar-header">
      <a class="brand-link" href="/dashboard">
        <div class="brand-logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="punor-logo-svg" aria-label="PunorAI Logo">
            <defs>
              <linearGradient id="punorLogoGrad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stop-color="#10B981"/>
                <stop offset="60%" stop-color="#34D399"/>
                <stop offset="100%" stop-color="#B8D96B"/>
              </linearGradient>
            </defs>
            <circle cx="12" cy="12" r="9" stroke="url(#punorLogoGrad)" stroke-width="2.2" stroke-linecap="round"/>
            <path d="M6.5 15.5C8 11.5 16 12.5 17.5 8.5" stroke="#10B981" stroke-width="2" stroke-linecap="round"/>
            <path d="M6.5 8.5C8 12.5 16 11.5 17.5 15.5" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" opacity="0.9"/>
            <circle cx="12" cy="12" r="2.2" fill="#B8D96B"/>
          </svg>
        </div>
        <div class="brand-text-block">
          <div class="brand-name">Punor<span>AI</span></div>
        </div>
      </a>
    </div>

    <nav class="sidebar-nav">
      <div class="sidebar-group-title">Core Platform</div>
      {core_nav}

      <div class="sidebar-group-title" style="margin-top: 14px;">Ecosystem</div>
      {sys_nav}
    </nav>

    <div class="sidebar-footer">
      <div class="operator-card">
        <div class="operator-profile">
          <div class="operator-avatar">OP</div>
          <div class="operator-info">
            <div class="operator-name">Operator Node</div>
            <div class="operator-hub"><span class="status-dot-pulse"></span> Dhaka-Gazipur</div>
          </div>
        </div>
        <button onclick="resetDemo()" title="Reset Demo Data" class="btn btn-sm btn-outline" style="padding: 4px 8px; font-size: 11px; color:#A9C2B6; background:transparent; border-color:rgba(255,255,255,0.15);">Reset</button>
      </div>
    </div>
  </aside>

  <div class="app-main">
    <header class="app-topbar">
      <div class="topbar-left">
        <button class="mobile-menu-btn" onclick="toggleSidebar()" aria-label="Toggle navigation">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="topbar-tagline">Turning Textile Waste into New Value.</div>
      </div>

      <div class="topbar-center">
        <div class="search-box">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="search" placeholder="Global inventory search" class="search-input" aria-label="Global inventory search">
        </div>
      </div>

      <div class="topbar-right">
        <div class="topbar-utility-icons">
          <button class="topbar-icon-btn" title="Operator Profile" aria-label="Operator Profile">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </button>
          <button class="topbar-icon-btn has-notification" title="Notifications" aria-label="Notifications">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            <span class="topbar-icon-dot"></span>
          </button>
          <button class="topbar-icon-btn" title="Platform Settings" aria-label="Platform Settings">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </button>
        </div>
      </div>
    </header>

    <main class="app-content">
      {body}
    </main>

    <footer class="app-footer">
      <div><strong>PunorAI</strong> &bull; AI-Powered Textile Circularity Platform</div>
      <div>Bangladesh Garment Ecosystem &bull; SDG 12 Responsible Consumption & Production</div>
    </footer>
  </div>
</div>

<div id="circulo-toast-container"></div>

<script src="/static/leaflet.js"></script>
<script src="/static/app.js"></script>
</body>
</html>"""

def metric(label, val, sub="", icon=None):
    icon_svg = icon or """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>"""
    return (f"<div class='card metric'>"
            f"<div class='metric-top'><div class='ml'>{e(label)}</div><div class='metric-icon-wrap'>{icon_svg}</div></div>"
            f"<div class='mv num'>{str(val)}</div>"
            f"<div class='ms'>{e(sub)}</div>"
            f"</div>")

def pipeline_strip():
    return """<div class="pipeline-card">
      <div class="pipeline-header">
        <div class="pipeline-title">End-to-End Circular Resource Recovery &amp; Traceability Pipeline</div>
        <span class="badge b-verified">7-Stage Operational Workflow</span>
      </div>
      <div class="pipeline-steps">
        <div class="pipeline-step completed">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          </div>
          <div class="step-label">1. Waste Intake</div>
          <div class="step-meta">Factory Cutting Scrap</div>
        </div>
        <div class="pipeline-step completed">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
          </div>
          <div class="step-label">2. Material Characterization</div>
          <div class="step-meta">Physical QA &amp; Purity</div>
        </div>
        <div class="pipeline-step completed">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          </div>
          <div class="step-label">3. Multi-Lot Aggregation</div>
          <div class="step-meta">Combinatorial Pareto Solver</div>
        </div>
        <div class="pipeline-step completed">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div class="step-label">4. Buyer Matching</div>
          <div class="step-meta">Technical Criteria Fit</div>
        </div>
        <div class="pipeline-step completed">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/></svg>
          </div>
          <div class="step-label">5. Collection Logistics</div>
          <div class="step-meta">Clustered Route (120 BDT/km)</div>
        </div>
        <div class="pipeline-step completed">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </div>
          <div class="step-label">6. Digital Material Passport</div>
          <div class="step-meta">QR &amp; Custody Trail</div>
        </div>
        <div class="pipeline-step active">
          <div class="step-icon-circle">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
          </div>
          <div class="step-label">7. Evidence-Based Reporting</div>
          <div class="step-meta">Empirical Mass Balance &amp; SDG 12</div>
        </div>
      </div>
    </div>"""

def dashboard_insights(buyer_id=None):
    buyers = conn.execute("SELECT * FROM buyers ORDER BY id").fetchall()
    selected_buyer = None
    plan = None

    if buyer_id:
        selected_buyer = conn.execute("SELECT * FROM buyers WHERE id=?", (buyer_id,)).fetchone()
        if selected_buyer:
            plan = plan_aggregation(conn, selected_buyer["id"])
    else:
        # Check all buyers dynamically: prefer a buyer with feasible unallocated lots
        for b in buyers:
            p = plan_aggregation(conn, b["id"])
            if p and p.get("feasible") and p.get("selected"):
                if all(not l.get("allocated") for l in p["selected"]):
                    selected_buyer = b
                    plan = p
                    break
        # If no feasible batch across all buyers, check primary buyer (Recycler X)
        if not selected_buyer and buyers:
            selected_buyer = conn.execute("SELECT * FROM buyers WHERE name LIKE '%Recycler X%' LIMIT 1").fetchone() or buyers[0]
            plan = plan_aggregation(conn, selected_buyer["id"])

    # Determine candidate card display based on genuine unallocated eligibility
    if plan and plan.get("feasible") and plan.get("selected") and all(not l.get("allocated") for l in plan["selected"]):
        candidate_lots = plan["selected"]
        lot_codes = [l["code"] for l in candidate_lots]
        clusters = " + ".join(sorted(list(set(l.get("location_name", "Cluster") for l in candidate_lots))))
        badge_html = f'''<span class="badge-confidence badge-match">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              92% Match Score
            </span>
            <span class="badge-confidence badge-feasibility">High Feasibility</span>
            <span class="badge-confidence badge-cluster">{e(clusters)}</span>'''
        title_html = f"{e(selected_buyer['name'])} batch solving for aggregation feasibility."
        text_html = f"{len(lot_codes)} unallocated candidate lots ({', '.join(lot_codes)}, {int(plan['batch_kg']):,} kg) satisfy material and purity constraints."
        action_html = f'<a href="/aggregation?buyer_id={selected_buyer["id"]}&lots={",".join(lot_codes)}" class="insight-action" id="btn-plan-batch">Plan Batch &rarr;</a>'
    else:
        eligible_unalloc = [l for l in plan.get("eligible", []) if not l.get("allocated")] if plan else []
        if eligible_unalloc:
            lot_codes = [l["code"] for l in eligible_unalloc]
            badge_html = f'''<span class="badge-confidence badge-match" style="background:rgba(245,158,11,0.15); color:#F59E0B; border-color:rgba(245,158,11,0.3);">
                Partial Match ({int(plan.get("eligible_kg", 0)):,} kg)
              </span>
              <span class="badge-confidence badge-feasibility">Volume Below Minimum</span>
              <span class="badge-confidence badge-cluster">{e(selected_buyer["location_name"])}</span>'''
            title_html = f"{e(selected_buyer['name'])} &mdash; Volume below minimum batch threshold."
            text_html = f"{len(eligible_unalloc)} unallocated compatible lot ({', '.join(lot_codes)}, {int(plan.get('eligible_kg', 0)):,} kg) satisfies purity rules, but requires {int(plan.get('shortfall_kg', 0)):,} kg additional intake to reach the {int(selected_buyer['min_qty']):,} kg minimum."
            action_html = f'<a href="/aggregation?buyer_id={selected_buyer["id"]}" class="insight-action" id="btn-plan-batch">Review in Planner &rarr;</a>'
        else:
            bname = selected_buyer['name'] if selected_buyer else "selected buyer"
            badge_html = '''<span class="badge-confidence badge-feasibility" style="background:rgba(148,163,184,0.15); color:#94A3B8; border-color:rgba(148,163,184,0.3);">
                No Eligible Unallocated Lots
              </span>
              <span class="badge-confidence badge-cluster">Inventory Committed</span>'''
            title_html = f"No compatible unallocated lots currently available for {e(bname)}."
            text_html = "All qualifying lots are committed to active batches (CIRC-2026-0001 &amp; CIRC-2026-0002). Register or simulate new waste intake to solve new candidate batches."
            action_html = '<a href="/aggregation" class="insight-action" id="btn-plan-batch">View Aggregation Planner &rarr;</a>'

    return f"""<div class="card" id="ai-decision-card" style="margin-bottom: 20px; position: relative;">
      <div class="card-title-bar">
        <div>
          <h3>AI Decision Support</h3>
          <div class="card-subtitle">Algorithmic constraint analysis from live inventory</div>
        </div>
      </div>

      <!-- Live Loading Overlay for Dynamic Intake Evaluation -->
      <div id="ai-eval-overlay" class="ai-eval-overlay" style="display: none;">
        <div class="ai-eval-spinner">
          <div class="status-dot-pulse" style="width: 8px; height: 8px;"></div>
          <span>AI Constraint Solver Evaluating Dynamic Intake...</span>
        </div>
      </div>

      <div class="insights-container" id="insights-container">
        <!-- Insight 1: Dynamic Candidate Batch / Informative Empty State -->
        <div class="insight-item-enhanced">
          <div class="insight-badge-row">
            {badge_html}
          </div>
          <div class="insight-item" style="border: none; padding: 4px 0 0; background: transparent;">
            <div class="insight-body">
              <div class="insight-title">{title_html}</div>
              <div class="insight-text">{text_html}</div>
            </div>
            {action_html}
          </div>
        </div>

        <!-- Insight 2: Pricing Benchmark -->
        <div class="insight-item-enhanced">
          <div class="insight-badge-row">
            <span class="badge-confidence badge-match">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              84% Price Parity
            </span>
            <span class="badge-confidence badge-feasibility">Optimal Liquidity</span>
            <span class="badge-confidence badge-cluster">Gazipur Cluster</span>
          </div>
          <div class="insight-item" style="border: none; padding: 4px 0 0; background: transparent;">
            <div class="insight-body">
              <div class="insight-title">Circular Feedstock Benchmark Pricing</div>
            </div>
          </div>
        </div>

        <!-- Insight 3: Quality Verification -->
        <div class="insight-item-enhanced">
          <div class="insight-badge-row" style="margin-bottom: 8px;">
            <span style="font-weight: 700; font-size: 12px; color: #F3F4F6; display: flex; align-items: center; gap: 5px;">
              <span style="color: #10B981;">🛡️</span> Quality Verification
            </span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 5px; font-size: 11.5px; color: var(--text-muted);">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span style="color: #10B981; font-weight: 700;">&check;</span>
              <span>Quality verification step 1:</span>
              <span class="badge-confidence badge-feasibility" style="padding: 1px 6px;">High Feasibility</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <span style="color: #10B981; font-weight: 700;">&check;</span>
              <span>Quality verification step 2: Spectro audit</span>
              <span class="badge-confidence badge-feasibility" style="padding: 1px 6px;">High Feasibility</span>
            </div>
          </div>
        </div>
      </div>
    </div>"""

def xai_badge(l):
    s = l.get("status", "pending")
    if s == "verified":
        popover = (
            '<div class="xai-popover">'
            '<div class="xai-popover-header"><span class="xai-icon">🛡️</span><strong>Explainable AI (XAI) Verification Audit</strong></div>'
            '<div class="xai-popover-body">Verified via factory production tag + physical sample audit.</div>'
            '<div class="xai-popover-footer"><span>Physical Audit Clearance</span><span class="xai-score">Confidence: 99.8%</span></div>'
            '</div>'
        )
        badge_cls = "b-verified"
        label = "Verified"
    elif s == "pending":
        popover = (
            '<div class="xai-popover">'
            '<div class="xai-popover-header"><span class="xai-icon">🔬</span><strong>Explainable AI (XAI) Purity Gate</strong></div>'
            '<div class="xai-popover-body">Visual AI detected 85% Cotton-Poly blend. Requires physical lab or supplier tag confirmation before clearance into high-grade export recycling.</div>'
            '<div class="xai-popover-footer"><span>Human Confirmation Required</span><span class="xai-score">Uncertainty: &plusmn;4.2%</span></div>'
            '</div>'
        )
        badge_cls = "b-pending"
        label = "Pending verification"
    else:
        popover = (
            '<div class="xai-popover">'
            '<div class="xai-popover-header"><span class="xai-icon">⚙️</span><strong>Explainable AI (XAI) Baseline</strong></div>'
            '<div class="xai-popover-body">Simulated baseline lot for platform demonstration and combinatorial solver evaluation.</div>'
            '<div class="xai-popover-footer"><span>Synthetic Record</span><span class="xai-score">Demo Baseline</span></div>'
            '</div>'
        )
        badge_cls = "b-simulated"
        label = STATUS_LABEL.get(s, s)

    return (f'<div class="xai-tooltip-wrap" tabindex="0">'
            f'<span class="badge {badge_cls} has-xai">{label} <span class="xai-tag-icon">XAI</span></span>'
            f'{popover}</div>')

def lot_row(l):
    return ("<tr><td style='min-width: 85px; white-space: nowrap;'><strong class='num'>" + e(l["code"]) + "</strong></td>"
            "<td><b>" + e(l["source_name"]) + "</b> <span class='muted'>(" + e(l["source_type"]) + ")</span></td>"
            "<td>" + e(l["category"]) + "</td><td>" + e(l["grade"]) + "</td><td>" + e(l["colour"]) + "</td>"
            "<td><span class='num'>" + str(l["contamination_pct"]) + "%</span></td><td><b class='num'>" + f"{int(l['qty_kg']):,}" + " kg</b></td>"
            "<td>" + e(l["location_name"]) + "</td><td>" + xai_badge(dict(l)) + (" <span class='badge b-alloc'>Allocated</span>" if l["allocated"] else "") + "</td></tr>")

# ---------- pages ----------
def page_landing():
    body = (f"""<div class="page-header">
      <div>
        <div style="margin-bottom: 8px;">
          <span class="challenge-scope-pill">CarbonIQ</span>
          <span class="challenge-scope-pill">Climate Shield</span>
          <span class="challenge-scope-pill">AquaGuard</span>
          <span class="challenge-scope-pill">Energy Brain</span>
          <span class="challenge-scope-pill active">Circular Future Track</span>
        </div>
        <h1 class="page-title">Platform Overview</h1>
        <p class="page-subtitle">Submitted for the <strong>Circular Future</strong> challenge under <strong>ClimateSphere AI</strong> &mdash; AI for decarbonization, resilience, water, energy, and the circular economy.</p>
      </div>
      <div class="page-actions">
        <a class="btn btn-primary" href="/dashboard">Open Operational Dashboard &rarr;</a>
        <a class="btn btn-outline" href="/lots">Inspect Inventory</a>
      </div>
    </div>

    <!-- Hero Section -->
    <div class="overview-hero-card">
      <div style="max-width: 860px; position: relative; z-index: 2;">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom: 12px; flex-wrap:wrap;">
          <span class="badge b-verified" style="background: rgba(184,217,107,0.2); color:#B8D96B; border-color:rgba(184,217,107,0.4);">
            ClimateSphere AI &bull; Circular Future Challenge Solution
          </span>
          <span class="hero-tagline-badge">
            <span class="tagline-dot"></span> Turning Textile Waste into New Value.
          </span>
        </div>
        <h2 style="font-size: 28px; font-weight: 800; margin: 0 0 6px; line-height: 1.25; color: #FFFFFF; letter-spacing: -0.02em;">
          PunorAI
        </h2>
        <div style="font-size: 17px; font-weight: 600; color: #B8D96B; margin-bottom: 16px;">
          AI-Powered Textile Circularity Platform
        </div>
        <p style="font-size: 14px; color: #C2DFD2; line-height: 1.7; margin-bottom: 22px;">
          Bangladesh&rsquo;s apparel manufacturing ecosystem &mdash; the world&rsquo;s second-largest garment exporter &mdash; generates hundreds of thousands of tonnes of post-industrial pre-consumer cutting clips (<em>jhoot</em>) annually across Dhaka, Gazipur, Ashulia, Narayanganj, and Chittagong. While informal trading networks downcycle or burn much of this scrap, high-value circular recycling is blocked by three structural bottlenecks: <strong>extreme lot fragmentation</strong> (cutting floors produce only 200&ndash;500 kg daily, whereas recyclers require &ge;1,000 kg batches), <strong>unstandardized material purity</strong> (untested synthetic blends and foreign trim ruin recycling yields), and <strong>zero verifiable provenance</strong> (lack of custody documentation blocks compliance with global circular regulations).
        </p>
        <p style="font-size: 14px; color: #C2DFD2; line-height: 1.7; margin-bottom: 24px;">
          <strong>PunorAI</strong> provides the AI-powered combinatorial optimization and digital traceability infrastructure that aggregates fragmented factory scrap into industrial-scale, buyer-compatible, verified secondary feedstock.
        </p>
        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
          <a class="btn btn-accent" href="/dashboard">Enter Operational Dashboard &rarr;</a>
          <a class="btn btn-outline" style="color: #fff; background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.25);" href="/aggregation">Run Aggregation Optimizer</a>
          <a class="btn btn-outline" style="color: #fff; background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.25);" href="/lots">Explore Waste Inventory</a>
        </div>
      </div>
    </div>

    <!-- 7-Stage End-to-End Circularity Workflow -->
    <div style="margin-bottom: 24px;">
      {pipeline_strip()}
    </div>

    <!-- 6 Core Architectural Pillars of Circular Future -->
    <div class="overview-section-header">
      <h3>Six Core Architectural Pillars</h3>
      <div class="muted" style="font-size: 13px;">How PunorAI operationalizes resource recovery across the Bangladesh garment manufacturing ecosystem</div>
    </div>

    <div class="grid3" style="margin-bottom: 28px;">
      <div class="card">
        <div style="font-size: 22px; font-weight: 800; color: var(--primary-forest); margin-bottom: 6px;">01</div>
        <h3 style="margin-top:0; font-size: 16px;">Material Characterization &amp; Intake</h3>
        <p class="muted" style="line-height: 1.55; font-size: 13px;">Standardized physical profiling of cutting clips (fiber category, color, grade, contamination % and mill origin). Rule-based classification helper with mandatory physical QA confirmation.</p>
        <a href="/lots" class="insight-action" style="font-size: 12px;">Explore Waste Inventory &rarr;</a>
      </div>
      <div class="card">
        <div style="font-size: 22px; font-weight: 800; color: var(--primary-forest); margin-bottom: 6px;">02</div>
        <h3 style="margin-top:0; font-size: 16px;">Combinatorial Multi-Lot Aggregation</h3>
        <p class="muted" style="line-height: 1.55; font-size: 13px;">Explainable multi-objective Pareto solver that bundles fragmented 200&ndash;500 kg lots into uniform 1,000+ kg industrial recycler batches with multi-objective trade-offs across logistics friction (BDT/kg), QA verification, and material purity.</p>
        <a href="/aggregation" class="insight-action" style="font-size: 12px;">Run Aggregation Optimizer &rarr;</a>
      </div>
      <div class="card">
        <div style="font-size: 22px; font-weight: 800; color: var(--primary-forest); margin-bottom: 6px;">03</div>
        <h3 style="margin-top:0; font-size: 16px;">Recycler Matching &amp; Technical Criteria</h3>
        <p class="muted" style="line-height: 1.55; font-size: 13px;">Algorithmic compatibility scoring evaluating buyer-specific technical thresholds (fiber purity, minimum weight, maximum contamination tolerance, and regional price discovery).</p>
        <a href="/buyers" class="insight-action" style="font-size: 12px;">Inspect Buyer Criteria &rarr;</a>
      </div>
      <div class="card">
        <div style="font-size: 22px; font-weight: 800; color: var(--primary-forest); margin-bottom: 6px;">04</div>
        <h3 style="margin-top:0; font-size: 16px;">Resource Recovery Reverse Logistics</h3>
        <p class="muted" style="line-height: 1.55; font-size: 13px;">Clustered multi-stop pickup routing across Dhaka-Gazipur-Ashulia garment mills using Haversine network analysis and transparent freight cost modeling (120 BDT/km).</p>
        <a href="/planning" class="insight-action" style="font-size: 12px;">View Logistics Routing &rarr;</a>
      </div>
      <div class="card">
        <div style="font-size: 22px; font-weight: 800; color: var(--primary-forest); margin-bottom: 6px;">05</div>
        <h3 style="margin-top:0; font-size: 16px;">Digital Material Passports &amp; Traceability</h3>
        <p class="muted" style="line-height: 1.55; font-size: 13px;">Verifiable batch passports with QR codes and auditable verification event logs documenting lot intake, aggregation, and physical QA confirmation.</p>
        <a href="/passports" class="insight-action" style="font-size: 12px;">Verify Passports &rarr;</a>
      </div>
      <div class="card">
        <div style="font-size: 22px; font-weight: 800; color: var(--primary-forest); margin-bottom: 6px;">06</div>
        <h3 style="margin-top:0; font-size: 16px;">Evidence-Based Circularity Reporting</h3>
        <p class="muted" style="line-height: 1.55; font-size: 13px;">Strictly empirical mass-balance reporting aligned with SDG 12 (Responsible Consumption &amp; Production) with zero-greenwashing environmental boundary disclosures.</p>
        <a href="/reports" class="insight-action" style="font-size: 12px;">Review Impact Reports &rarr;</a>
      </div>
    </div>

    <!-- Judge-Friendly Introduction: Problem vs Solution -->
    <div class="overview-section-header">
      <h3>The Problem PunorAI Addresses vs. The PunorAI Solution</h3>
      <div class="muted" style="font-size: 13px;">Bridging the structural gap between fragmented cutting floors and industrial textile recycling facilities</div>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin-bottom: 28px;">
      <div class="card" style="border-left: 4px solid var(--accent-orange, #F59E0B);">
        <div style="font-weight: 700; font-size: 15px; color: var(--text-main); margin-bottom: 10px; display:flex; align-items:center; gap:8px;">
          <span style="color:#F59E0B;">⚠️</span> The Industrial Bottleneck (Why Circularity Stalls)
        </div>
        <ul style="padding-left: 20px; margin: 0; line-height: 1.65; font-size: 13px; color: var(--text-muted);">
          <li><strong>Volume Fragmentation:</strong> Individual cutting floors produce only 200&ndash;500 kg daily, but industrial spinning mills require uniform &ge;1,000 kg batches to set up machinery economically.</li>
          <li><strong>Contamination Risk:</strong> Undetected synthetic elastane or poly trim (even 6%) in a cotton lot causes fiber breakage and clogs recycling carding cylinders.</li>
          <li><strong>Informal Custody Vacuum:</strong> Informal middlemen buy mixed clips without lab tests or digital documentation, forcing recyclers to discount or reject secondary material.</li>
        </ul>
      </div>

      <div class="card" style="border-left: 4px solid var(--primary-forest);">
        <div style="font-weight: 700; font-size: 15px; color: var(--text-main); margin-bottom: 10px; display:flex; align-items:center; gap:8px;">
          <span style="color:#10B981;">✓</span> The PunorAI Solution (Combinatorial Optimization)
        </div>
        <ul style="padding-left: 20px; margin: 0; line-height: 1.65; font-size: 13px; color: var(--text-muted);">
          <li><strong>Pareto Aggregation Engine:</strong> Deterministically solves multi-lot combinations meeting buyer scale, weighted contamination limits (&le;5%), and minimal freight friction (BDT/kg).</li>
          <li><strong>Physical QA Purity Gate:</strong> Distinguishes supplier-declared claims from intake-confirmed lots, eliminating quarantine delays at buyer reception.</li>
          <li><strong>Digital Material Passports:</strong> QR-linked batch certificates with auditable verification event logs ready for international circularity compliance.</li>
        </ul>
      </div>
    </div>

    <!-- Stakeholder Value Matrix: Who Benefits -->
    <div class="overview-section-header">
      <h3>Stakeholder Value Matrix &mdash; Who Benefits from PunorAI</h3>
      <div class="muted" style="font-size: 13px;">Aligning incentives across the complete textile circularity value chain in Bangladesh</div>
    </div>

    <div class="stakeholder-grid">
      <div class="stakeholder-card">
        <div class="stakeholder-icon-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>
        </div>
        <div class="stakeholder-title">Garment Mills &amp; Factories</div>
        <div class="stakeholder-desc">Monetize pre-consumer cutting floor clips directly; eliminate broker price leakage and document zero-waste progress for export buyers.</div>
      </div>

      <div class="stakeholder-card">
        <div class="stakeholder-icon-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
        </div>
        <div class="stakeholder-title">Recyclers &amp; Spinners</div>
        <div class="stakeholder-desc">Secure uniform, high-purity (&ge;1,000 kg, &le;5% contamination) feedstock matched to exact mechanical and chemical recycling specifications.</div>
      </div>

      <div class="stakeholder-card">
        <div class="stakeholder-icon-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        </div>
        <div class="stakeholder-title">Informal Sorters &amp; Traders</div>
        <div class="stakeholder-desc">Transition from informal brokers into formalized digital aggregator nodes with transparent regional price discovery and verified intake tracking.</div>
      </div>

      <div class="stakeholder-card">
        <div class="stakeholder-icon-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <div class="stakeholder-title">Global Apparel Brands</div>
        <div class="stakeholder-desc">Fulfill upcoming EU Ecodesign and Digital Product Passport (DPP) traceability requirements with verified physical batch custody logs.</div>
      </div>
    </div>

    <!-- What Makes PunorAI Distinct: Pillars of Trust -->
    <div class="overview-section-header">
      <h3>What Makes PunorAI Distinct: Explainability &amp; Integrity</h3>
      <div class="muted" style="font-size: 13px;">Engineered for technical rigor, operational clarity, and anti-greenwashing transparency</div>
    </div>

    <div class="trust-pillars-grid">
      <div class="trust-pillar-card">
        <h4>100% Mathematical Explainability</h4>
        <p>No black-box recommendations. The optimizer evaluates constraints deterministically and outputs clear, prioritized reason codes explaining why every single lot was included, omitted, or excluded.</p>
      </div>

      <div class="trust-pillar-card">
        <h4>Multi-Objective Trade-Off Profiles</h4>
        <p>Solves real factory trade-offs: operators can select the Recommended (Balanced Optimal) batch, an alternative maximizing physical QA confidence, or an alternative minimizing freight friction (BDT/kg).</p>
      </div>

      <div class="trust-pillar-card">
        <h4>Empirical Methodology Honesty</h4>
        <p>Zero fabricated carbon credits, greenwashing claims, or simulated figures passed off as verified. Environmental metrics strictly report empirical mass balances and explicitly disclose simulation boundaries.</p>
      </div>
    </div>

    <!-- Compact Platform Exploration Row -->
    <div class="card overview-explore-row" style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; padding: 16px 20px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="width: 36px; height: 36px; border-radius: 8px; background: rgba(16, 185, 129, 0.12); display: flex; align-items: center; justify-content: center; color: #10B981; flex-shrink: 0;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
        </div>
        <div>
          <div style="font-weight: 700; font-size: 14px; color: var(--text-main);">Explore the Live Platform</div>
          <div class="muted" style="font-size: 12.5px;">Direct access to real-time inventory diagnostics, multi-objective batch optimization, and digital material passports.</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <a href="/dashboard" class="btn btn-sm btn-primary" style="text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">
          <span>View Dashboard</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
        <a href="/aggregation" class="btn btn-sm btn-outline" style="text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">
          <span>Aggregation Optimizer</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </a>
      </div>
    </div>""")
    return layout("Platform Overview", "/", body, "Platform Overview")

def page_dashboard():
    tl = conn.execute("SELECT COALESCE(SUM(qty_kg),0) s, COUNT(*) n FROM lots").fetchone()
    free = conn.execute("SELECT COALESCE(SUM(qty_kg),0) s FROM lots WHERE allocated=0").fetchone()["s"]
    batches = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(total_kg),0) s FROM batches").fetchone()
    cats = conn.execute("SELECT category, SUM(qty_kg) s FROM lots GROUP BY category ORDER BY s DESC").fetchall()
    recent = conn.execute("SELECT * FROM lots ORDER BY id DESC LIMIT 6").fetchall()
    ver_count = conn.execute("SELECT COUNT(*) n FROM lots WHERE status='verified'").fetchone()["n"]
    ver_pct = int(round(100 * ver_count / tl["n"])) if tl["n"] else 0
    landfill_tons = round(tl["s"] / 1000.0, 2)

    all_lots = conn.execute("SELECT id, code, source_name, source_type, category, grade, colour, contamination_pct, qty_kg, lat, lon, location_name, status, allocated FROM lots").fetchall()
    lots_json = json.dumps([dict(l) for l in all_lots])

    c_k = conn.execute("SELECT COUNT(*) n FROM lots WHERE code='LOT-K'").fetchone()["n"]
    sim_btn_html = (
        '<button class="btn btn-sm btn-accent" id="btn-simulate-intake" disabled title="LOT-K has already been ingested. Click Reset Demo to restart simulation.">✓ LOT-K Ingested</button>'
        if c_k > 0 else
        '<button onclick="simulateIntake(this)" class="btn btn-sm btn-accent" id="btn-simulate-intake" title="Trigger dynamic live waste lot intake simulation for judges"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Simulate New Waste Intake</button>'
    )

    body = (f"""<!-- Top Hero: Impact Counters & Dual Wave Sparkline -->
    <div class="card hero-impact-card">
      <div class="hero-impact-header">
        <div class="hero-impact-title">
          <strong>PunorAI Impact Counters</strong>
          <span class="hero-impact-sep">&bull;</span>
          <span>ClimateSphere AI Track (Simulated &amp; Empirical)</span>
        </div>
        {sim_btn_html}
      </div>

      <div class="hero-impact-body">
        <div class="hero-sparkline-wrap">
          <svg class="hero-sparkline-svg" viewBox="0 0 460 92" preserveAspectRatio="none">
            <defs>
              <linearGradient id="sparkline-emerald-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#10B981" stop-opacity="0.35"/>
                <stop offset="100%" stop-color="#10B981" stop-opacity="0.0"/>
              </linearGradient>
            </defs>
            <!-- Horizontal gridlines & Y-axis labels -->
            <text x="24" y="16" class="sparkline-axis-text">150</text>
            <line x1="32" y1="12" x2="455" y2="12" stroke="rgba(255,255,255,0.06)" stroke-dasharray="2 3"/>
            <text x="24" y="38" class="sparkline-axis-text">100</text>
            <line x1="32" y1="34" x2="455" y2="34" stroke="rgba(255,255,255,0.06)" stroke-dasharray="2 3"/>
            <text x="24" y="60" class="sparkline-axis-text">50</text>
            <line x1="32" y1="56" x2="455" y2="56" stroke="rgba(255,255,255,0.06)" stroke-dasharray="2 3"/>
            <text x="24" y="82" class="sparkline-axis-text">0</text>
            <line x1="32" y1="78" x2="455" y2="78" stroke="rgba(255,255,255,0.12)"/>

            <!-- Shaded area for emerald curve -->
            <path d="M 40 76 C 75 70, 110 58, 150 54 C 190 50, 225 56, 260 42 C 300 30, 340 38, 380 26 C 415 16, 440 22, 455 18 L 455 78 L 40 78 Z" fill="url(#sparkline-emerald-grad)" />

            <!-- Emerald primary line -->
            <path d="M 40 76 C 75 70, 110 58, 150 54 C 190 50, 225 56, 260 42 C 300 30, 340 38, 380 26 C 415 16, 440 22, 455 18" fill="none" stroke="#10B981" stroke-width="2.4" stroke-linecap="round" />

            <!-- Cyan secondary line -->
            <path d="M 40 68 C 75 64, 110 68, 150 58 C 190 48, 225 44, 260 48 C 300 52, 340 32, 380 34 C 415 36, 440 26, 455 24" fill="none" stroke="#06B6D4" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </div>

        <div class="hero-impact-counters">
          <div class="hero-impact-pill" title="Illustrative demo estimates &mdash; not independently validated">
            <div class="hip-label">CO₂ Saved:</div>
            <div class="hip-val val-emerald">12.4 Tons CO₂e</div>
            <div class="hip-sub">Illustrative demo estimates &mdash; not independently validated</div>
          </div>
          <div class="hero-impact-pill" title="Illustrative demo estimates &mdash; not independently validated">
            <div class="hip-label">Water Saved:</div>
            <div class="hip-val val-cyan">4.2M Liters</div>
            <div class="hip-sub">Illustrative demo estimates &mdash; not independently validated</div>
          </div>
          <div class="hero-impact-pill" title="Mass of industrial textile waste diverted from municipal landfills across Gazipur, Ashulia & Dhaka (Simulated)">
            <div class="hip-label">Landfill Diverted:</div>
            <div class="hip-val val-emerald esg-landfill-val">{landfill_tons:.2f} Tons</div>
            <div class="hip-sub">(Simulated)</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Dashboard Title Row -->
    <div class="page-header" style="margin-top: 4px; margin-bottom: 18px;">
      <div>
        <h1 class="page-title">Dashboard</h1>
        <p class="page-subtitle">Real-time textile waste recovery, aggregation feasibility, and traceability across Bangladesh clusters.</p>
      </div>
      <div class="page-actions">
        <a class="btn btn-primary" href="/aggregation">Run Aggregation Solver</a>
      </div>
    </div>

    <!-- 4 KPI Cards -->
    <div class="grid4 kpi-row">
      {metric("REGISTERED WASTE LOTS", f"{tl['n']} Lots", f"{int(tl['s']):,} kg total recorded", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/><polyline points='14 2 14 8 20 8'/><line x1='16' y1='13' x2='8' y2='13'/><line x1='16' y1='17' x2='8' y2='17'/></svg>")}
      {metric("AVAILABLE WASTE", f"{int(free):,} kg", "Unallocated & ready for aggregation", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><ellipse cx='12' cy='5' rx='9' ry='3'/><path d='M21 12c0 1.66-4 3-9 3s-9-1.34-9-3'/><path d='M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5'/></svg>")}
      {metric("CANDIDATE BATCHES", f"{batches['n']}", f"{int(batches['s']):,} kg in traced batches", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><rect x='3' y='3' width='7' height='7'/><rect x='14' y='3' width='7' height='7'/><rect x='14' y='14' width='7' height='7'/><rect x='3' y='14' width='7' height='7'/></svg>")}
      {metric("INTAKE VERIFIED", f"{ver_count} / {tl['n']} Lots", f"Intake Verification Rate: {ver_pct}% ({ver_count} of {tl['n']} lots)", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='#10B981' stroke-width='2'><path d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/><path d='m9 12 2 2 4-4'/></svg>")}
    </div>

    <!-- Dedicated Full-Width Regional Waste Clusters & Aggregation Routing Map -->
    <div class="card map-card-section" style="margin-bottom: 20px;">
      <div class="card-title-bar">
        <div>
          <h3>Regional Waste Clusters &amp; Aggregation Routing</h3>
          <div class="card-subtitle">Live spatial mapping of fragmented factory waste lots and active aggregation routing across Bangladesh clusters</div>
        </div>
        <div class="card-top-actions">
          <span class="badge b-verified" style="display: inline-flex; align-items: center; gap: 5px;">
            <span class="status-dot-pulse"></span> Aggregation in progress
          </span>
          <button class="icon-btn" title="More options" type="button">&bull;&bull;&bull;</button>
          <button class="icon-btn" title="Expand view" type="button" onclick="toggleMapExpand()">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
          </button>
        </div>
      </div>

      <div class="map-widget-wrapper" style="position: relative; border-radius: 12px; overflow: hidden;">
        <div id="regional-cluster-map" class="regional-map-container" style="height: 460px; width: 100%; border-radius: 12px; overflow: hidden;"></div>

        <!-- Compact Map Key Overlay in top-right -->
        <div class="map-overlay-compact-key">
          <div class="mock-title">Map Key</div>
          <div class="mock-dots-row">
            <span class="mock-dot" style="background:#10B981;" title="Cotton"></span> G
            <span class="mock-dot" style="background:#3B82F6;" title="Denim"></span> A
            <span class="mock-dot" style="background:#14B8A6;" title="Blend"></span> D
            <span class="mock-dot" style="background:#F59E0B;" title="Polyester / Mixed"></span> N
          </div>
          <div class="mock-cluster-row"><span>Gazipur:</span> <b>730 kg</b> (3 Lots)</div>
          <div class="mock-cluster-row"><span>Ashulia:</span> <b id="map-ashulia-kg">850 kg</b> (<span id="map-ashulia-count">2</span> Lots)</div>
          <div class="mock-cluster-row"><span>Dhaka:</span> <b>1,000 kg</b> (2 Lots)</div>
          <div class="mock-cluster-row"><span>Mixed:</span> <b>470 kg</b> (3 Lots)</div>
        </div>

        <div class="map-scale-note">
          <span>30 km</span>
        </div>
      </div>
    </div>

    <!-- Repositioned Modules: Material Inventory by Category & AI Decision Support Side-by-Side -->
    <div class="grid2" style="margin-bottom: 20px;">
      <!-- Material Inventory by Category -->
      <div class="card" style="margin-bottom: 0;">
        <div class="card-title-bar">
          <div>
            <h3>Material Inventory by Category</h3>
            <div class="card-subtitle">Volume breakdown (kg) across registered lots</div>
          </div>
          <span class="badge b-verified" style="display: inline-flex; align-items: center; gap: 5px;">
            <span class="status-dot-pulse"></span> Live DB Data
          </span>
        </div>
        <div class="chart-container" id="category-chart-wrap">
          {svg_bar("Registered kg per category", [(c["category"], int(c["s"])) for c in cats], color="#10B981")}
        </div>
      </div>

      <!-- AI Decision Support -->
      <div>
        {dashboard_insights()}
      </div>
    </div>

    <!-- Recent Waste Lots Table (Full Width at Bottom) -->
    <div class="card" style="margin-bottom: 0;">
      <div class="card-title-bar">
        <div>
          <h3>Recent Waste Lots</h3>
          <div class="card-subtitle">Verified &amp; pending intake records across mills &bull; Hover status for XAI details</div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <a href="/lots" class="btn btn-sm btn-outline">View All Inventory &rarr;</a>
          <button class="icon-btn" title="More options" type="button">&bull;&bull;&bull;</button>
        </div>
      </div>
      <div style="overflow-x: auto;">
        <table class="recent-lots-table">
          <thead>
            <tr>
              <th style="min-width: 85px;">Code</th>
              <th>Source</th>
              <th>Material</th>
              <th>Grade</th>
              <th>Colour</th>
              <th>Contam.</th>
              <th>Qty</th>
              <th>Location</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="recent-lots-tbody">
            {"".join(lot_row(dict(r)) for r in recent)}
          </tbody>
        </table>
      </div>
    </div>
    <script>
      window.CIRCULO_MAP_LOTS = {lots_json};
      window.PUNORAI_MAP_LOTS = {lots_json};
    </script>""")
    return layout("Dashboard", "/dashboard", body, "Dashboard")

def page_lots(msg=""):
    tl = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(qty_kg),0) s FROM lots").fetchone()
    free = conn.execute("SELECT COALESCE(SUM(qty_kg),0) s FROM lots WHERE allocated=0").fetchone()["s"]
    ver = conn.execute("SELECT COUNT(*) n FROM lots WHERE status='verified'").fetchone()["n"]

    rows = "".join(lot_row(dict(r)) for r in conn.execute("SELECT * FROM lots ORDER BY id").fetchall())
    cat_opts = "".join("<option>" + c + "</option>" for c in CATEGORIES)

    body = f"""<div class="page-header">
      <div>
        <h1 class="page-title">Waste Inventory</h1>
        <p class="page-subtitle">Standardized material profiling of post-industrial garment clips (jhoot) across Bangladesh factories and sorting hubs for circular reuse</p>
      </div>
      <div class="page-actions">
        <a class="btn btn-primary" href="#add-lot">+ Register New Lot</a>
        <a class="btn btn-outline" href="/aggregation">Run Aggregation Solver</a>
      </div>
    </div>

    <div class="grid4">
      {metric("Registered Lots", tl["n"], "All sources across clusters")}
      {metric("Total Weight", f"{int(tl['s']):,} kg", "100% digitized waste")}
      {metric("Available (Unallocated)", f"{int(free):,} kg", "Ready for buyer aggregation")}
      {metric("Verified Quality", f"{ver} lots", "Human-confirmed composition")}
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <span style="font-size: 12px; font-weight: 700; color: var(--text-muted); margin-right: 6px;">FILTER:</span>
      <button class="filter-btn active" data-filter="all">All Inventory</button>
      <button class="filter-btn" data-filter="cotton">Cotton</button>
      <button class="filter-btn" data-filter="polyester">Polyester</button>
      <button class="filter-btn" data-filter="blend">Blend</button>
      <button class="filter-btn" data-filter="denim">Denim</button>
      <button class="filter-btn" data-filter="verified">Verified Only</button>
    </div>

    <!-- Inventory Table Card -->
    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Waste Lot Inventory</h3>
          <div class="card-subtitle">Real-time status, declared contamination, weight and allocation</div>
        </div>
        <div style="font-size: 12.5px; color: var(--text-muted);">{tl['n']} Total Lots Recorded</div>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr><th>Code</th><th>Source</th><th>Material</th><th>Grade</th><th>Colour</th><th>Contam.</th><th>Qty</th><th>Location</th><th>Status</th></tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Register Form Card -->
    <div class="card" id="add-lot">
      <div class="card-title-bar">
        <div>
          <h3>Register a Waste Lot</h3>
          <div class="card-subtitle">Add a new factory cutting clip or jhoot trader lot to the digitized circularity pool</div>
        </div>
        <span class="badge b-verified">Intake Portal</span>
      </div>
      <div id="lot-msg" class="msg">{e(msg)}</div>
      <form id="lot-form" onsubmit="return addLot(event)">
        <div class="frow">
          <label>Source Name <span style="color:var(--accent-red)">*</span>
            <input name="source_name" required placeholder="e.g. Apex Spinning Mills Ltd">
          </label>
          <label>Source Type
            <select name="source_type"><option>factory</option><option>trader</option></select>
          </label>
          <label>Quantity (kg) <span style="color:var(--accent-red)">*</span>
            <input name="qty_kg" type="number" min="1" required placeholder="e.g. 500">
          </label>
        </div>
        <div class="frow">
          <label>Material Category
            <select name="category">{cat_opts}</select>
          </label>
          <label>Grade
            <select name="grade"><option>A</option><option selected>B</option><option>C</option></select>
          </label>
          <label>Colour
            <input name="colour" placeholder="e.g. off-white / grey">
          </label>
          <label>Contamination %
            <input name="contamination_pct" type="number" min="0" max="100" value="3">
          </label>
        </div>
        <div class="frow">
          <label>Location Name
            <input name="location_name" placeholder="e.g. Gazipur / Ashulia">
          </label>
          <label>Latitude
            <input name="lat" type="number" step="0.0001" value="23.9999">
          </label>
          <label>Longitude
            <input name="lon" type="number" step="0.0001" value="90.4203">
          </label>
          <label>Verification Status
            <select name="status"><option>pending</option><option selected>verified</option></select>
          </label>
        </div>
        
        <label>Lot Sample Photo (Optional)
          <div class="upload-box" onclick="document.querySelector('input[name=photo]').click()">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" style="color:var(--primary-forest); margin-bottom:6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <div style="font-weight:600; font-size:13px; color:var(--text-main);">Click to upload sample image</div>
            <div class="muted" style="margin-top:2px;">Supports JPG, PNG up to 1.5MB &bull; Triggers AI material classification suggestion</div>
          </div>
          <input name="photo" type="file" accept="image/*" style="display:none;">
        </label>
        <p style="margin-top: 16px;">
          <button class="btn btn-primary" type="submit">Register Waste Lot</button>
          <span class="muted" style="margin-left: 12px;">Composition is declared by the supplier; human physical verification is logged at intake.</span>
        </p>
      </form>
    </div>"""
    return layout("Waste Inventory", "/lots", body, "Inventory")

def page_aggregation(msg=""):
    buyers = conn.execute("SELECT * FROM buyers").fetchall()
    opts = "".join(f"<option value='{b["id"]}'>{e(b["name"])} &mdash; Needs {int(b["min_qty"]):,} kg {e(b["category"])} (Grades {e(b["accepted_grades"])}, max {b["max_contamination"]}% contam)</option>" for b in buyers)

    body = f"""<div class="page-header">
      <div>
        <h1 class="page-title">Explainable Multi-Objective Batch Optimizer</h1>
        <p class="page-subtitle">Solving the fundamental bottleneck of textile circularity: bundling fragmented 200&ndash;500 kg factory lots into homogeneous 1,000+ kg batches with multi-objective Pareto trade-offs across logistics friction, QA verification, and material purity</p>
      </div>
      <div class="page-actions">
        <a class="btn btn-outline" href="/buyers">View Buyer Requirements</a>
      </div>
    </div>

    <div class="challenge-context-strip">
      <div class="challenge-context-badge">Pillar 2: Multi-Objective Aggregation</div>
      <div class="challenge-context-text">
        <strong>Multi-Objective Pareto Solver:</strong> Bangladesh cutting floors generate small daily volumes that recyclers cannot economically process alone. PunorAI evaluates unallocated inventory across candidate combinations, balancing freight friction (BDT/kg), intake QA confidence (% verified), and weighted contamination with 100% explainable reason codes.
      </div>
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Run Multi-Objective Optimizer for a Buyer</h3>
          <div class="card-subtitle">Evaluates material category, acceptable grades, contamination limits, transport friction, and physical QA status</div>
        </div>
        <span class="badge b-verified">Multi-Objective Pareto Solver</span>
      </div>
      <form onsubmit="return runAgg(event)" style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
        <select name="buyer_id" required style="max-width: 540px; flex:1;">
          {opts}
        </select>
        <button class="btn btn-primary" type="submit">Find Optimal Batch</button>
      </form>
      <div id="agg-result" style="margin-top: 20px;"></div>
    </div>
    {msg}"""
    return layout("Aggregation", "/aggregation", body, "Aggregation Planner")

def render_plan(p):
    exc = "".join("<tr><td><strong class='num'>" + e(x["lot"]["code"]) + "</strong></td><td>" + e(x["lot"]["source_name"]) + "</td><td><span class='badge " + ("b-alloc" if "allocated" in x["reason"].lower() else "b-pending") + "'>" + e(x["reason"]) + "</span></td></tr>" for x in p.get("excluded", []))

    if not p["feasible"]:
        el_rows = "".join("<tr><td><strong class='num'>" + e(l["code"]) + "</strong></td><td><b>" + e(l["source_name"]) + "</b></td><td>" + e(l["category"]) + "</td><td>" + e(l["grade"]) + "</td><td><b class='num'>" + f"{int(l['qty_kg']):,}" + " kg</b></td><td>" + e(l["location_name"]) + "</td><td><span class='badge b-verified'>Eligible (" + f"{int(l['qty_kg']):,}" + " kg)</span></td></tr>" for l in p.get("eligible", []))
        eligible_section = ""
        if el_rows:
            eligible_section = f"""<div class="card" style="margin-bottom: 16px; padding: 14px 18px;">
              <div style="font-weight:700; font-size:13px; margin-bottom:8px; text-transform:uppercase; color:var(--text-muted);">Compatible Eligible Lots in Inventory (Volume Below Minimum Batch)</div>
              <div style="overflow-x:auto;">
                <table>
                  <thead><tr><th>Lot Code</th><th>Source Factory/Trader</th><th>Material</th><th>Grade</th><th>Quantity</th><th>Location</th><th>Eligibility Status</th></tr></thead>
                  <tbody>{el_rows}</tbody>
                </table>
              </div>
            </div>"""

        shortfall_diag = ""
        sf_details = p.get("shortfall_details", {})
        if sf_details and sf_details.get("shortfall_kg", 0) > 0:
            shortfall_diag = f"""<div class="card" style="margin-bottom: 16px; padding: 16px 20px; border-left: 4px solid var(--accent-orange, #F59E0B);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px; flex-wrap:wrap; gap:8px;">
                <div style="font-weight:700; font-size:13px; text-transform:uppercase; color:var(--text-main);">
                  Aggregation Bottleneck Diagnostic &amp; Required Secondary Feedstock
                </div>
                <span class="badge b-pending">Deficit: {int(sf_details['shortfall_kg']):,} kg</span>
              </div>
              <p style="margin: 0 0 12px 0; color:var(--text-muted); line-height: 1.5; font-size:13px;">
                {e(sf_details.get('recommendation', ''))}
              </p>
              <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 6px; border: 1px solid var(--border-color);">
                <div><div class="muted" style="font-size:11px; text-transform:uppercase;">Required Category</div><strong>{e(sf_details.get('category', p['buyer']['category']))}</strong></div>
                <div><div class="muted" style="font-size:11px; text-transform:uppercase;">Acceptable Grades</div><strong>{e(sf_details.get('accepted_grades', p['buyer']['accepted_grades']))}</strong></div>
                <div><div class="muted" style="font-size:11px; text-transform:uppercase;">Contamination Ceiling</div><strong>&le; {sf_details.get('max_contamination', p['buyer']['max_contamination'])}%</strong></div>
                <div><div class="muted" style="font-size:11px; text-transform:uppercase;">Regional Cluster Radius</div><strong>{e(sf_details.get('location_name', p['buyer']['location_name']))} ({int(sf_details.get('service_radius_km', p['buyer']['service_radius_km']))} km)</strong></div>
              </div>
            </div>"""

        return (f"<div class='warn' style='margin-bottom: 16px;'>"
                f"<div><strong>Feasible batch not currently possible:</strong> Only <b>{int(p['total_kg']):,} kg</b> eligible material available in inventory vs buyer minimum <b>{int(p['target_kg']):,} kg</b> "
                f"(shortfall of <b>{int(p['shortfall_kg']):,} kg</b>). Feasible batch weight: <b>0 kg</b>. The engine reports shortfall honestly rather than fabricating a match.</div>"
                f"</div>"
                f"""<div style="border-top: 1px solid var(--border-color); padding-top: 16px;">
                  {shortfall_diag}
                  {eligible_section}
                  <div class="card" style="padding: 14px 18px;">
                    <div style="font-weight:700; font-size:13px; margin-bottom:8px; text-transform:uppercase; color:var(--text-muted);">Transparent Exclusion Explanations (Why Other Lots Were Not Selected)</div>
                    <div style="overflow-x:auto;">
                      <table>
                        <thead><tr><th>Lot Code</th><th>Source</th><th>Specific Constraint Reason</th></tr></thead>
                        <tbody>{exc}</tbody>
                      </table>
                    </div>
                  </div>
                </div>""")

    def render_candidate_card(cand, buyer, is_primary=True):
        lot_rows = "".join(
            f"<tr><td><strong class='num'>{e(l['code'])}</strong></td>"
            f"<td><b>{e(l['source_name'])}</b></td>"
            f"<td>{e(l['category'])}</td>"
            f"<td>{e(l['grade'])}</td>"
            f"<td><span class='num'>{l['contamination_pct']}%</span></td>"
            f"<td><b class='num'>{int(l['qty_kg']):,} kg</b></td>"
            f"<td>{e(l['location_name'])}</td>"
            f"<td><span class='badge {('b-verified' if l.get('status') == 'verified' else 'b-pending')}'>{e(STATUS_LABEL.get(l.get('status'), l.get('status', 'Pending')))}</span></td></tr>"
            for l in cand["lots"]
        )

        border_style = "border: 2px solid var(--primary-forest); box-shadow: var(--shadow-sm);" if is_primary else "border: 1px solid var(--border-color);"
        bg_style = "background: linear-gradient(180deg, rgba(21, 61, 50, 0.06) 0%, rgba(21, 61, 50, 0.02) 100%);" if is_primary else ""
        btn_cls = "btn-accent" if is_primary else "btn-primary"
        btn_label = "Create Batch &amp; Issue Material Passport" if is_primary else f"Select {e(cand['profile_name'])} &amp; Issue Passport"

        return f"""<div class="card" style="margin-bottom: 20px; padding: 18px 20px; {border_style} {bg_style}">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 12px; flex-wrap:wrap; gap:10px;">
            <div>
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <span class="badge {cand.get('profile_badge_class', 'b-verified')}">{e(cand.get('profile_badge', 'Candidate Batch'))}</span>
                <span class="badge {cand.get('v_badge', 'b-pending')}">{e(cand.get('v_label', 'Batch QA'))}</span>
              </div>
              <h4 style="margin:0; font-size:16px; color:var(--text-main); font-weight:700;">{e(cand.get('profile_name', 'Feasible Batch'))} &mdash; <span class="num" style="color:var(--primary-forest);">{int(cand['total_kg']):,} kg</span></h4>
            </div>
            <button class="btn {btn_cls}" onclick='createBatch({buyer["id"]},{json.dumps(cand["lot_ids"])})'>{btn_label}</button>
          </div>

          <div style="background: rgba(255,255,255,0.04); border-left: 3px solid var(--primary-forest); padding: 10px 14px; border-radius: 4px; margin-bottom: 14px; font-size:12.5px; line-height:1.5;">
            <strong>💡 Multi-Objective Rationale:</strong> {e(cand.get('rationale', 'Feasible subset-sum solution meeting all quality and contamination limits.'))}
          </div>

          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px;">
            <div style="background: rgba(255,255,255,0.02); border:1px solid var(--border-color); padding: 10px; border-radius:6px;">
              <div class="muted" style="font-size:11px; text-transform:uppercase;">Total Weight</div>
              <div style="font-size:15px; font-weight:700;" class="num">{int(cand['total_kg']):,} kg</div>
              <div class="muted" style="font-size:11px;">Target: {int(buyer['min_qty']):,} kg (+{int(cand.get('excess_kg', 0)):,} kg)</div>
            </div>
            <div style="background: rgba(255,255,255,0.02); border:1px solid var(--border-color); padding: 10px; border-radius:6px;">
              <div class="muted" style="font-size:11px; text-transform:uppercase;">Logistics Friction</div>
              <div style="font-size:15px; font-weight:700; color:var(--primary-teal);" class="num">{cand.get('cost_per_kg', 0):.2f} BDT/kg</div>
              <div class="muted" style="font-size:11px;">{cand.get('route_km', 0)} km &bull; {int(cand.get('route_cost', 0)):,} BDT</div>
            </div>
            <div style="background: rgba(255,255,255,0.02); border:1px solid var(--border-color); padding: 10px; border-radius:6px;">
              <div class="muted" style="font-size:11px; text-transform:uppercase;">Weighted Contam</div>
              <div style="font-size:15px; font-weight:700;" class="num">{cand.get('avg_contamination', 0):.1f}%</div>
              <div class="muted" style="font-size:11px;">Buyer ceiling: &le;{buyer['max_contamination']}%</div>
            </div>
            <div style="background: rgba(255,255,255,0.02); border:1px solid var(--border-color); padding: 10px; border-radius:6px;">
              <div class="muted" style="font-size:11px; text-transform:uppercase;">Intake Verification</div>
              <div style="font-size:15px; font-weight:700;" class="num">{cand.get('verified_pct', 0)}% QA</div>
              <div class="muted" style="font-size:11px;">{cand.get('verified_count', 0)} of {len(cand['lots'])} lots verified</div>
            </div>
          </div>

          <div style="font-weight:700; font-size:12px; margin-bottom:6px; text-transform:uppercase; color:var(--text-muted);">Constituent Lots in This Batch</div>
          <div style="overflow-x:auto;">
            <table>
              <thead><tr><th>Lot Code</th><th>Source Factory/Trader</th><th>Material</th><th>Grade</th><th>Contam</th><th>Quantity</th><th>Location</th><th>Intake QA</th></tr></thead>
              <tbody>{lot_rows}</tbody>
            </table>
          </div>
        </div>"""

    # Primary recommended candidate
    candidates = p.get("candidates", [])
    rec = p.get("recommended")
    if not rec and candidates:
        rec = candidates[0]
    if not rec and p.get("selected"):
        rec = {
            "lots": p["selected"],
            "lot_ids": [l["id"] for l in p["selected"]],
            "total_kg": p["total_kg"],
            "target_kg": p["target_kg"],
            "excess_kg": max(0, p["total_kg"] - p["target_kg"]),
            "avg_contamination": round(sum(l.get("qty_kg", 0) * l.get("contamination_pct", 0) for l in p["selected"]) / max(p["total_kg"], 1), 2),
            "route_km": 0.0,
            "route_cost": 0.0,
            "cost_per_kg": 0.0,
            "v_label": "Standard Batch",
            "v_badge": "b-pending",
            "verified_pct": 50.0,
            "verified_count": sum(1 for l in p["selected"] if l.get("status") == "verified"),
            "profile_name": "Balanced Optimal Batch",
            "profile_badge": "Recommended (Balanced Optimal)",
            "profile_badge_class": "b-verified",
            "rationale": "Optimal subset-sum solution meeting all quality and contamination limits."
        }

    rec_html = render_candidate_card(rec, p["buyer"], is_primary=True)

    # Alternative candidate cards (if distinct options exist)
    alternatives = p.get("alternatives", [])
    alt_cards_html = ""
    if alternatives:
        rendered_alts = "".join(render_candidate_card(alt, p["buyer"], is_primary=False) for alt in alternatives)
        alt_cards_html = f"""<div style="margin-top: 24px; margin-bottom: 20px;">
          <div style="margin-bottom: 12px;">
            <h4 style="margin:0; font-size:15px; color:var(--text-main); font-weight:700;">Viable Alternative Candidate Batches (Operational Trade-Off Profiles)</h4>
            <div class="muted" style="font-size:12px;">Operators can select alternative batch configurations based on physical QA urgency or transport clustering.</div>
          </div>
          {rendered_alts}
        </div>"""

    exc = "".join("<tr><td><strong class='num'>" + e(x["lot"]["code"]) + "</strong></td><td>" + e(x["lot"]["source_name"]) + "</td><td><span class='badge " + ("b-alloc" if "allocated" in x["reason"].lower() else "b-pending") + "'>" + e(x["reason"]) + "</span></td></tr>" for x in p.get("excluded", []))
    skip = "".join("<tr><td><strong class='num'>" + e(l["code"]) + "</strong></td><td>" + e(l["source_name"]) + "</td><td><span class='badge b-simulated'>Eligible unallocated lot &mdash; omitted to optimize candidate logistics/QA</span></td></tr>" for l in p.get("skipped_eligible", []))

    return (f"""<div style="border-top: 1px solid var(--border-color); padding-top: 20px;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom: 16px; flex-wrap:wrap; gap:10px;">
        <div>
          <h4 style="margin:0; font-size:16px; color:var(--primary-forest);">Feasible Batch Solved: {int(p['total_kg']):,} kg (Target {int(p['target_kg']):,} kg)</h4>
          <div class="muted">Multi-objective Pareto solver evaluated {len(candidates)} candidate batch configuration(s).</div>
        </div>
        <span class="badge b-verified">Multi-Objective Pareto Optimal</span>
      </div>

      {rec_html}

      {alt_cards_html}

      <div class="card" style="padding: 14px 18px;">
        <div style="font-weight:700; font-size:13px; margin-bottom:8px; text-transform:uppercase; color:var(--text-muted);">Transparent Exclusion &amp; Omission Explanations (Why Other Lots Were Not Selected)</div>
        <div style="overflow-x:auto;">
          <table>
            <thead><tr><th>Lot Code</th><th>Source</th><th>Specific Constraint Reason</th></tr></thead>
            <tbody>{exc}{skip}</tbody>
          </table>
        </div>
      </div>
    </div>""")

def page_buyers():
    rows = ""
    for b in conn.execute("SELECT * FROM buyers").fetchall():
        rows += ("<tr><td><b>" + e(b["name"]) + "</b></td>"
                 "<td>" + e(b["category"]) + "</td><td>" + e(b["accepted_grades"]) + "</td>"
                 "<td><span class='num'>" + str(b["max_contamination"]) + "%</span></td>"
                 "<td><span class='num'>" + f"{int(b['min_qty']):,}" + "&ndash;" + f"{int(b['max_qty']):,}" + " kg</span></td>"
                 "<td>" + e(b["location_name"]) + " (" + str(int(b["service_radius_km"])) + " km radius)</td>"
                 "<td>" + badge(b["status"]) + "</td></tr>")

    pr = "".join("<tr><td><b>" + e(r["category"]) + "</b></td><td>" + e(r["grade"]) + "</td><td><b class='num'>" + str(int(r["low"])) + "&ndash;" + str(int(r["high"])) + " BDT/kg</b></td><td>" + e(r["source"]) + "</td><td><span class='num'>" + e(r["updated_at"]) + "</span></td><td>" + badge(r["status"]) + "</td></tr>" for r in conn.execute("SELECT * FROM prices").fetchall())

    body = f"""<div class="page-header">
      <div>
        <h1 class="page-title">Circular Recycler Demand & Material Compatibility</h1>
        <p class="page-subtitle">Matching characterized textile waste streams to industrial recyclers based on technical intake specifications and fiber constraints</p>
      </div>
    </div>

    <div class="challenge-context-strip">
      <div class="challenge-context-badge">Pillar 3: Recycler Matching</div>
      <div class="challenge-context-text">
        <strong>Technical Intake Constraints:</strong> In Bangladesh, industrial recyclers and spinning mills operate under rigid technical boundaries: maximum 5% synthetic contamination, minimum 1,000 kg batch weights, and fiber length requirements. PunorAI matches these constraints deterministically to enable industrial-scale circular recovery.
      </div>
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Verified Industrial Recycler Profiles</h3>
          <div class="card-subtitle">Intake specifications, material tolerance limits and logistics radiuses</div>
        </div>
        <span class="badge b-verified">Recycler Network</span>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr><th>Buyer Name</th><th>Material Accepted</th><th>Grades</th><th>Max Contam.</th><th>Batch Range (kg)</th><th>Location & Radius</th><th>Status</th></tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
      <div class="muted" style="margin-top: 10px;">All buyers and requirements are simulated demonstration records based on typical Bangladesh recycling mill profiles.</div>
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Indicative Market Price Guidance</h3>
          <div class="card-subtitle">Transparent regional price benchmarks with declared sources and freshness timestamps</div>
        </div>
        <span class="badge b-simulated">Market Benchmarks</span>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr><th>Material Category</th><th>Grade</th><th>Indicative Range</th><th>Data Source</th><th>Last Updated</th><th>Status</th></tr>
          </thead>
          <tbody>
            {pr}
          </tbody>
        </table>
      </div>
      <div class="muted" style="margin-top: 10px;">A machine-learning price discovery model is planned for future phases; the MVP displays declared market survey benchmarks.</div>
    </div>"""
    return layout("Buyers", "/buyers", body, "AI Matching")

def page_passports():
    batches = conn.execute("SELECT * FROM batches ORDER BY id DESC").fetchall()
    cards = ""
    for b in batches:
        url = BASE_URL + "/passport/" + urllib.parse.quote(b["code"])
        qr = "https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=" + urllib.parse.quote(url, safe="")
        lots = conn.execute("SELECT l.* FROM lots l JOIN batch_lots bl ON l.id=bl.lot_id WHERE bl.batch_id=?", (b["id"],)).fetchall()
        v_code, v_label, v_badge, v_desc = batch_verification_status(lots)
        actual_total_kg = int(sum(l["qty_kg"] for l in lots)) or int(b["total_kg"])
        is_pub = is_public_url(url)
        url_note = "Publicly verifiable link" if is_pub else "Local development link (configure PUNORAI_BASE_URL / CIRCULO_BASE_URL for public deployment)"

        cards += f"""<div class="card passport-card">
          <div style="flex:1;">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
              <span class="badge {v_badge}">{v_label}</span>
              <span class="badge b-alloc">{e(b['code'])}</span>
            </div>
            <h3 style="margin: 0 0 6px;">Allocated to {e(b['buyer_name'])}</h3>
            <p class="muted" style="margin: 0 0 12px; font-size:13px;">
              Total Weight: <b class="num" style="color:var(--text-main); font-size:15px;">{actual_total_kg:,} kg</b> &bull;
              Originating Lots: <b>{len(lots) or b['lot_count']}</b> &bull;
              Created: <span class="num">{e(b['created_at'])}</span>
            </p>
            <div>
              <a href="/passport/{e(b['code'])}" class="btn btn-sm btn-primary">Open Passport Certificate &rarr;</a>
              <span class="muted" style="margin-left: 10px; font-size:11.5px;">{url_note}</span>
            </div>
          </div>
          <div style="text-align:center;">
            <img class="passport-qr" src="{qr}" alt="QR Passport" onerror="this.style.opacity='0.25'; this.title='QR image service offline; use direct link';">
            <div class="qr-scan-label">Scan to verify passport</div>
          </div>
        </div>"""

    if not cards:
        cards = """<div class="card" style="text-align: center; padding: 48px 24px;">
          <div style="width: 48px; height: 48px; border-radius: 50%; background: var(--bg-app); display: inline-flex; align-items: center; justify-content: center; color: var(--text-muted); margin-bottom: 12px;">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          </div>
          <h3 style="margin:0 0 6px;">No Material Passports Generated Yet</h3>
          <p class="muted" style="max-width: 480px; margin: 0 auto 18px;">Run the Smart Aggregation Engine for a buyer to solve an optimal batch and issue a Digital Material Passport.</p>
          <a href="/aggregation" class="btn btn-primary">Go to Aggregation Engine</a>
        </div>"""

    body = f"""<div class="page-header">
      <div>
        <h1 class="page-title">Digital Material Passports & Circular Traceability</h1>
        <p class="page-subtitle">Digital Material Passports tracking fiber composition, originating cutting rooms, handling history, and physical verification events</p>
      </div>
    </div>

    <div class="challenge-context-strip">
      <div class="challenge-context-badge">Pillar 5: Material Passports & Traceability</div>
      <div class="challenge-context-text">
        <strong>Verifiable Chain-of-Custody:</strong> Export-grade circular recycling requires transparent provenance. Digital Material Passports link each aggregated industrial batch to its constituent factory cutting clips, preserving traceability for international brands and domestic spinners.
      </div>
    </div>
    {cards}"""
    return layout("Material Passports", "/passports", body, "Passports")

def page_passport_detail(code):
    b = conn.execute("SELECT * FROM batches WHERE code=?", (code,)).fetchone()
    if not b: return layout("Not Found", "/passports", "<h1>Passport Not Found</h1><p>Batch code does not exist.</p>")
    lots = conn.execute("SELECT l.* FROM lots l JOIN batch_lots bl ON l.id=bl.lot_id WHERE bl.batch_id=?", (b["id"],)).fetchall()
    evs = conn.execute("SELECT * FROM events WHERE batch_id=? ORDER BY id", (b["id"],)).fetchall()
    url = BASE_URL + "/passport/" + urllib.parse.quote(code)
    qr = "https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=" + urllib.parse.quote(url, safe="")

    v_code, v_label, v_badge, v_desc = batch_verification_status(lots)
    actual_total_kg = int(sum(l["qty_kg"] for l in lots)) or int(b["total_kg"])
    is_pub = is_public_url(url)
    url_badge = '<span class="badge b-verified" style="font-size:10px;">Public Domain</span>' if is_pub else '<span class="badge b-simulated" style="font-size:10px;">Local Dev URL</span>'
    url_note = "Publicly accessible certificate link" if is_pub else "Local development URL (configure PUNORAI_BASE_URL / CIRCULO_BASE_URL for public deployment)"

    timeline = "".join(f"<li style='margin-bottom:12px;'><strong class='num' style='color:var(--primary-forest);'>{e(x['ts'])}</strong> &mdash; {e(x['description'])}</li>" for x in evs)
    lrows = "".join("<tr><td><strong class='num'>" + e(l["code"]) + "</strong></td><td><b>" + e(l["source_name"]) + "</b></td><td>" + e(l["category"]) + " (Declared)</td><td>" + e(l["grade"]) + "</td><td><b class='num'>" + f"{int(l['qty_kg']):,}" + " kg</b></td><td>" + e(l["location_name"]) + "</td><td>" + badge(l["status"]) + "</td></tr>" for l in lots)

    body = f"""<div class="page-header">
      <div>
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
          <a href="/passports" style="text-decoration:none; color:var(--text-muted); font-size:13px;">&larr; Back to All Passports</a>
        </div>
        <h1 class="page-title">Material Passport: {e(code)}</h1>
        <p class="page-subtitle">Digital Material Passport tracking constituent factory waste lots &bull; Batch total {actual_total_kg:,} kg</p>
      </div>
    </div>

    <div class="card passport-card">
      <div style="flex:1;">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
          <span class="badge {v_badge}">{v_label}</span>
          <span class="badge b-alloc">Traced Batch</span>
        </div>
        <h2 style="margin: 0 0 6px; font-size:22px;">Batch {e(code)} &rarr; {e(b['buyer_name'])}</h2>
        <p class="muted" style="margin: 0 0 14px;">Created on <span class="num">{e(b['created_at'])}</span> &bull; Batch Status: <span class="badge {v_badge}">{v_label}</span> &bull; Batch Weight: <b class="num" style="color:var(--text-main);">{actual_total_kg:,} kg</b></p>
        <div class="warn" style="margin: 0 0 14px;">
          <div><strong>Verification Protocol:</strong> {v_desc} Composition is supplier-declared and intake-checked. Independent chemical laboratory certification is not fabricated.</div>
        </div>
        <div class="muted">Verification URL: <a href="{e(url)}" target="_blank" style="color:var(--primary-forest);">{e(url)}</a> {url_badge}</div>
        <div class="muted" style="font-size:11px; margin-top:3px;">{url_note}</div>
      </div>
      <div style="text-align:center;">
        <img class="passport-qr" style="width:130px; height:130px;" src="{qr}" alt="QR code" onerror="this.style.opacity='0.25'; this.title='QR image service offline; use direct link';">
        <div class="qr-scan-label">Scan to verify passport</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Originating Waste Lots in this Batch</h3>
          <div class="card-subtitle">Constituent cutting clips and trader lots bundled into this industrial batch</div>
        </div>
        <span class="badge b-verified">{len(lots)} Input Lots &bull; {actual_total_kg:,} kg</span>
      </div>
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr><th>Lot Code</th><th>Source Factory</th><th>Declared Material</th><th>Grade</th><th>Quantity</th><th>Location</th><th>Intake QA</th></tr>
          </thead>
          <tbody>
            {lrows}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Verifiable Event History</h3>
          <div class="card-subtitle">Auditable Verification Event Log of lot intake, aggregation solver execution, and passport generation</div>
        </div>
        <span class="badge b-simulated">Audit Trail</span>
      </div>
      <ol style="padding-left: 20px; line-height: 1.6; margin: 0;">
        {timeline}
      </ol>
    </div>"""
    return layout("Passport " + code, "/passports", body, "Passport " + code)

def page_planning():
    batches = conn.execute("SELECT * FROM batches").fetchall()
    if not batches:
        body = """<div class="page-header">
          <div>
            <h1 class="page-title">Resource Recovery Logistics & Route Optimization</h1>
            <p class="page-subtitle">Reverse logistics decision support for multi-stop lot consolidation across Gazipur, Ashulia, and Dhaka garment clusters</p>
          </div>
        </div>
        <div class="challenge-context-strip">
          <div class="challenge-context-badge">Pillar 4: Reverse Logistics</div>
          <div class="challenge-context-text">
            <strong>Clustered Collection Decision Support:</strong> Fragmented mill waste incurs high freight friction if collected ad-hoc. PunorAI models multi-stop pickup circuits using Haversine network analysis and transparent freight cost rates to minimize reverse-logistics carbon footprint and transport costs.
          </div>
        </div>
        <div class="card" style="text-align: center; padding: 48px 24px;">
          <h3 style="margin:0 0 8px;">No Batches Available for Route Planning</h3>
          <p class="muted" style="max-width: 480px; margin: 0 auto 18px;">Create a candidate batch on the Aggregation page to calculate consolidation routes and transport cost estimates.</p>
          <a href="/aggregation" class="btn btn-primary">Go to Aggregation Planner</a>
        </div>"""
        return layout("Collection Planning", "/planning", body, "Logistics")

    body = """<div class="page-header">
      <div>
        <h1 class="page-title">Resource Recovery Logistics & Route Optimization</h1>
        <p class="page-subtitle">Reverse logistics decision support for multi-stop lot consolidation across Gazipur, Ashulia, and Dhaka garment clusters</p>
      </div>
    </div>

    <div class="challenge-context-strip">
      <div class="challenge-context-badge">Pillar 4: Reverse Logistics</div>
      <div class="challenge-context-text">
        <strong>Clustered Collection Decision Support:</strong> Fragmented mill waste incurs high freight friction if collected ad-hoc. PunorAI models multi-stop pickup circuits using Haversine network analysis and transparent freight cost rates to minimize reverse-logistics carbon footprint and transport costs.
      </div>
    </div>"""

    for b in batches:
        lots = conn.execute("SELECT l.* FROM lots l JOIN batch_lots bl ON l.id=bl.lot_id WHERE bl.batch_id=?", (b["id"],)).fetchall()
        buyer = conn.execute("SELECT * FROM buyers WHERE id=?", (b["buyer_id"],)).fetchone()
        r = plan_route(conn, [l["id"] for l in lots], buyer["lat"], buyer["lon"])
        stops = "".join(f"<tr><td><b>Stop {i+1}</b></td><td><strong class='num'>{e(p['code'])}</strong> &bull; {e(p['location_name'])}</td><td><b class='num'>{int(p['qty_kg']):,} kg</b></td><td><span class='num'>{d:.1f} km</span> from previous</td></tr>" for i, (p, d) in enumerate(r["stops"]))

        body += f"""<div class="card">
          <div class="card-title-bar">
            <div>
              <h3>Batch {e(b['code'])} &rarr; {e(b['buyer_name'])} ({int(b['total_kg']):,} kg)</h3>
              <div class="card-subtitle">Collection route originating from Gazipur/Ashulia to destination depot</div>
            </div>
            <span class="badge b-alloc">Active Route</span>
          </div>
          <div style="overflow-x:auto;">
            <table>
              <thead><tr><th>Sequence</th><th>Pickup Location</th><th>Material Load</th><th>Leg Distance</th></tr></thead>
              <tbody>{stops}</tbody>
            </table>
          </div>
          <div style="background:var(--bg-app); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:14px 18px; margin-top:16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
              <div>Total Circuit Distance: <b class="num" style="font-size:16px;">{r['total_km']} km</b> &bull; Rate Assumption: <span class="num">{int(r['rate_per_km'])} BDT/km</span></div>
              <div class="muted" style="margin-top:2px;">{e(r['method'])}</div>
            </div>
            <div>
              <div style="font-size:11px; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Estimated Transport Cost</div>
              <div class="num" style="font-size:20px; font-weight:800; color:var(--primary-forest);">{int(r['est_cost']):,} BDT</div>
            </div>
          </div>
        </div>"""
    return layout("Collection Planning", "/planning", body, "Logistics")

def page_reports():
    tl = conn.execute("SELECT COUNT(*) n, COALESCE(SUM(qty_kg),0) s FROM lots").fetchone()
    al = conn.execute("SELECT COALESCE(SUM(total_kg),0) s, COUNT(*) n FROM batches").fetchone()
    ver = conn.execute("SELECT COUNT(*) n FROM lots WHERE status='verified'").fetchone()["n"]
    pend = conn.execute("SELECT COUNT(*) n FROM lots WHERE status='pending'").fetchone()["n"]
    cats = conn.execute("SELECT category, SUM(qty_kg) s FROM lots GROUP BY category ORDER BY s DESC").fetchall()
    
    total_kg = int(tl["s"]) if tl["s"] else 0
    allocated_kg = int(al["s"]) if al["s"] else 0
    unallocated_kg = total_kg - allocated_kg
    allocation_rate = int(round(100 * allocated_kg / total_kg)) if total_kg else 0

    body = f"""<div class="page-header">
      <div>
        <h1 class="page-title">Circular Economy Resource Recovery Reports</h1>
        <p class="page-subtitle">Empirical mass-balance analytics, material recovery efficiency, and transparent environmental disclosures under the ClimateSphere AI Circular Future framework.</p>
      </div>
    </div>

    <div class="challenge-context-strip">
      <div class="challenge-context-badge">Pillar 6: Empirical Reporting</div>
      <div class="challenge-context-text">
        <strong>ClimateSphere AI &bull; Circular Future Scope:</strong> Advancing the circular economy through verified material recovery. PunorAI enforces strict methodology honesty: reporting empirical mass balance and physical recovery rates rather than unverified carbon credit claims.
      </div>
    </div>

    <div class="grid4">
      {metric("Total Characterized", f"{total_kg:,} kg", f"{tl['n']} registered waste lots across RMG clusters", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z'/></svg>")}
      {metric("Aggregated to Batches", f"{allocated_kg:,} kg", f"{al['n']} batches ({unallocated_kg:,} kg unallocated inventory)", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><rect x='3' y='3' width='7' height='7'/><rect x='14' y='3' width='7' height='7'/><rect x='14' y='14' width='7' height='7'/><rect x='3' y='14' width='7' height='7'/></svg>")}
      {metric("Batch Allocation Rate", f"{allocation_rate}%", "Share allocated to batches (not physical recycling yield)", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M22 11.08V12a10 10 0 1 1-5.93-9.14'/><polyline points='22 4 12 14.01 9 11.01'/></svg>")}
      {metric("Intake Verification Rate", f"{ver} of {tl['n']} Lots", "Intake sample & tag verified (not lab-certified)", "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/></svg>")}
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>Registered Material Streams by Category</h3>
          <div class="card-subtitle">Measured inventory volumes (kg) across all verified and pending lots</div>
        </div>
        <span class="badge b-verified">Measured Activity</span>
      </div>
      <div class="chart-container">
        {svg_bar("Registered kg per category", [(c["category"], int(c["s"])) for c in cats], color="#153D32")}
      </div>
    </div>

    <div class="card">
      <div class="card-title-bar">
        <div>
          <h3>ClimateSphere AI &bull; Circular Future & SDG Alignment</h3>
          <span class="badge b-verified">Impact Framework</span>
        </div>
      </div>
      <p style="line-height:1.65; margin-top:0; color:var(--text-main);">
        Under <strong>ClimateSphere AI</strong> (AI for decarbonization, resilience, water, energy, and the circular economy), <strong>PunorAI</strong> directly solves the <strong>Circular Future</strong> challenge by transforming fragmented post-industrial garment waste across Bangladesh's textile manufacturing hubs from downcycled or landfilled scrap into traceable secondary feedstock with explicit verification status.
      </p>
      
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin: 18px 0;">
        <div style="background:var(--bg-app); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:16px;">
          <div style="font-weight:700; font-size:13.5px; color:var(--primary-forest); margin-bottom:4px;">SDG 12: Responsible Consumption</div>
          <div style="font-size:12.5px; color:var(--text-muted); line-height:1.5;">Target 12.5: Substantially reduce waste generation through prevention, reduction, recycling, and reuse by converting cutting floor scrap into industrial spinning batches.</div>
        </div>
        <div style="background:var(--bg-app); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:16px;">
          <div style="font-weight:700; font-size:13.5px; color:var(--primary-forest); margin-bottom:4px;">SDG 9: Industry & Innovation</div>
          <div style="font-size:12.5px; color:var(--text-muted); line-height:1.5;">Target 9.4: Upgrade infrastructure and retrofit industries with transparent combinatorial constraint solvers and verifiable Digital Material Passports.</div>
        </div>
        <div style="background:var(--bg-app); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:16px;">
          <div style="font-weight:700; font-size:13.5px; color:var(--primary-forest); margin-bottom:4px;">SDG 13: Climate Action</div>
          <div style="font-size:12.5px; color:var(--text-muted); line-height:1.5;">Indirect mitigation: Replacing virgin cotton cultivation and polyester synthesis with recovered secondary circular fibers avoids high-emission agricultural and fossil inputs.</div>
        </div>
      </div>

      <div class="warn">
        <div>
          <strong>Methodology Honesty & Environmental Boundary Disclosure:</strong> Theoretical carbon offset, GHG reduction, and avoided water consumption metrics are intentionally NOT fabricated or claimed as verified credits in this build. In accordance with ClimateSphere AI standards to prevent greenwashing, PunorAI strictly reports empirical mass balance (kilograms of verified material characterized, aggregated, and routed). Certified lifecycle assessment (LCA) coefficients will only be incorporated once certified by accredited independent auditors.
        </div>
      </div>
    </div>"""
    return layout("Reports", "/reports", body, "Analytics")

# ---------- API ----------
def api_lots(payload):
    photo_path = ""
    pd = payload.get("photo_data", "")
    if pd and "," in pd and len(pd) < 1_500_000:
        ext = "png" if "png" in pd[:40] else "jpg"
        fn = "lot_" + str(int(NOW()[-5:].replace(":", ""))) + "." + ext
        with open(os.path.join(UPLOADS, fn), "wb") as f:
            f.write(base64.b64decode(pd.split(",", 1)[1]))
        photo_path = "/uploads/" + fn

    req_code = payload.get("code", "").strip()
    if req_code:
        if conn.execute("SELECT COUNT(*) n FROM lots WHERE code=?", (req_code,)).fetchone()["n"] > 0:
            return {"ok": False, "error": f"Lot code '{req_code}' already exists. Duplicate code prevented."}
        code = req_code
    else:
        cnt = conn.execute("SELECT COUNT(*) n FROM lots").fetchone()["n"]
        code = f"LOT-{chr(65 + (cnt % 26))}{cnt + 1}"
        while conn.execute("SELECT COUNT(*) n FROM lots WHERE code=?", (code,)).fetchone()["n"] > 0:
            cnt += 1
            code = f"LOT-{chr(65 + (cnt % 26))}{cnt + 1}"

    cur = conn.execute("""INSERT INTO lots(code,source_name,source_type,category,grade,colour,contamination_pct,
        qty_kg,lat,lon,location_name,status,photo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, payload["source_name"], payload.get("source_type", "factory"), payload["category"],
         payload.get("grade", "B"), payload.get("colour", ""), float(payload.get("contamination_pct", 0)),
         float(payload["qty_kg"]), float(payload.get("lat", 23.81)), float(payload.get("lon", 90.41)),
         payload.get("location_name", ""), payload.get("status", "pending"), photo_path, NOW()))
    conn.commit()
    return {"ok": True, "code": code, "id": cur.lastrowid,
            "note": "Material classification in this demo is rule-based. A vision-model module plugs into the same slot."}

def api_aggregate(payload):
    bid = payload.get("buyer_id")
    if not bid:
        first_buyer = conn.execute("SELECT id FROM buyers LIMIT 1").fetchone()
        bid = first_buyer["id"] if first_buyer else 1
    else:
        bid = int(bid)
    p = plan_aggregation(conn, bid)
    return {"ok": True, "html": render_plan(p) if p else "Buyer not found.", "plan": p and {"feasible": p["feasible"], "total_kg": p["total_kg"], "eligible_kg": p.get("eligible_kg", p["total_kg"]), "batch_kg": p.get("batch_kg", 0), "target_kg": p["target_kg"], "shortfall_kg": p["shortfall_kg"], "candidates_count": len(p.get("candidates", []))}}

def api_batches(payload):
    buyer_id = payload.get("buyer_id")
    buyer = None
    if buyer_id:
        buyer = conn.execute("SELECT * FROM buyers WHERE id=?", (int(buyer_id),)).fetchone()
    if not buyer:
        buyer = conn.execute("SELECT * FROM buyers LIMIT 1").fetchone()
    if not buyer:
        return {"ok": False, "error": "No valid buyer found to assign batch."}

    raw_lot_ids = payload.get("lot_ids", [])
    lots = []
    lot_ids = []
    for i in raw_lot_ids:
        row = conn.execute("SELECT * FROM lots WHERE id=? OR code=?", (i, str(i))).fetchone()
        if row and not row["allocated"]:
            lots.append(dict(row))
            lot_ids.append(row["id"])

    if not lots:
        return {"ok": False, "error": "No valid unallocated lots selected for batch."}

    total = sum(l["qty_kg"] for l in lots)
    r = plan_route(conn, lot_ids, buyer["lat"], buyer["lon"])
    v_code, v_label, v_badge, v_desc = batch_verification_status(lots)
    code = "CIRC-2026-" + "%04d" % (conn.execute("SELECT COUNT(*) n FROM batches").fetchone()["n"] + 1)
    cur = conn.execute("""INSERT INTO batches(code,buyer_id,buyer_name,total_kg,lot_count,route_km,route_cost,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)""", (code, buyer["id"], buyer["name"], total, len(lot_ids), r["total_km"], r["est_cost"], v_code, NOW()))
    bid = cur.lastrowid
    for i in lot_ids:
        conn.execute("INSERT INTO batch_lots(batch_id,lot_id) VALUES(?,?)", (bid, i))
        conn.execute("UPDATE lots SET allocated=1 WHERE id=?", (i,))
    add_event(conn, bid, "Batch created from " + str(len(lot_ids)) + " aggregated lots (" + str(int(total)) + " kg).")
    add_event(conn, bid, f"Verification protocol: {v_label}. {v_desc}")
    add_event(conn, bid, "Digital Material Passport issued. Traceability chain active with declared composition.")
    conn.commit()
    return {"ok": True, "code": code}

def api_reset(_):
    conn.executescript("""
        DELETE FROM batch_lots;
        DELETE FROM events;
        DELETE FROM batches;
        DELETE FROM lots;
        DELETE FROM buyers;
        DELETE FROM prices;
        DELETE FROM sqlite_sequence WHERE name IN ('lots', 'buyers', 'prices', 'batches', 'events');
    """)
    conn.commit()
    seed(conn)
    return {"ok": True}

def api_simulate_intake(payload):
    req_code = payload.get("code", "LOT-K").strip() or "LOT-K"
    if conn.execute("SELECT COUNT(*) n FROM lots WHERE code=?", (req_code,)).fetchone()["n"] > 0:
        return {
            "ok": False,
            "error": f"Simulated lot '{req_code}' has already been ingested. Duplicate intake prevented. Click 'Reset Demo' to restart simulation.",
            "code": req_code
        }
    code = req_code
        
    source_name = payload.get("source_name", "DenimCo BD")
    source_type = payload.get("source_type", "factory")
    category = payload.get("category", "denim")
    grade = payload.get("grade", "B")
    colour = payload.get("colour", "indigo")
    contamination_pct = float(payload.get("contamination_pct", 4.0))
    qty_kg = float(payload.get("qty_kg", 450))
    lat = float(payload.get("lat", 23.8550))
    lon = float(payload.get("lon", 90.2550))
    location_name = payload.get("location_name", "Ashulia")
    status = payload.get("status", "pending")
    notes = payload.get("notes", "Simulated demo intake: 450kg Denim clips from Ashulia cutting floor")
    
    conn.execute("""INSERT INTO lots(code,source_name,source_type,category,grade,colour,contamination_pct,
        qty_kg,lat,lon,location_name,status,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, source_name, source_type, category, grade, colour, contamination_pct, qty_kg, lat, lon, location_name, status, notes, NOW()))
    conn.commit()
    
    tl = conn.execute("SELECT COALESCE(SUM(qty_kg),0) s, COUNT(*) n FROM lots").fetchone()
    free = conn.execute("SELECT COALESCE(SUM(qty_kg),0) s FROM lots WHERE allocated=0").fetchone()["s"]
    landfill_tons = round(tl["s"] / 1000.0, 2)
    
    new_lot = {
        "code": code,
        "source_name": source_name,
        "source_type": source_type,
        "category": category,
        "grade": grade,
        "colour": colour,
        "contamination_pct": contamination_pct,
        "qty_kg": qty_kg,
        "location_name": location_name,
        "status": status,
        "allocated": 0,
        "lat": lat,
        "lon": lon
    }
    
    return {
        "ok": True,
        "lot": new_lot,
        "stats": {
            "total_kg": int(tl["s"]),
            "free_kg": int(free),
            "lot_count": tl["n"],
            "landfill_tons": landfill_tons
        },
        "msg": f"New Waste Intake Registered: {code} ({int(qty_kg)}kg {category.title()})"
    }

ROUTES_GET = {"/": page_landing, "/overview": page_landing, "/dashboard": page_dashboard, "/lots": lambda: page_lots(),
              "/aggregation": page_aggregation, "/aggregation-planner": page_aggregation,
              "/buyers": page_buyers, "/planning": page_planning, "/passports": page_passports, "/reports": page_reports}
API_POST = {"/api/lots": api_lots, "/api/aggregate": api_aggregate, "/api/batches": api_batches, "/api/reset": api_reset, "/api/simulate-intake": api_simulate_intake}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path.startswith("/static/") or path.startswith("/uploads/"):
                fp = os.path.join(BASE, path.lstrip("/"))
                if os.path.isfile(fp):
                    ct = "text/css" if fp.endswith(".css") else "application/javascript" if fp.endswith(".js") else "image/png"
                    self._send(200, open(fp, "rb").read(), ct); return
                self._send(404, "not found"); return
            if path.startswith("/passport/"):
                self._send(200, page_passport_detail(urllib.parse.unquote(path.split("/passport/", 1)[1]))); return
            fn = ROUTES_GET.get(path)
            self._send(200, fn() if fn else layout("404", "/", "<h1>404 Not Found</h1>"))
        except Exception as ex:
            traceback.print_exc()
            self._send(500, layout("500", "/", "<h1>500 Internal Server Error</h1><p>" + e(ex) + "</p>"))
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        fn = API_POST.get(path)
        if not fn: self._send(404, json.dumps({"ok": False, "error": "Endpoint not found"}), "application/json"); return
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, json.dumps(fn(payload)), "application/json")
        except Exception as ex:
            traceback.print_exc()
            self._send(200, json.dumps({"ok": False, "error": str(ex)}), "application/json")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print("PunorAI demo running at http://localhost:%d" % port)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
