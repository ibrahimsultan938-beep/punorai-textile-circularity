# ==============================================================================
# PUNORAI — BUYER WORKSPACE (PROCUREMENT PLATFORM) MODULE
# ==============================================================================
import base64
import datetime
import html
import json
import math
import os
import re
import secrets
import sqlite3
import urllib.parse

import auth
import core
from brand import render_brand_logo, BrandLogo

def e(x):
    """HTML escape helper."""
    return html.escape(str(x) if x is not None else "")

def get_user_initials(name_or_org: str) -> str:
    """Generates two-letter uppercase initials from user name or organization."""
    if not name_or_org:
        return "JD"
    parts = [p for p in name_or_org.strip().split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    elif len(parts) == 1 and len(parts[0]) == 1:
        return (parts[0][0] + "B").upper()
    return "JD"

def get_lot_photo_url(lot) -> str:
    """Returns appropriate photograph URL for lot based on photo column or category."""
    photo = lot["photo"] if (hasattr(lot, "keys") and "photo" in lot.keys()) else ""
    if photo:
        return photo
    cat = (lot["category"] if (hasattr(lot, "keys") and "category" in lot.keys()) else "") or ""
    cat = str(cat).lower()
    if "cotton" in cat and "blend" not in cat:
        return "/static/lot_cotton.jpg"
    elif "denim" in cat:
        return "/static/lot_denim.jpg"
    elif "polyester" in cat or "blend" in cat or "mixed" in cat:
        return "/static/lot_mixed.jpg"
    return "/static/hero_roll_crop.jpg"

def get_buyer_stats(conn, user: dict) -> dict:
    """
    Computes real database-derived statistics for the Buyer Workspace.
    Respects verified and available lots, remaining quantity, and buyer's transactions.
    """
    user_id = user["id"]
    cursor = conn.cursor()

    # 1. Total available approved waste lots
    cursor.execute("""
        SELECT
            COUNT(*) as available_lots,
            COALESCE(SUM(qty_kg), 0.0) as available_kg,
            COUNT(DISTINCT source_name) as verified_suppliers
        FROM lots
        WHERE status = 'verified' AND allocated = 0
    """)
    avail_row = cursor.fetchone()
    avail_lots = avail_row[0] if avail_row else 0
    avail_kg = avail_row[1] if avail_row else 0.0
    verified_suppliers = avail_row[2] if avail_row else 0

    # 2. Total platform verified waste diverted / CO2 saved (2.8 kg CO2 per kg textile diverted)
    cursor.execute("""
        SELECT COALESCE(SUM(qty_kg), 0.0)
        FROM lots
        WHERE status = 'verified'
    """)
    tot_verified_kg = cursor.fetchone()[0] or 0.0
    co2_saved_t = (tot_verified_kg * 2.8) / 1000.0

    # 3. Buyer's own purchase requests
    cursor.execute("""
        SELECT
            COUNT(*) as total_requests,
            COUNT(CASE WHEN status = 'pending_admin' THEN 1 END) as pending_requests,
            COUNT(CASE WHEN status = 'admin_approved' THEN 1 END) as approved_requests,
            COUNT(CASE WHEN status = 'fulfilled' THEN 1 END) as fulfilled_requests,
            COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_requests,
            COALESCE(SUM(requested_qty_kg), 0.0) as total_requested_kg
        FROM purchase_requests
        WHERE buyer_id = ?
    """, (user_id,))
    pr_row = cursor.fetchone()
    total_requests = pr_row[0] if pr_row else 0
    pending_requests = pr_row[1] if pr_row else 0
    approved_requests = pr_row[2] if pr_row else 0
    fulfilled_requests = pr_row[3] if pr_row else 0
    rejected_requests = pr_row[4] if pr_row else 0
    total_requested_kg = pr_row[5] if pr_row else 0.0

    # 4. Buyer's completed transactions (Purchased Material & Spend)
    cursor.execute("""
        SELECT
            COUNT(*) as total_orders,
            COALESCE(SUM(qty_kg), 0.0) as purchased_kg,
            COALESCE(SUM(total_amount), 0.0) as total_spend,
            COUNT(CASE WHEN handover_status = 'completed' THEN 1 END) as completed_orders
        FROM transactions
        WHERE buyer_id = ? AND handover_status = 'completed'
    """, (user_id,))
    tx_row = cursor.fetchone()
    total_orders = tx_row[0] if tx_row else 0
    purchased_kg = tx_row[1] if tx_row else 0.0
    total_spend = tx_row[2] if tx_row else 0.0
    completed_orders = tx_row[3] if tx_row else 0

    # Buyer personal CO2 saved from circular purchases (illustrative estimate: 2.8 kg CO2e / kg textile)
    buyer_co2_kg = purchased_kg * 2.8

    # Dynamic impact percentage: ratio of fulfilled circular purchases to total requested material
    if total_requested_kg > 0:
        impact_pct = min(100, int(round((purchased_kg / total_requested_kg) * 100.0)))
    else:
        impact_pct = 0

    # 5. Saved lots count
    cursor.execute("SELECT COUNT(*) FROM saved_lots WHERE user_id = ?", (user_id,))
    saved_count = cursor.fetchone()[0] or 0

    # 6. Passports count for buyer
    cursor.execute("""
        SELECT COUNT(DISTINCT passport_code)
        FROM transactions
        WHERE buyer_id = ? AND passport_code != ''
    """, (user_id,))
    passports_count = cursor.fetchone()[0] or 0

    # 7. Scoped procurement notifications for authenticated buyer
    notifications = []
    cursor.execute("""
        SELECT code, status, requested_qty_kg, updated_at
        FROM purchase_requests
        WHERE buyer_id = ?
        ORDER BY id DESC LIMIT 2
    """, (user_id,))
    for pr_n in cursor.fetchall():
        pr_c, pr_s, pr_q, pr_t = pr_n[0], pr_n[1], pr_n[2], pr_n[3]
        if pr_s == "admin_approved":
            notifications.append({
                "title": f"Purchase Request {pr_c} approved by Admin",
                "time": f"{pr_t} &bull; {pr_q:,.0f} kg approved for allocation",
                "color": "green",
                "unread": True
            })
        elif pr_s == "fulfilled":
            notifications.append({
                "title": f"Order for Request {pr_c} completed",
                "time": f"{pr_t} &bull; Handover completed",
                "color": "cyan",
                "unread": False
            })
        elif pr_s == "pending_admin":
            notifications.append({
                "title": f"Purchase Request {pr_c} submitted",
                "time": f"{pr_t} &bull; Awaiting Admin verification",
                "color": "amber",
                "unread": False
            })
        elif pr_s == "rejected":
            notifications.append({
                "title": f"Purchase Request {pr_c} rejected",
                "time": f"{pr_t} &bull; Check notes in requests ledger",
                "color": "red",
                "unread": True
            })

    # Latest verified lot on the platform
    cursor.execute("""
        SELECT code, category, qty_kg, location_name
        FROM lots
        WHERE status = 'verified' AND allocated = 0
        ORDER BY id DESC LIMIT 1
    """,)
    latest_lot = cursor.fetchone()
    if latest_lot:
        notifications.append({
            "title": f"New verified {latest_lot[1].title()} lot {latest_lot[0]} in {latest_lot[3]}",
            "time": f"Available now &bull; {latest_lot[2]:,.0f} kg",
            "color": "cyan",
            "unread": True
        })

    if not notifications:
        notifications.append({
            "title": "Welcome to PunorAI Circular Procurement Hub",
            "time": "System &bull; Real-time verified textile inventory",
            "color": "green",
            "unread": False
        })
        notifications.append({
            "title": "Digital Material Passports Active",
            "time": "System &bull; Verifiable circular batch traceability",
            "color": "cyan",
            "unread": False
        })

    return {
        "available_lots": avail_lots,
        "available_kg": avail_kg,
        "available_mt": avail_kg / 1000.0,
        "verified_suppliers": verified_suppliers,
        "co2_saved_t": co2_saved_t,
        "total_requests": total_requests,
        "total_requested_kg": total_requested_kg,
        "pending_requests": pending_requests,
        "approved_requests": approved_requests,
        "fulfilled_requests": fulfilled_requests,
        "rejected_requests": rejected_requests,
        "total_orders": total_orders,
        "purchased_kg": purchased_kg,
        "purchased_mt": purchased_kg / 1000.0,
        "total_spend": total_spend,
        "completed_orders": completed_orders,
        "buyer_co2_kg": buyer_co2_kg,
        "impact_pct": impact_pct,
        "saved_count": saved_count,
        "passports_count": passports_count,
        "notifications": notifications
    }

def render_buyer_sparkline_svg(color="#10B981", trend_type="lots") -> str:
    """Renders a sleek SVG mini sparkline matching the reference design."""
    paths = {
        "lots": "M 0 24 C 20 22, 35 14, 55 16 C 75 18, 90 8, 110 5",
        "material": "M 0 25 C 25 24, 45 16, 65 19 C 85 22, 95 10, 110 4",
        "suppliers": "M 0 26 C 20 25, 40 18, 60 17 C 80 16, 95 9, 110 6",
        "co2": "M 0 25 C 20 23, 40 15, 60 17 C 80 19, 95 11, 110 5"
    }
    path_d = paths.get(trend_type, paths["lots"])
    fill_d = f"{path_d} L 110 32 L 0 32 Z"
    return f"""
    <div class="buyer-sparkline-box">
      <svg width="110" height="32" viewBox="0 0 110 32" fill="none" preserveAspectRatio="none">
        <defs>
          <linearGradient id="bgrad_{trend_type}" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="{color}" stop-opacity="0.0"/>
          </linearGradient>
        </defs>
        <path d="{fill_d}" fill="url(#bgrad_{trend_type})"/>
        <path d="{path_d}" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    """

def render_impact_gauge_svg(percent: int = 72) -> str:
    """
    Renders the circular impact gauge SVG matching the reference design.
    """
    radius = 42
    circumference = 2 * math.pi * radius
    offset = circumference - (percent / 100.0) * circumference
    return f"""
    <div class="buyer-gauge-wrapper">
      <svg width="110" height="110" viewBox="0 0 100 100" class="buyer-gauge-svg">
        <circle cx="50" cy="50" r="{radius}" class="buyer-gauge-track"/>
        <circle cx="50" cy="50" r="{radius}" class="buyer-gauge-bar"
                stroke-dasharray="{circumference:.2f}"
                stroke-dashoffset="{offset:.2f}"
                stroke-linecap="round"
                transform="rotate(-90 50 50)"/>
        <text x="50" y="55" class="buyer-gauge-text">{percent}%</text>
      </svg>
    </div>
    """

def require_buyer(handler, conn):
    """
    Role-based authentication enforcement for Buyer Workspace.
    Redirects unauthenticated users to /login?redirect=/buyer.
    Renders 403 Access Denied if authenticated user is not a Buyer.
    """
    sess_id = auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None
    user, csrf = auth.get_session_and_user(conn, sess_id)
    if not user:
        handler._redirect("/login?role=buyer&redirect=" + urllib.parse.quote(handler.path))
        return None, None
    if user["role"] != "buyer":
        # Strictly prevent non-buyer accounts from accessing buyer platform
        body = f"""
        <div class="buyer-app-layout" style="min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #070e0b; padding: 24px;">
          <div style="max-width: 540px; width: 100%; background: #0d1a15; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 16px; padding: 40px 32px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.5);">
            <div style="width: 64px; height: 64px; background: rgba(239, 68, 68, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; border: 1px solid rgba(239, 68, 68, 0.3);">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2.2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <h2 style="color: #FFFFFF; font-size: 22px; font-weight: 700; margin-bottom: 12px;">Access Denied — Buyer Role Required</h2>
            <p style="color: #94A3B8; font-size: 14.5px; line-height: 1.6; margin-bottom: 24px;">
              Your account <strong>{e(user['email'])}</strong> is signed in as a <span style="text-transform: capitalize; color: #10B981; font-weight: 600;">{e(user['role'])}</span>.
              The Procurement Workspace is reserved exclusively for verified Buyer organizations.
            </p>
            <div style="display: flex; gap: 12px; justify-content: center;">
              <a href="/{e(user['role'])}" class="buyer-btn-primary" style="text-decoration: none; padding: 10px 24px;">Go to Your {e(user['role'].title())} Workspace</a>
              <a href="/logout" class="buyer-btn-outline" style="text-decoration: none; padding: 10px 20px;">Sign Out</a>
            </div>
          </div>
        </div>
        """
        handler._send(403, f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Access Denied — PunorAI</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="buyer-platform-body">{body}</body>
</html>""")
        return None, None
    return user, csrf

# ==============================================================================
# BUYER PLATFORM LAYOUT SHELL
# ==============================================================================

def buyer_layout(title: str, active: str, body: str, user: dict, counts: dict = None, csrf_token: str = "") -> str:
    """
    Dedicated layout template for the PunorAI Buyer Workspace.
    Follows the reference design (media_1793871909160_2875c040.jpg):
    - Dark black-green emerald visual theme
    - Dedicated Buyer sidebar with 7 items
    - Topbar with Search (Ctrl+K), Notification bell, Bangladesh flag, User Profile pill
    - Bottom promotional banner
    - Responsive mobile drawer and modals
    """
    counts = counts or {}
    req_badge_val = counts.get("pending_requests", 2)
    saved_badge_val = counts.get("saved_count", 0)

    # User display details - strictly dynamic per authenticated account
    org_name = user.get("org_name") or "Buyer Organization"
    contact_name = user.get("contact_name") or ""
    display_name = contact_name if contact_name else (org_name if org_name else "Buyer")
    initials = get_user_initials(display_name)
    user_email = user.get("email", "")

    # Navigation items (7 items per specification)
    nav_items = [
        {"id": "dashboard", "url": "/buyer", "label": "My Dashboard", "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>"""},
        {"id": "materials", "url": "/buyer/materials", "label": "Browse Materials", "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>"""},
        {"id": "saved", "url": "/buyer/saved", "label": "Saved Lots", "badge": str(saved_badge_val) if saved_badge_val > 0 else None, "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>"""},
        {"id": "requests", "url": "/buyer/requests", "label": "Purchase Requests", "badge": str(req_badge_val) if req_badge_val > 0 else None, "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>"""},
        {"id": "orders", "url": "/buyer/orders", "label": "My Orders", "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>"""},
        {"id": "passports", "url": "/buyer/passports", "label": "Material Passports", "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>"""},
        {"id": "settings", "url": "/buyer/settings", "label": "Account Settings", "icon": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>"""}
    ]

    nav_links_html = []
    for item in nav_items:
        is_active = (active == item["id"])
        cls = "buyer-nav-item active" if is_active else "buyer-nav-item"
        badge_html = f'<span class="buyer-nav-badge">{e(item["badge"])}</span>' if item.get("badge") else ""
        nav_links_html.append(f"""
          <a href="{item['url']}" class="{cls}">
            <span class="buyer-nav-icon">{item['icon']}</span>
            <span class="buyer-nav-text">{e(item['label'])}</span>
            {badge_html}
          </a>
        """)

    nav_rendered = "\n".join(nav_links_html)

    # Dynamic notifications scoped to logged-in user
    notifs = counts.get("notifications", []) if isinstance(counts, dict) else []
    notif_pill_count = max(1, len(notifs))
    notifs_html = []
    for n in notifs:
        unr_cls = "unread" if n.get("unread", False) else ""
        color = n.get("color", "green")
        notifs_html.append(f'''
                <div class="buyer-notif-item {unr_cls}">
                  <span class="buyer-notif-dot {color}"></span>
                  <div class="buyer-notif-info">
                    <div class="buyer-notif-title">{e(n.get("title", ""))}</div>
                    <div class="buyer-notif-time">{n.get("time", "")}</div>
                  </div>
                </div>
        ''')
    notifs_rendered = "\n".join(notifs_html)

    brand_logo_html = render_brand_logo(
        href="/buyer",
        size=26,
        extra_class="buyer-brand-link",
        id_prefix="buyer"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{e(title)} — PunorAI Buyer Platform</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <meta name="csrf-token" content="{e(csrf_token)}">
</head>
<body class="buyer-platform-body">
  <div class="buyer-app-layout">
    <!-- DEDICATED BUYER SIDEBAR -->
    <aside class="buyer-sidebar" id="buyerSidebar">
      <!-- BRAND LOGO -->
      <div class="buyer-sidebar-header">
        {brand_logo_html}
      </div>

      <!-- USER PROFILE CARD -->
      <div class="buyer-user-card">
        <div class="buyer-user-avatar">
          <span>{e(initials)}</span>
          <span class="buyer-online-status" title="Active Buyer Session"></span>
        </div>
        <div class="buyer-user-info">
          <div class="buyer-user-name" title="{e(display_name)}">{e(display_name)}</div>
          <div class="buyer-user-role">
            <span>Buyer</span>
            <span class="verified-check" title="Verified Buyer">✔</span>
          </div>
        </div>
      </div>

      <!-- 7 SIDEBAR NAVIGATION ITEMS -->
      <nav class="buyer-nav-list">
        {nav_rendered}
      </nav>

      <!-- SIDEBAR FOOTER -->
      <div class="buyer-sidebar-footer">
        <!-- TOGETHER FOR A GREENER BANGLADESH CARD -->
        <div class="buyer-eco-card">
          <div class="buyer-eco-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <div class="buyer-eco-title">Better Waste Management</div>
          <div class="buyer-eco-sub">Together for a Greener Bangladesh</div>
          <div class="buyer-eco-visual">
            <svg width="100%" height="40" viewBox="0 0 160 40" fill="none">
              <path d="M0 40 L0 32 Q 40 20, 80 30 T 160 22 L 160 40 Z" fill="rgba(16, 185, 129, 0.22)"/>
              <path d="M0 40 L0 36 Q 40 28, 80 34 T 160 30 L 160 40 Z" fill="rgba(0, 229, 153, 0.3)"/>
              <circle cx="120" cy="18" r="4" fill="#00E599"/>
              <path d="M120 18 L124 10 L128 18 Z" fill="#10B981"/>
            </svg>
          </div>
        </div>

        <!-- LOGOUT BUTTON -->
        <a href="/logout" class="buyer-logout-btn">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          <span>Logout</span>
        </a>
      </div>
    </aside>

    <!-- MAIN VIEWPORT CONTAINER -->
    <div class="buyer-viewport">
      <!-- TOPBAR -->
      <header class="buyer-topbar">
        <div class="buyer-topbar-left">
          <button class="buyer-mobile-toggle" id="buyerMobileToggle" aria-label="Toggle Navigation">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
          <!-- GLOBAL SEARCH INPUT WITH SHORTCUT -->
          <div class="buyer-search-wrapper" onclick="openSearchPalette()">
            <svg class="buyer-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <span class="buyer-search-placeholder">Search for materials, types, or suppliers...</span>
            <kbd class="buyer-search-badge">Ctrl + K</kbd>
          </div>
        </div>

        <div class="buyer-topbar-right">
          <!-- NOTIFICATIONS BELL -->
          <div class="buyer-notif-container">
            <button class="buyer-icon-btn" id="notifBellBtn" onclick="toggleNotifDropdown()" title="Notifications">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
              <span class="buyer-notif-pill">{notif_pill_count}</span>
            </button>
            <div class="buyer-notif-dropdown" id="notifDropdown">
              <div class="buyer-notif-header">
                <span>Procurement Notifications</span>
                <span class="buyer-notif-mark">{len(notifs)} Available</span>
              </div>
              <div class="buyer-notif-list">
                {notifs_rendered}
              </div>
            </div>
          </div>

          <!-- BANGLADESH COUNTRY PILL (FROM REFERENCE DESIGN) -->
          <div class="buyer-country-pill" title="Procurement Hub: Bangladesh">
            <span class="buyer-flag-icon">
              <svg width="18" height="18" viewBox="0 0 32 32">
                <rect width="32" height="32" rx="16" fill="#006A4E"/>
                <circle cx="14" cy="16" r="7" fill="#F42A41"/>
              </svg>
            </span>
            <span class="buyer-country-name">Bangladesh</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          </div>

          <!-- BUYER PROFILE PILL -->
          <div class="buyer-profile-container">
            <button class="buyer-profile-pill" onclick="toggleProfileDropdown()">
              <div class="buyer-pill-avatar">{e(initials)}</div>
              <div class="buyer-pill-details">
                <span class="buyer-pill-name">{e(display_name)}</span>
                <span class="buyer-pill-sub">Buyer</span>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="buyer-profile-dropdown" id="profileDropdown">
              <div class="buyer-profile-header">
                <strong>{e(org_name)}</strong>
                <small>{e(user_email)}</small>
              </div>
              <a href="/buyer/settings" class="buyer-profile-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                <span>Account & Hub Settings</span>
              </a>
              <a href="/buyer/requests" class="buyer-profile-item">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>
                <span>My Purchase Requests</span>
              </a>
              <div style="height: 1px; background: rgba(255,255,255,0.08); margin: 6px 0;"></div>
              <a href="/logout" class="buyer-profile-item" style="color: #EF4444;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                <span>Sign Out</span>
              </a>
            </div>
          </div>
        </div>
      </header>

      <!-- MAIN SCROLLABLE CONTENT BODY -->
      <main class="buyer-main-content">
        {body}
      </main>
    </div>
  </div>

  <!-- SEARCH / COMMAND PALETTE MODAL (CTRL+K) -->
  <div class="buyer-palette-modal" id="searchPaletteModal" onclick="closePaletteOnBackdrop(event)">
    <div class="buyer-palette-card">
      <div class="buyer-palette-header">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="paletteSearchInput" placeholder="Quick jump or search verified materials, suppliers, requests..." onkeyup="filterPalette(this.value)">
        <kbd onclick="closeSearchPalette()">ESC</kbd>
      </div>
      <div class="buyer-palette-results" id="paletteResults">
        <a href="/buyer/materials" class="buyer-palette-item">
          <div class="buyer-palette-label">Browse All Available Materials</div>
          <div class="buyer-palette-meta">Explore verified waste inventory</div>
        </a>
        <a href="/buyer/materials?category=cotton" class="buyer-palette-item">
          <div class="buyer-palette-label">Cotton Waste Lots</div>
          <div class="buyer-palette-meta">Filter by Cotton fiber waste</div>
        </a>
        <a href="/buyer/materials?category=denim" class="buyer-palette-item">
          <div class="buyer-palette-label">Denim Fabric Scrap</div>
          <div class="buyer-palette-meta">Filter by Denim waste lots</div>
        </a>
        <a href="/buyer/saved" class="buyer-palette-item">
          <div class="buyer-palette-label">Saved Lots (Bookmarks)</div>
          <div class="buyer-palette-meta">View lots bookmarked for later</div>
        </a>
        <a href="/buyer/requests" class="buyer-palette-item">
          <div class="buyer-palette-label">My Purchase Requests</div>
          <div class="buyer-palette-meta">Track pending admin reviews</div>
        </a>
        <a href="/buyer/orders" class="buyer-palette-item">
          <div class="buyer-palette-label">My Orders & Handover</div>
          <div class="buyer-palette-meta">View active & completed transactions</div>
        </a>
        <a href="/buyer/passports" class="buyer-palette-item">
          <div class="buyer-palette-label">Material Passports</div>
          <div class="buyer-palette-meta">Digital Product Passports & circular QR</div>
        </a>
      </div>
    </div>
  </div>

  <!-- TOAST NOTIFICATION CONTAINER -->
  <div class="buyer-toast" id="buyerToast"></div>

  <!-- GLOBAL CLIENT JS ENGINE -->
  <script>
    // Mobile Drawer Toggle
    const mobileBtn = document.getElementById('buyerMobileToggle');
    const sidebar = document.getElementById('buyerSidebar');
    if (mobileBtn && sidebar) {{
      mobileBtn.addEventListener('click', () => {{
        sidebar.classList.toggle('open');
      }});
    }}

    // Dropdowns Toggle
    function toggleNotifDropdown() {{
      const d = document.getElementById('notifDropdown');
      d.classList.toggle('open');
      document.getElementById('profileDropdown')?.classList.remove('open');
    }}
    function toggleProfileDropdown() {{
      const d = document.getElementById('profileDropdown');
      d.classList.toggle('open');
      document.getElementById('notifDropdown')?.classList.remove('open');
    }}
    document.addEventListener('click', (e) => {{
      if (!e.target.closest('.buyer-notif-container')) {{
        document.getElementById('notifDropdown')?.classList.remove('open');
      }}
      if (!e.target.closest('.buyer-profile-container')) {{
        document.getElementById('profileDropdown')?.classList.remove('open');
      }}
    }});

    // Command Palette (Ctrl+K)
    function openSearchPalette() {{
      const m = document.getElementById('searchPaletteModal');
      m.classList.add('open');
      const inp = document.getElementById('paletteSearchInput');
      setTimeout(() => inp.focus(), 50);
    }}
    function closeSearchPalette() {{
      document.getElementById('searchPaletteModal').classList.remove('open');
    }}
    function closePaletteOnBackdrop(e) {{
      if (e.target.id === 'searchPaletteModal') closeSearchPalette();
    }}
    document.addEventListener('keydown', (e) => {{
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {{
        e.preventDefault();
        openSearchPalette();
      }}
      if (e.key === 'Escape') {{
        closeSearchPalette();
        closeModal();
      }}
    }});

    function filterPalette(q) {{
      q = q.toLowerCase();
      const items = document.querySelectorAll('.buyer-palette-item');
      items.forEach(el => {{
        const text = el.innerText.toLowerCase();
        el.style.display = text.includes(q) ? 'flex' : 'none';
      }});
    }}

    // Toast Messenger
    function showToast(msg, type='success') {{
      const t = document.getElementById('buyerToast');
      t.innerText = msg;
      t.className = 'buyer-toast show ' + type;
      setTimeout(() => {{ t.className = 'buyer-toast'; }}, 3500);
    }}

    // Generic Modal Closer
    function closeModal() {{
      const backdrops = document.querySelectorAll('.buyer-modal-backdrop');
      backdrops.forEach(b => b.classList.remove('open'));
    }}

    // CSRF Token Helper
    function getCsrfToken() {{
      return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }}

    // Bookmark Toggle Helper
    async function toggleBookmark(lotId, btnEl) {{
      try {{
        const res = await fetch('/api/buyer/saved/toggle', {{
          method: 'POST',
          headers: {{
            'Content-Type': 'application/json',
            'X-CSRF-Token': getCsrfToken()
          }},
          body: JSON.stringify({{ lot_id: lotId }})
        }});
        const data = await res.json();
        if (data.ok) {{
          showToast(data.saved ? 'Lot saved to your bookmarks!' : 'Lot removed from bookmarks.', 'success');
          if (btnEl) {{
            if (data.saved) {{
              btnEl.classList.add('active');
              btnEl.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="#10B981" stroke="#10B981" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>';
            }} else {{
              btnEl.classList.remove('active');
              btnEl.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>';
            }}
          }}
        }} else {{
          showToast(data.error || 'Failed to update bookmark', 'error');
        }}
      }} catch (err) {{
        console.error(err);
        showToast('Network error updating bookmark', 'error');
      }}
    }}
  </script>
</body>
</html>"""

# ==============================================================================
# PAGE 1: BUYER DASHBOARD (/buyer)
# ==============================================================================

def page_buyer_dashboard(handler, conn) -> str:
    """
    Renders the dedicated Buyer Dashboard matching the reference design:
    - Hero banner: Clean textile warehouse photo visual (NO recycling symbol overlay, strictly following instructions)
    - 4 KPI Stat Cards: Available Lots, Total Available Material, Verified Suppliers, Estimated CO2 Saved
    - Browse Materials preview: 3 verified available lots, category chips filter bar, View All link
    - Your Impact circular progress gauge (72%)
    - Recent Purchase Requests table / list
    - Bottom promo card: "Together for a Circular Bangladesh"
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    stats = get_buyer_stats(conn, user)

    # Query 3 latest approved and available material lots for the preview
    cursor.execute("""
        SELECT id, code, source_name, source_type, category, grade, colour,
               contamination_pct, qty_kg, location_name, status, photo,
               asking_price_per_kg, created_at
        FROM lots
        WHERE status = 'verified' AND allocated = 0
        ORDER BY id DESC
        LIMIT 3
    """)
    preview_lots = cursor.fetchall()

    # Query saved lot IDs for this buyer to show active bookmark status
    cursor.execute("SELECT lot_id FROM saved_lots WHERE user_id = ?", (user["id"],))
    saved_lot_ids = {r[0] for r in cursor.fetchall()}

    # Build preview material cards HTML
    material_cards_html = []
    if preview_lots:
        for lot in preview_lots:
            lot_id = lot["id"]
            code = lot["code"]
            cat = (lot["category"] or "Textile Waste").title()
            grade = lot["grade"] or "A"
            qty_kg = lot["qty_kg"] or 0.0
            qty_str = f"{qty_kg/1000.0:.1f} MT" if qty_kg >= 1000 else f"{qty_kg:,.0f} kg"
            supplier = lot["source_name"] or "Verified Supplier"
            loc = lot["location_name"] or "Dhaka, BD"
            asking_price = lot["asking_price_per_kg"] or 0.0
            price_str = f"৳ {asking_price:,.0f}/kg (Approx.)" if asking_price > 0 else "Market Negotiable"
            photo_url = get_lot_photo_url(lot)
            is_saved = (lot_id in saved_lot_ids)

            bookmark_cls = "buyer-bookmark-btn active" if is_saved else "buyer-bookmark-btn"
            bookmark_icon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="#10B981" stroke="#10B981" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>' if is_saved else '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'

            # Display title matching reference (e.g., Cotton Waste - White Grade, Denim Fabric Waste, etc.)
            card_title = f"{cat} - Grade {grade}"
            if "cotton" in cat.lower():
                card_title = f"Cotton Waste — {lot['colour'].title()} Grade"
            elif "denim" in cat.lower():
                card_title = "Denim Fabric Waste"
            elif "mixed" in cat.lower() or "blend" in cat.lower():
                card_title = "Mixed Textile Waste"

            material_cards_html.append(f"""
            <div class="buyer-material-card">
              <div class="buyer-card-media">
                <img src="{e(photo_url)}" alt="{e(card_title)}" onerror="this.src='/static/hero_roll_crop.jpg'">
                <div class="buyer-verified-pill">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                  <span>Verified</span>
                </div>
                <button type="button" class="{bookmark_cls}" onclick="toggleBookmark({lot_id}, this)" title="Save Lot">
                  {bookmark_icon}
                </button>
              </div>
              <div class="buyer-card-content">
                <div class="buyer-card-title">{e(card_title)}</div>
                <div class="buyer-card-meta">
                  <span class="buyer-meta-item">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3l3 4 3-4"/></svg>
                    <span>{e(supplier)}</span>
                  </span>
                  <span class="buyer-meta-item">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                    <span>{e(loc)}</span>
                  </span>
                </div>
                <div class="buyer-specs-row">
                  <span class="buyer-spec-tag">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                    <span>{qty_str} Available</span>
                  </span>
                  <span class="buyer-spec-tag grade">
                    <span style="color: #F59E0B;">★</span> Grade {e(grade)}
                  </span>
                  <span class="buyer-spec-tag price">
                    {e(price_str)}
                  </span>
                </div>
                <div class="buyer-card-actions">
                  <button type="button" class="buyer-btn-card" onclick="openLotModal({lot_id})">
                    <span>View Details</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                  </button>
                  <button type="button" class="buyer-btn-card-save" onclick="toggleBookmark({lot_id}, this)">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                  </button>
                </div>
              </div>
            </div>
            """)
    else:
        material_cards_html.append("""
          <div style="grid-column: 1 / -1; padding: 40px; text-align: center; background: #0d1a15; border-radius: 12px; border: 1px dashed rgba(16, 185, 129, 0.3);">
            <div style="font-size: 32px; margin-bottom: 12px;">📦</div>
            <div style="color: #FFFFFF; font-size: 16px; font-weight: 600;">No Available Approved Lots Currently</div>
            <div style="color: #94A3B8; font-size: 13.5px; margin-top: 4px;">Check back soon as verified suppliers submit new batches daily.</div>
          </div>
        """)

    material_cards_rendered = "\n".join(material_cards_html)

    # Query recent purchase requests for this buyer
    cursor.execute("""
        SELECT pr.id, pr.code, pr.requested_qty_kg, pr.offered_price_per_kg, pr.status, pr.created_at,
               l.code as lot_code, l.category as lot_category, l.photo as lot_photo
        FROM purchase_requests pr
        JOIN lots l ON pr.lot_id = l.id
        WHERE pr.buyer_id = ?
        ORDER BY pr.id DESC
        LIMIT 3
    """, (user["id"],))
    recent_prs = cursor.fetchall()

    recent_prs_html = []
    if recent_prs:
        for pr in recent_prs:
            pr_code = pr["code"]
            pr_qty = pr["requested_qty_kg"]
            pr_status = pr["status"]
            pr_date = pr["created_at"]
            lot_cat = (pr["lot_category"] or "Textile").title()

            status_cls = "buyer-status-pill pending"
            status_text = "Pending"
            if pr_status == "admin_approved":
                status_cls = "buyer-status-pill approved"
                status_text = "Approved"
            elif pr_status == "fulfilled":
                status_cls = "buyer-status-pill completed"
                status_text = "Completed"
            elif pr_status == "rejected":
                status_cls = "buyer-status-pill rejected"
                status_text = "Rejected"

            lot_thumb = get_lot_photo_url({"photo": pr["lot_photo"], "category": pr["lot_category"]})
            recent_prs_html.append(f"""
            <div class="buyer-pr-row">
              <div class="buyer-pr-thumb">
                <img src="{lot_thumb}" alt="Waste Lot Thumbnail">
              </div>
              <div class="buyer-pr-info">
                <div class="buyer-pr-id">Request #{e(pr_code)}</div>
                <div class="buyer-pr-sub">{e(pr_date)} &bull; {pr_qty:,.0f} kg {e(lot_cat)}</div>
              </div>
              <div class="{status_cls}">{status_text}</div>
            </div>
            """)
    else:
        # Show realistic baseline preview items if no request records exist
        recent_prs_html.append("""
          <div style="padding: 24px 16px; text-align: center; color: #94A3B8; font-size: 13.5px;">
            No purchase requests submitted yet.<br>
            <a href="/buyer/materials" style="color: #10B981; font-weight: 600; text-decoration: underline; margin-top: 8px; display: inline-block;">Browse Approved Materials &rarr;</a>
          </div>
        """)

    recent_prs_rendered = "\n".join(recent_prs_html)

    # Format KPI values
    avail_lots_str = f"{stats['available_lots']}"
    avail_mt_str = f"{stats['available_mt']:.2f} MT" if stats['available_mt'] < 10 else f"{stats['available_mt']:,.1f} MT"
    suppliers_str = f"{stats['verified_suppliers']}"
    co2_str = f"{stats['co2_saved_t']:.1f} tCO₂" if stats['co2_saved_t'] > 0 else "Not yet calculated"

    # Donut gauge for circular contribution (dynamically derived from buyer's purchases vs requests)
    impact_pct = stats.get("impact_pct", 0)
    circular_gauge_html = render_impact_gauge_svg(impact_pct)
    if stats['purchased_kg'] > 0:
        impact_desc_html = f"Your circular procurement has fulfilled <strong>{impact_pct}%</strong> of requested textile waste ({stats['purchased_kg']:,.0f} kg diverted from landfill)."
    else:
        impact_desc_html = "No completed procurement yet. Browse approved lots and submit purchase requests to begin diverting textile waste." 

    body = f"""
    <!-- HERO BANNER -->
    <!-- HERO BANNER: Natural textile warehouse photograph background ONLY -->
    <div class="buyer-hero-banner">
      <div class="buyer-hero-bg-overlay"></div>
      <div class="buyer-hero-content">
        <div class="buyer-hero-tag">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
          <span>Buyer Platform</span>
        </div>
        <h1 class="buyer-hero-title">
          Find Verified Textile Waste.<br>
          Build a <span class="highlight-green">Sustainable Tomorrow.</span>
        </h1>
        <p class="buyer-hero-subtitle">
          Browse approved textile waste lots and contribute to a circular economy.
        </p>
        <div class="buyer-hero-action">
          <a href="/buyer/materials" class="buyer-btn-primary">
            <span>Browse Materials</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </a>
        </div>
      </div>
    </div>

    <!-- 4 KPI STAT METRIC CARDS -->
    <div class="buyer-stats-grid">
      <!-- Card 1: Available Lots -->
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{avail_lots_str}</div>
            <div class="buyer-stat-label">Available Lots</div>
          </div>
        </div>
        <div class="buyer-stat-chart">
          {render_buyer_sparkline_svg("#10B981", "lots")}
        </div>
      </div>

      <!-- Card 2: Total Available Material -->
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{avail_mt_str}</div>
            <div class="buyer-stat-label">Total Available Material</div>
          </div>
        </div>
        <div class="buyer-stat-chart">
          {render_buyer_sparkline_svg("#10B981", "material")}
        </div>
      </div>

      <!-- Card 3: Verified Suppliers -->
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3l3 4 3-4"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{suppliers_str}</div>
            <div class="buyer-stat-label">Verified Suppliers</div>
          </div>
        </div>
        <div class="buyer-stat-chart">
          {render_buyer_sparkline_svg("#10B981", "suppliers")}
        </div>
      </div>

      <!-- Card 4: Estimated CO2 Saved -->
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{co2_str}</div>
            <div class="buyer-stat-label">Estimated CO₂ Saved (Est.)*</div>
          </div>
        </div>
        <div class="buyer-stat-chart">
          {render_buyer_sparkline_svg("#10B981", "co2")}
        </div>
      </div>
    </div>

    <!-- MAIN TWO-COLUMN SPLIT GRID -->
    <div class="buyer-main-grid">
      <!-- LEFT COLUMN: BROWSE MATERIALS PREVIEW -->
      <div class="buyer-left-col">
        <div class="buyer-section-panel">
          <div class="buyer-panel-header">
            <div class="buyer-panel-title-group">
              <div class="buyer-panel-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              </div>
              <div>
                <h2 class="buyer-panel-title">Browse Materials</h2>
                <div class="buyer-panel-subtitle">Explore verified textile waste lots from trusted suppliers</div>
              </div>
            </div>
            <a href="/buyer/materials" class="buyer-link-more">
              <span>View All Materials</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </a>
          </div>

          <!-- MATERIAL CATEGORY FILTER BAR -->
          <div class="buyer-filter-bar">
            <div class="buyer-chip-group">
              <a href="/buyer/materials" class="buyer-chip active">All Materials</a>
              <a href="/buyer/materials?category=cotton" class="buyer-chip">Cotton</a>
              <a href="/buyer/materials?category=polyester" class="buyer-chip">Polyester</a>
              <a href="/buyer/materials?category=mixed" class="buyer-chip">Mixed Fiber</a>
              <a href="/buyer/materials?category=denim" class="buyer-chip">Denim</a>
            </div>
            <form action="/buyer/materials" method="GET" class="buyer-inline-filter-form">
              <input type="number" name="min_qty" placeholder="Min Quantity (kg)" class="buyer-filter-input">
              <select name="grade" class="buyer-filter-select">
                <option value="">Grade (All)</option>
                <option value="A">Grade A</option>
                <option value="B">Grade B</option>
                <option value="C">Grade C</option>
              </select>
              <button type="submit" class="buyer-btn-filter">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
                <span>Apply Filters</span>
              </button>
            </form>
          </div>

          <!-- 3 MATERIAL CARDS GRID -->
          <div class="buyer-materials-grid">
            {material_cards_rendered}
          </div>
        </div>
      </div>

      <!-- RIGHT COLUMN: YOUR IMPACT, RECENT REQUESTS, BOTTOM PROMO -->
      <div class="buyer-right-col">
        <!-- YOUR IMPACT PANEL -->
        <div class="buyer-section-panel buyer-impact-card">
          <div class="buyer-panel-header">
            <div class="buyer-panel-title-group">
              <div class="buyer-panel-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
              </div>
              <h3 class="buyer-panel-title" style="font-size: 16px;">Your Impact</h3>
            </div>
            <div class="buyer-year-badge">This Year ⌄</div>
          </div>
          <div class="buyer-impact-body">
            {circular_gauge_html}
            <div class="buyer-impact-desc">
              {impact_desc_html}
            </div>
            <div class="buyer-impact-metrics">
              <div class="buyer-impact-metric-item">
                <div class="metric-val">{stats['purchased_kg']:,.0f} kg</div>
                <div class="metric-lbl">Material Purchased</div>
              </div>
              <div class="buyer-impact-metric-item">
                <div class="metric-val">{stats['buyer_co2_kg']:.1f} kg</div>
                <div class="metric-lbl">CO₂ Avoided (Est.)*</div>
              </div>
            </div>
            <div class="buyer-impact-disclosure" style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.08); font-size: 11px; color: #64748B; line-height: 1.4;">
              * Preliminary illustrative estimate (~2.8 kg CO₂e / kg textile diverted). Uncertified estimation per ClimateSphere AI transparency standards; not an audited carbon credit.
            </div>
          </div>
        </div>

        <!-- RECENT PURCHASE REQUESTS PANEL -->
        <div class="buyer-section-panel">
          <div class="buyer-panel-header">
            <div class="buyer-panel-title-group">
              <div class="buyer-panel-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              </div>
              <h3 class="buyer-panel-title" style="font-size: 16px;">Recent Purchase Requests</h3>
            </div>
            <a href="/buyer/requests" class="buyer-link-more" style="font-size: 12px;">View All &rarr;</a>
          </div>
          <div class="buyer-recent-pr-list">
            {recent_prs_rendered}
          </div>
        </div>

        <!-- BOTTOM PROMO CARD -->
        <div class="buyer-bottom-promo-card">
          <div class="buyer-promo-leaf">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <div class="buyer-promo-content">
            <div class="buyer-promo-title">Together for a Circular Bangladesh</div>
            <div class="buyer-promo-sub">Let's turn textile waste into new possibilities.</div>
          </div>
          <a href="/buyer/materials" class="buyer-promo-btn" title="Procure Materials">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </a>
        </div>
      </div>
    </div>

    <!-- LOT DETAILS MODAL -->
    <div class="buyer-modal-backdrop" id="lotDetailModal" onclick="closeLotModalOnBackdrop(event)">
      <div class="buyer-modal-card">
        <div class="buyer-modal-header">
          <div>
            <div class="buyer-modal-title" id="mCode">LOT Details</div>
            <div class="buyer-modal-subtitle" id="mCat">Textile Waste Specification</div>
          </div>
          <button type="button" class="buyer-modal-close" onclick="closeModal()">&times;</button>
        </div>
        <div class="buyer-modal-body" id="mBody">
          <!-- Dynamically filled by JS -->
        </div>
        <div class="buyer-modal-footer">
          <button type="button" class="buyer-btn-outline" onclick="closeModal()">Close</button>
          <button type="button" class="buyer-btn-primary" id="mRequestBtn" onclick="openRequestFormModal()">
            <span>Submit Purchase Request</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- PURCHASE REQUEST FORM MODAL -->
    <div class="buyer-modal-backdrop" id="requestFormModal" onclick="closeRequestModalOnBackdrop(event)">
      <div class="buyer-modal-card" style="max-width: 520px;">
        <div class="buyer-modal-header">
          <div>
            <div class="buyer-modal-title">Submit Purchase Request</div>
            <div class="buyer-modal-subtitle" id="reqModalSubtitle">Procure verified textile waste</div>
          </div>
          <button type="button" class="buyer-modal-close" onclick="closeModal()">&times;</button>
        </div>
        <form id="purchaseRequestForm" onsubmit="submitPurchaseRequest(event)">
          <input type="hidden" id="reqLotId" name="lot_id" value="">
          <div class="buyer-modal-body">
            <div class="buyer-form-group">
              <label class="buyer-label">Selected Waste Lot</label>
              <input type="text" id="reqLotDisplay" class="buyer-input" readonly>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Available Inventory</label>
              <input type="text" id="reqLotAvail" class="buyer-input" readonly>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Requested Quantity (kg) <span class="req">*</span></label>
              <input type="number" id="reqQtyInput" name="requested_qty_kg" class="buyer-input" min="1" step="0.1" required placeholder="Enter quantity in kg" oninput="calculateRequestTotal()">
              <div class="buyer-hint">Must be greater than 0 and cannot exceed available lot quantity.</div>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Offered Price (BDT/kg)</label>
              <input type="number" id="reqPriceInput" name="offered_price_per_kg" class="buyer-input" step="0.5" placeholder="Suggested / offered price" oninput="calculateRequestTotal()">
              <div class="buyer-hint" id="reqTotalHint">Estimated total: ৳ 0</div>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Notes for Intake Admin & Supplier (Optional)</label>
              <textarea id="reqNotesInput" name="notes" class="buyer-textarea" rows="3" placeholder="Specify spinning requirement, pickup preference, or QA requirements..."></textarea>
            </div>
          </div>
          <div class="buyer-modal-footer">
            <button type="button" class="buyer-btn-outline" onclick="closeModal()">Cancel</button>
            <button type="submit" class="buyer-btn-primary" id="reqSubmitBtn">
              <span>Send Request to Admin</span>
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- DASHBOARD LOT & REQUEST SCRIPTS -->
    <script>
      let currentActiveLot = null;

      // Available lots catalog data stored in client for instant modal inspect
      const AVAILABLE_LOTS = {json.dumps({lot["id"]: dict(lot) for lot in preview_lots})};

      function openLotModal(lotId) {{
        const lot = AVAILABLE_LOTS[lotId];
        if (!lot) return;
        currentActiveLot = lot;

        document.getElementById('mCode').innerText = lot.code + ' — ' + (lot.category || '').toUpperCase();
        document.getElementById('mCat').innerText = 'Verified Supplier: ' + (lot.source_name || 'N/A') + ' (' + (lot.location_name || 'Dhaka') + ')';

        const asking = lot.asking_price_per_kg ? '৳ ' + lot.asking_price_per_kg + '/kg (Approx.)' : 'Market Negotiable';

        document.getElementById('mBody').innerHTML = `
          <div class="buyer-lot-specs-grid">
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Lot Code</div>
              <div class="spec-val">${{lot.code}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Available Quantity</div>
              <div class="spec-val highlight">${{Number(lot.qty_kg).toLocaleString()}} kg</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Category & Material</div>
              <div class="spec-val">${{lot.category || 'Textile'}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Quality Grade</div>
              <div class="spec-val">Grade ${{lot.grade || 'A'}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Colour</div>
              <div class="spec-val">${{lot.colour || 'N/A'}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Contamination Estimate</div>
              <div class="spec-val">${{lot.contamination_pct || 0}}%</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Supplier Facility</div>
              <div class="spec-val">${{lot.source_name || 'Verified Supplier'}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Intake Location</div>
              <div class="spec-val">${{lot.location_name || 'Dhaka, BD'}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Approximate Price</div>
              <div class="spec-val">${{asking}}</div>
            </div>
            <div class="buyer-spec-cell">
              <div class="spec-lbl">Verification Status</div>
              <div class="spec-val" style="color: #10B981;">✔ Admin Verified</div>
            </div>
          </div>
          <div style="margin-top: 16px; padding: 12px; background: rgba(16, 185, 129, 0.08); border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.2); font-size: 13px; color: #94A3B8;">
            <strong style="color: #10B981;">Traceability Note:</strong> This waste lot has been physically inspected and cataloged with intake QA. Material passport generation and transaction handover are managed via PunorAI circular verification protocol.
          </div>
        `;

        document.getElementById('lotDetailModal').classList.add('open');
      }}

      function openRequestFormModal() {{
        if (!currentActiveLot) return;
        closeModal();

        document.getElementById('reqLotId').value = currentActiveLot.id;
        document.getElementById('reqLotDisplay').value = currentActiveLot.code + ' (' + (currentActiveLot.category || '') + ')';
        document.getElementById('reqLotAvail').value = Number(currentActiveLot.qty_kg).toLocaleString() + ' kg Available';
        document.getElementById('reqQtyInput').value = currentActiveLot.qty_kg;
        document.getElementById('reqQtyInput').max = currentActiveLot.qty_kg;
        document.getElementById('reqPriceInput').value = currentActiveLot.asking_price_per_kg || '';
        document.getElementById('reqNotesInput').value = '';

        calculateRequestTotal();
        document.getElementById('requestFormModal').classList.add('open');
      }}

      function calculateRequestTotal() {{
        const qty = parseFloat(document.getElementById('reqQtyInput').value) || 0;
        const price = parseFloat(document.getElementById('reqPriceInput').value) || 0;
        const total = qty * price;
        const hint = document.getElementById('reqTotalHint');
        if (total > 0) {{
          hint.innerText = 'Estimated total: ৳ ' + total.toLocaleString() + ' BDT';
        }} else {{
          hint.innerText = 'Estimated total: Market Negotiable';
        }}
      }}

      function closeLotModalOnBackdrop(e) {{
        if (e.target.id === 'lotDetailModal') closeModal();
      }}
      function closeRequestModalOnBackdrop(e) {{
        if (e.target.id === 'requestFormModal') closeModal();
      }}

      async function submitPurchaseRequest(e) {{
        e.preventDefault();
        const lotId = document.getElementById('reqLotId').value;
        const qty = parseFloat(document.getElementById('reqQtyInput').value);
        const price = parseFloat(document.getElementById('reqPriceInput').value) || 0.0;
        const notes = document.getElementById('reqNotesInput').value;

        if (!qty || qty <= 0) {{
          alert('Requested quantity must be greater than zero.');
          return;
        }}

        const btn = document.getElementById('reqSubmitBtn');
        btn.disabled = true;
        btn.innerHTML = '<span>Submitting Request...</span>';

        try {{
          const res = await fetch('/api/buyer/requests/create', {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCsrfToken()
            }},
            body: JSON.stringify({{
              lot_id: parseInt(lotId),
              requested_qty_kg: qty,
              offered_price_per_kg: price,
              notes: notes
            }})
          }});
          const data = await res.json();
          if (data.ok) {{
            closeModal();
            showToast('Purchase request ' + data.code + ' submitted successfully! Admin will review.', 'success');
            setTimeout(() => window.location.reload(), 1500);
          }} else {{
            alert('Error: ' + (data.error || 'Failed to submit request.'));
            btn.disabled = false;
            btn.innerHTML = '<span>Send Request to Admin</span>';
          }}
        }} catch (err) {{
          console.error(err);
          alert('Network communication error.');
          btn.disabled = false;
          btn.innerHTML = '<span>Send Request to Admin</span>';
        }}
      }}
    </script>
    """
    return buyer_layout("Procurement Workspace", "dashboard", body, user, stats, csrf_token)

# ==============================================================================
# PAGE 2: BROWSE MATERIALS FULL PROCUREMENT CATALOG (/buyer/materials)
# ==============================================================================

def page_buyer_materials(handler, conn) -> str:
    """
    Full procurement catalog of approved and available material lots.
    Features:
    - Filters by Category, Grade, Location, Min Qty
    - Text search by Lot ID, Category, Supplier, Location
    - Sorting by Quantity, Date, Price
    - Only displays lots where status = 'verified' AND allocated = 0
    - Interactive lot inspection and purchase request trigger
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    stats = get_buyer_stats(conn, user)

    # Parse query parameters
    query_params = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    search_q = query_params.get("search", [""])[0].strip()
    category_f = query_params.get("category", [""])[0].strip().lower()
    grade_f = query_params.get("grade", [""])[0].strip().upper()
    min_qty_f = query_params.get("min_qty", [""])[0].strip()
    location_f = query_params.get("location", [""])[0].strip().lower()
    sort_by = query_params.get("sort", ["newest"])[0].strip()

    # Query saved lots for bookmark state
    cursor.execute("SELECT lot_id FROM saved_lots WHERE user_id = ?", (user["id"],))
    saved_lot_ids = {r[0] for r in cursor.fetchall()}

    # Base WHERE clause: strictly verified and unallocated lots
    where_clauses = ["status = 'verified'", "allocated = 0"]
    params = []

    if search_q:
        where_clauses.append("(code LIKE ? OR category LIKE ? OR source_name LIKE ? OR location_name LIKE ? OR notes LIKE ?)")
        s_term = f"%{search_q}%"
        params.extend([s_term, s_term, s_term, s_term, s_term])

    if category_f:
        where_clauses.append("LOWER(category) LIKE ?")
        params.append(f"%{category_f}%")

    if grade_f in ("A", "B", "C"):
        where_clauses.append("grade = ?")
        params.append(grade_f)

    if min_qty_f:
        try:
            min_val = float(min_qty_f)
            where_clauses.append("qty_kg >= ?")
            params.append(min_val)
        except ValueError:
            pass

    if location_f:
        where_clauses.append("LOWER(location_name) LIKE ?")
        params.append(f"%{location_f}%")

    order_clause = "id DESC"
    if sort_by == "qty_desc":
        order_clause = "qty_kg DESC"
    elif sort_by == "qty_asc":
        order_clause = "qty_kg ASC"
    elif sort_by == "price_asc":
        order_clause = "asking_price_per_kg ASC"
    elif sort_by == "price_desc":
        order_clause = "asking_price_per_kg DESC"

    query = f"""
        SELECT id, code, source_name, source_type, category, grade, colour,
               contamination_pct, qty_kg, location_name, status, photo,
               asking_price_per_kg, created_at, notes
        FROM lots
        WHERE {" AND ".join(where_clauses)}
        ORDER BY {order_clause}
    """
    cursor.execute(query, params)
    lots = cursor.fetchall()

    # Build catalog material cards
    cards_html = []
    lots_dict = {}
    for lot in lots:
        lots_dict[lot["id"]] = dict(lot)
        lot_id = lot["id"]
        code = lot["code"]
        cat = (lot["category"] or "Textile Waste").title()
        grade = lot["grade"] or "A"
        qty_kg = lot["qty_kg"] or 0.0
        qty_str = f"{qty_kg/1000.0:.1f} MT" if qty_kg >= 1000 else f"{qty_kg:,.0f} kg"
        supplier = lot["source_name"] or "Verified Supplier"
        loc = lot["location_name"] or "Dhaka, BD"
        asking_price = lot["asking_price_per_kg"] or 0.0
        price_str = f"৳ {asking_price:,.0f}/kg" if asking_price > 0 else "Negotiable"
        photo_url = get_lot_photo_url(lot)
        is_saved = (lot_id in saved_lot_ids)

        bookmark_cls = "buyer-bookmark-btn active" if is_saved else "buyer-bookmark-btn"
        bookmark_icon = '<svg width="18" height="18" viewBox="0 0 24 24" fill="#10B981" stroke="#10B981" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>' if is_saved else '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>'

        cards_html.append(f"""
        <div class="buyer-material-card">
          <div class="buyer-card-media">
            <img src="{e(photo_url)}" alt="{e(code)}" onerror="this.src='/static/hero_roll_crop.jpg'">
            <div class="buyer-verified-pill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
              <span>Verified</span>
            </div>
            <button type="button" class="{bookmark_cls}" onclick="toggleBookmark({lot_id}, this)" title="Save Lot">
              {bookmark_icon}
            </button>
          </div>
          <div class="buyer-card-content">
            <div class="buyer-card-title">{e(code)}: {e(cat)}</div>
            <div class="buyer-card-meta">
              <span class="buyer-meta-item">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3l3 4 3-4"/></svg>
                <span>{e(supplier)}</span>
              </span>
              <span class="buyer-meta-item">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                <span>{e(loc)}</span>
              </span>
            </div>
            <div class="buyer-specs-row">
              <span class="buyer-spec-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                <span>{qty_str} Avail.</span>
              </span>
              <span class="buyer-spec-tag grade">
                <span style="color: #F59E0B;">★</span> Grade {e(grade)}
              </span>
              <span class="buyer-spec-tag price">
                {e(price_str)}
              </span>
            </div>
            <div class="buyer-card-actions">
              <button type="button" class="buyer-btn-card" onclick="openLotModal({lot_id})">
                <span>View Details</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
              <button type="button" class="buyer-btn-card-save" onclick="quickRequestLot({lot_id})" title="Request Lot Directly">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>
              </button>
            </div>
          </div>
        </div>
        """)

    cards_rendered = "\n".join(cards_html) if cards_html else """
      <div style="grid-column: 1 / -1; padding: 60px 24px; text-align: center; background: #0d1a15; border-radius: 16px; border: 1px dashed rgba(16, 185, 129, 0.3);">
        <div style="font-size: 40px; margin-bottom: 16px;">🔍</div>
        <h3 style="color: #FFFFFF; font-size: 18px; margin-bottom: 8px;">No Waste Lots Match Your Filter</h3>
        <p style="color: #94A3B8; font-size: 14px; margin-bottom: 20px;">Try clearing filters or adjusting your quantity requirement to see all available lots.</p>
        <a href="/buyer/materials" class="buyer-btn-primary" style="display: inline-flex;">Clear All Filters</a>
      </div>
    """

    body = f"""
    <!-- PAGE HEADER -->
    <div class="buyer-page-header">
      <div>
        <h1 class="buyer-page-title">Procurement Materials Catalog</h1>
        <div class="buyer-page-subtitle">Verified, unallocated textile waste available for immediate circular procurement</div>
      </div>
      <div class="buyer-header-actions">
        <span class="buyer-count-badge">{len(lots)} Available Lots Found</span>
      </div>
    </div>

    <!-- ADVANCED FILTER & SEARCH TOOLBAR -->
    <div class="buyer-section-panel" style="margin-bottom: 24px; padding: 20px 24px;">
      <form action="/buyer/materials" method="GET" class="buyer-catalog-filter-form">
        <div class="buyer-search-field">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" name="search" value="{e(search_q)}" placeholder="Search by lot ID, material, supplier, or location...">
        </div>
        <div class="buyer-filter-selects-row">
          <select name="category" class="buyer-select">
            <option value="">All Categories</option>
            <option value="cotton" {"selected" if category_f == "cotton" else ""}>Cotton</option>
            <option value="polyester" {"selected" if category_f == "polyester" else ""}>Polyester</option>
            <option value="denim" {"selected" if category_f == "denim" else ""}>Denim</option>
            <option value="blend" {"selected" if "blend" in category_f else ""}>Blended Fibers</option>
            <option value="mixed" {"selected" if category_f == "mixed" else ""}>Mixed Textile Scrap</option>
          </select>
          <select name="grade" class="buyer-select">
            <option value="">All Grades</option>
            <option value="A" {"selected" if grade_f == "A" else ""}>Grade A (High Purity)</option>
            <option value="B" {"selected" if grade_f == "B" else ""}>Grade B (Standard)</option>
            <option value="C" {"selected" if grade_f == "C" else ""}>Grade C (Mixed / Rags)</option>
          </select>
          <input type="number" name="min_qty" value="{e(min_qty_f)}" placeholder="Min Quantity (kg)" class="buyer-input" style="max-width: 150px;">
          <select name="sort" class="buyer-select">
            <option value="newest" {"selected" if sort_by == "newest" else ""}>Newest Listings</option>
            <option value="qty_desc" {"selected" if sort_by == "qty_desc" else ""}>Quantity: High to Low</option>
            <option value="qty_asc" {"selected" if sort_by == "qty_asc" else ""}>Quantity: Low to High</option>
            <option value="price_asc" {"selected" if sort_by == "price_asc" else ""}>Price: Low to High</option>
          </select>
          <button type="submit" class="buyer-btn-primary" style="padding: 10px 20px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
            <span>Filter</span>
          </button>
          <a href="/buyer/materials" class="buyer-btn-outline" style="text-decoration: none; padding: 10px 16px;">Reset</a>
        </div>
      </form>
    </div>

    <!-- MATERIAL CARDS GRID -->
    <div class="buyer-materials-grid" style="grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));">
      {cards_rendered}
    </div>

    <!-- LOT DETAILS MODAL -->
    <div class="buyer-modal-backdrop" id="lotDetailModal" onclick="closeLotModalOnBackdrop(event)">
      <div class="buyer-modal-card">
        <div class="buyer-modal-header">
          <div>
            <div class="buyer-modal-title" id="mCode">LOT Details</div>
            <div class="buyer-modal-subtitle" id="mCat">Textile Waste Specification</div>
          </div>
          <button type="button" class="buyer-modal-close" onclick="closeModal()">&times;</button>
        </div>
        <div class="buyer-modal-body" id="mBody"></div>
        <div class="buyer-modal-footer">
          <button type="button" class="buyer-btn-outline" onclick="closeModal()">Close</button>
          <button type="button" class="buyer-btn-primary" id="mRequestBtn" onclick="openRequestFormModal()">
            <span>Submit Purchase Request</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- PURCHASE REQUEST FORM MODAL -->
    <div class="buyer-modal-backdrop" id="requestFormModal" onclick="closeRequestModalOnBackdrop(event)">
      <div class="buyer-modal-card" style="max-width: 520px;">
        <div class="buyer-modal-header">
          <div>
            <div class="buyer-modal-title">Submit Purchase Request</div>
            <div class="buyer-modal-subtitle">Procure verified textile waste</div>
          </div>
          <button type="button" class="buyer-modal-close" onclick="closeModal()">&times;</button>
        </div>
        <form id="purchaseRequestForm" onsubmit="submitPurchaseRequest(event)">
          <input type="hidden" id="reqLotId" name="lot_id" value="">
          <div class="buyer-modal-body">
            <div class="buyer-form-group">
              <label class="buyer-label">Selected Waste Lot</label>
              <input type="text" id="reqLotDisplay" class="buyer-input" readonly>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Available Inventory</label>
              <input type="text" id="reqLotAvail" class="buyer-input" readonly>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Requested Quantity (kg) <span class="req">*</span></label>
              <input type="number" id="reqQtyInput" name="requested_qty_kg" class="buyer-input" min="1" step="0.1" required placeholder="Enter quantity in kg" oninput="calculateRequestTotal()">
              <div class="buyer-hint">Must be greater than 0 and cannot exceed available lot quantity.</div>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Offered Price (BDT/kg)</label>
              <input type="number" id="reqPriceInput" name="offered_price_per_kg" class="buyer-input" step="0.5" placeholder="Suggested / offered price" oninput="calculateRequestTotal()">
              <div class="buyer-hint" id="reqTotalHint">Estimated total: ৳ 0</div>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Notes for Intake Admin & Supplier (Optional)</label>
              <textarea id="reqNotesInput" name="notes" class="buyer-textarea" rows="3" placeholder="Specify spinning requirement, pickup preference, or QA requirements..."></textarea>
            </div>
          </div>
          <div class="buyer-modal-footer">
            <button type="button" class="buyer-btn-outline" onclick="closeModal()">Cancel</button>
            <button type="submit" class="buyer-btn-primary" id="reqSubmitBtn">
              <span>Send Request to Admin</span>
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- CATALOG SCRIPTS -->
    <script>
      let currentActiveLot = null;
      const AVAILABLE_LOTS = {json.dumps(lots_dict)};

      function quickRequestLot(lotId) {{
        currentActiveLot = AVAILABLE_LOTS[lotId];
        if (currentActiveLot) openRequestFormModal();
      }}

      function openLotModal(lotId) {{
        const lot = AVAILABLE_LOTS[lotId];
        if (!lot) return;
        currentActiveLot = lot;

        document.getElementById('mCode').innerText = lot.code + ' — ' + (lot.category || '').toUpperCase();
        document.getElementById('mCat').innerText = 'Verified Supplier: ' + (lot.source_name || 'N/A') + ' (' + (lot.location_name || 'Dhaka') + ')';

        const asking = lot.asking_price_per_kg ? '৳ ' + lot.asking_price_per_kg + '/kg' : 'Market Negotiable';

        document.getElementById('mBody').innerHTML = `
          <div class="buyer-lot-specs-grid">
            <div class="buyer-spec-cell"><div class="spec-lbl">Lot Code</div><div class="spec-val">${{lot.code}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Available Quantity</div><div class="spec-val highlight">${{Number(lot.qty_kg).toLocaleString()}} kg</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Category & Material</div><div class="spec-val">${{lot.category || 'Textile'}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Quality Grade</div><div class="spec-val">Grade ${{lot.grade || 'A'}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Colour</div><div class="spec-val">${{lot.colour || 'N/A'}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Contamination Estimate</div><div class="spec-val">${{lot.contamination_pct || 0}}%</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Supplier Facility</div><div class="spec-val">${{lot.source_name || 'Verified Supplier'}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Intake Location</div><div class="spec-val">${{lot.location_name || 'Dhaka, BD'}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Approximate Price</div><div class="spec-val">${{asking}}</div></div>
            <div class="buyer-spec-cell"><div class="spec-lbl">Verification Status</div><div class="spec-val" style="color: #10B981;">✔ Admin Verified</div></div>
          </div>
          ${{lot.notes ? `<div style="margin-top: 12px; font-size: 13px; color: #94A3B8;"><strong>Supplier Notes:</strong> ${{lot.notes}}</div>` : ''}}
        `;

        document.getElementById('lotDetailModal').classList.add('open');
      }}

      function openRequestFormModal() {{
        if (!currentActiveLot) return;
        closeModal();

        document.getElementById('reqLotId').value = currentActiveLot.id;
        document.getElementById('reqLotDisplay').value = currentActiveLot.code + ' (' + (currentActiveLot.category || '') + ')';
        document.getElementById('reqLotAvail').value = Number(currentActiveLot.qty_kg).toLocaleString() + ' kg Available';
        document.getElementById('reqQtyInput').value = currentActiveLot.qty_kg;
        document.getElementById('reqQtyInput').max = currentActiveLot.qty_kg;
        document.getElementById('reqPriceInput').value = currentActiveLot.asking_price_per_kg || '';
        document.getElementById('reqNotesInput').value = '';

        calculateRequestTotal();
        document.getElementById('requestFormModal').classList.add('open');
      }}

      function calculateRequestTotal() {{
        const qty = parseFloat(document.getElementById('reqQtyInput').value) || 0;
        const price = parseFloat(document.getElementById('reqPriceInput').value) || 0;
        const total = qty * price;
        const hint = document.getElementById('reqTotalHint');
        hint.innerText = total > 0 ? 'Estimated total: ৳ ' + total.toLocaleString() + ' BDT' : 'Estimated total: Market Negotiable';
      }}

      function closeLotModalOnBackdrop(e) {{
        if (e.target.id === 'lotDetailModal') closeModal();
      }}
      function closeRequestModalOnBackdrop(e) {{
        if (e.target.id === 'requestFormModal') closeModal();
      }}

      async function submitPurchaseRequest(e) {{
        e.preventDefault();
        const lotId = document.getElementById('reqLotId').value;
        const qty = parseFloat(document.getElementById('reqQtyInput').value);
        const price = parseFloat(document.getElementById('reqPriceInput').value) || 0.0;
        const notes = document.getElementById('reqNotesInput').value;

        if (!qty || qty <= 0) {{
          alert('Requested quantity must be greater than zero.');
          return;
        }}

        const btn = document.getElementById('reqSubmitBtn');
        btn.disabled = true;
        btn.innerHTML = '<span>Submitting Request...</span>';

        try {{
          const res = await fetch('/api/buyer/requests/create', {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCsrfToken()
            }},
            body: JSON.stringify({{
              lot_id: parseInt(lotId),
              requested_qty_kg: qty,
              offered_price_per_kg: price,
              notes: notes
            }})
          }});
          const data = await res.json();
          if (data.ok) {{
            closeModal();
            showToast('Purchase request ' + data.code + ' submitted successfully! Admin will review.', 'success');
            setTimeout(() => window.location.href = '/buyer/requests', 1200);
          }} else {{
            alert('Error: ' + (data.error || 'Failed to submit request.'));
            btn.disabled = false;
            btn.innerHTML = '<span>Send Request to Admin</span>';
          }}
        }} catch (err) {{
          console.error(err);
          alert('Network communication error.');
          btn.disabled = false;
          btn.innerHTML = '<span>Send Request to Admin</span>';
        }}
      }}
    </script>
    """
    return buyer_layout("Browse Materials Catalog", "materials", body, user, stats, csrf_token)

# ==============================================================================
# PAGE 3: SAVED LOTS / BOOKMARKS (/buyer/saved)
# ==============================================================================

def page_buyer_saved(handler, conn) -> str:
    """
    Renders saved lots (bookmarks) scoped to the authenticated Buyer.
    Shows availability status:
    - If status = 'verified' AND allocated = 0: "Available for Procurement"
    - If allocated = 1 or status != 'verified': "Allocated / Currently Unavailable"
    Allows removing bookmarks and launching direct purchase request.
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    stats = get_buyer_stats(conn, user)

    cursor.execute("""
        SELECT sl.id as saved_id, sl.created_at as saved_date,
               l.id as lot_id, l.code, l.source_name, l.category, l.grade,
               l.qty_kg, l.location_name, l.status, l.allocated, l.asking_price_per_kg, l.photo
        FROM saved_lots sl
        JOIN lots l ON sl.lot_id = l.id
        WHERE sl.user_id = ?
        ORDER BY sl.id DESC
    """, (user["id"],))
    saved_items = cursor.fetchall()

    saved_cards_html = []
    saved_dict = {}
    for item in saved_items:
        saved_dict[item["lot_id"]] = dict(item)
        lot_id = item["lot_id"]
        code = item["code"]
        cat = (item["category"] or "Textile Waste").title()
        grade = item["grade"] or "A"
        qty_kg = item["qty_kg"] or 0.0
        qty_str = f"{qty_kg/1000.0:.1f} MT" if qty_kg >= 1000 else f"{qty_kg:,.0f} kg"
        supplier = item["source_name"] or "Verified Supplier"
        loc = item["location_name"] or "Dhaka, BD"
        asking_price = item["asking_price_per_kg"] or 0.0
        price_str = f"৳ {asking_price:,.0f}/kg" if asking_price > 0 else "Negotiable"
        photo_url = get_lot_photo_url(item)

        is_avail = (item["status"] == "verified" and item["allocated"] == 0)
        status_badge = '<span class="buyer-status-pill approved">✔ Available for Procurement</span>' if is_avail else '<span class="buyer-status-pill rejected">Allocated / Unavailable</span>'

        action_btn = f"""
          <button type="button" class="buyer-btn-card" onclick="quickRequestLot({lot_id})">
            <span>Request Lot</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </button>
        """ if is_avail else """
          <button type="button" class="buyer-btn-card" disabled style="opacity: 0.5; cursor: not-allowed;">
            <span>Unavailable</span>
          </button>
        """

        saved_cards_html.append(f"""
        <div class="buyer-material-card" id="savedCard_{lot_id}">
          <div class="buyer-card-media">
            <img src="{e(photo_url)}" alt="{e(code)}" onerror="this.src='/static/hero_roll_crop.jpg'">
            <div style="position: absolute; top: 10px; left: 10px;">
              {status_badge}
            </div>
            <button type="button" class="buyer-bookmark-btn active" onclick="removeBookmark({lot_id})" title="Remove Bookmark">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="#10B981" stroke="#10B981" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
            </button>
          </div>
          <div class="buyer-card-content">
            <div class="buyer-card-title">{e(code)}: {e(cat)}</div>
            <div class="buyer-card-meta">
              <span class="buyer-meta-item">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M3 7v14M21 7v14M6 11h4M6 15h4M14 11h4M14 15h4M9 3l3 4 3-4"/></svg>
                <span>{e(supplier)}</span>
              </span>
              <span class="buyer-meta-item">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                <span>{e(loc)}</span>
              </span>
            </div>
            <div class="buyer-specs-row">
              <span class="buyer-spec-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                <span>{qty_str}</span>
              </span>
              <span class="buyer-spec-tag grade">Grade {e(grade)}</span>
              <span class="buyer-spec-tag price">{e(price_str)}</span>
            </div>
            <div class="buyer-card-actions">
              {action_btn}
              <button type="button" class="buyer-btn-card-save" onclick="removeBookmark({lot_id})" title="Remove Bookmark" style="color: #EF4444;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
        </div>
        """)

    cards_rendered = "\n".join(saved_cards_html) if saved_cards_html else """
      <div style="grid-column: 1 / -1; padding: 60px 24px; text-align: center; background: #0d1a15; border-radius: 16px; border: 1px dashed rgba(16, 185, 129, 0.3);">
        <div style="font-size: 40px; margin-bottom: 16px;">🔖</div>
        <h3 style="color: #FFFFFF; font-size: 18px; margin-bottom: 8px;">No Saved Lots Yet</h3>
        <p style="color: #94A3B8; font-size: 14px; margin-bottom: 20px;">Bookmark verified waste lots as you explore the catalog to track their availability or purchase them later.</p>
        <a href="/buyer/materials" class="buyer-btn-primary" style="display: inline-flex;">Explore Materials Catalog</a>
      </div>
    """

    body = f"""
    <div class="buyer-page-header">
      <div>
        <h1 class="buyer-page-title">Saved Lots & Bookmarks</h1>
        <div class="buyer-page-subtitle">Your bookmarked waste lots for monitoring and future procurement</div>
      </div>
      <div class="buyer-header-actions">
        <span class="buyer-count-badge">{len(saved_items)} Bookmarks</span>
      </div>
    </div>

    <!-- SAVED LOTS GRID -->
    <div class="buyer-materials-grid" style="grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));">
      {cards_rendered}
    </div>

    <!-- PURCHASE REQUEST MODAL -->
    <div class="buyer-modal-backdrop" id="requestFormModal" onclick="closeRequestModalOnBackdrop(event)">
      <div class="buyer-modal-card" style="max-width: 520px;">
        <div class="buyer-modal-header">
          <div>
            <div class="buyer-modal-title">Submit Purchase Request</div>
            <div class="buyer-modal-subtitle">Procure verified textile waste</div>
          </div>
          <button type="button" class="buyer-modal-close" onclick="closeModal()">&times;</button>
        </div>
        <form id="purchaseRequestForm" onsubmit="submitPurchaseRequest(event)">
          <input type="hidden" id="reqLotId" name="lot_id" value="">
          <div class="buyer-modal-body">
            <div class="buyer-form-group">
              <label class="buyer-label">Selected Waste Lot</label>
              <input type="text" id="reqLotDisplay" class="buyer-input" readonly>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Available Inventory</label>
              <input type="text" id="reqLotAvail" class="buyer-input" readonly>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Requested Quantity (kg) <span class="req">*</span></label>
              <input type="number" id="reqQtyInput" name="requested_qty_kg" class="buyer-input" min="1" step="0.1" required placeholder="Enter quantity in kg" oninput="calculateRequestTotal()">
              <div class="buyer-hint">Must be greater than 0 and cannot exceed available lot quantity.</div>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Offered Price (BDT/kg)</label>
              <input type="number" id="reqPriceInput" name="offered_price_per_kg" class="buyer-input" step="0.5" placeholder="Suggested / offered price" oninput="calculateRequestTotal()">
              <div class="buyer-hint" id="reqTotalHint">Estimated total: ৳ 0</div>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Notes for Intake Admin & Supplier (Optional)</label>
              <textarea id="reqNotesInput" name="notes" class="buyer-textarea" rows="3" placeholder="Specify spinning requirement, pickup preference, or QA requirements..."></textarea>
            </div>
          </div>
          <div class="buyer-modal-footer">
            <button type="button" class="buyer-btn-outline" onclick="closeModal()">Cancel</button>
            <button type="submit" class="buyer-btn-primary" id="reqSubmitBtn">
              <span>Send Request to Admin</span>
            </button>
          </div>
        </form>
      </div>
    </div>

    <script>
      let currentActiveLot = null;
      const SAVED_LOTS = {json.dumps(saved_dict)};

      async function removeBookmark(lotId) {{
        try {{
          const res = await fetch('/api/buyer/saved/toggle', {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCsrfToken()
            }},
            body: JSON.stringify({{ lot_id: lotId }})
          }});
          const data = await res.json();
          if (data.ok) {{
            showToast('Lot removed from bookmarks', 'success');
            const card = document.getElementById('savedCard_' + lotId);
            if (card) card.remove();
          }}
        }} catch(e) {{
          console.error(e);
          showToast('Failed to remove bookmark', 'error');
        }}
      }}

      function quickRequestLot(lotId) {{
        currentActiveLot = SAVED_LOTS[lotId];
        if (!currentActiveLot) return;

        document.getElementById('reqLotId').value = currentActiveLot.lot_id;
        document.getElementById('reqLotDisplay').value = currentActiveLot.code + ' (' + (currentActiveLot.category || '') + ')';
        document.getElementById('reqLotAvail').value = Number(currentActiveLot.qty_kg).toLocaleString() + ' kg Available';
        document.getElementById('reqQtyInput').value = currentActiveLot.qty_kg;
        document.getElementById('reqQtyInput').max = currentActiveLot.qty_kg;
        document.getElementById('reqPriceInput').value = currentActiveLot.asking_price_per_kg || '';
        document.getElementById('reqNotesInput').value = '';

        calculateRequestTotal();
        document.getElementById('requestFormModal').classList.add('open');
      }}

      function calculateRequestTotal() {{
        const qty = parseFloat(document.getElementById('reqQtyInput').value) || 0;
        const price = parseFloat(document.getElementById('reqPriceInput').value) || 0;
        const total = qty * price;
        const hint = document.getElementById('reqTotalHint');
        hint.innerText = total > 0 ? 'Estimated total: ৳ ' + total.toLocaleString() + ' BDT' : 'Estimated total: Market Negotiable';
      }}

      function closeRequestModalOnBackdrop(e) {{
        if (e.target.id === 'requestFormModal') closeModal();
      }}

      async function submitPurchaseRequest(e) {{
        e.preventDefault();
        const lotId = document.getElementById('reqLotId').value;
        const qty = parseFloat(document.getElementById('reqQtyInput').value);
        const price = parseFloat(document.getElementById('reqPriceInput').value) || 0.0;
        const notes = document.getElementById('reqNotesInput').value;

        if (!qty || qty <= 0) {{
          alert('Requested quantity must be greater than zero.');
          return;
        }}

        const btn = document.getElementById('reqSubmitBtn');
        btn.disabled = true;
        btn.innerHTML = '<span>Submitting Request...</span>';

        try {{
          const res = await fetch('/api/buyer/requests/create', {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCsrfToken()
            }},
            body: JSON.stringify({{
              lot_id: parseInt(lotId),
              requested_qty_kg: qty,
              offered_price_per_kg: price,
              notes: notes
            }})
          }});
          const data = await res.json();
          if (data.ok) {{
            closeModal();
            showToast('Purchase request ' + data.code + ' submitted successfully! Admin will review.', 'success');
            setTimeout(() => window.location.href = '/buyer/requests', 1200);
          }} else {{
            alert('Error: ' + (data.error || 'Failed to submit request.'));
            btn.disabled = false;
            btn.innerHTML = '<span>Send Request to Admin</span>';
          }}
        }} catch (err) {{
          console.error(err);
          alert('Network communication error.');
          btn.disabled = false;
          btn.innerHTML = '<span>Send Request to Admin</span>';
        }}
      }}
    </script>
    """
    return buyer_layout("Saved Lots", "saved", body, user, stats, csrf_token)

# ==============================================================================
# PAGE 4: PURCHASE REQUESTS LEDGER (/buyer/requests)
# ==============================================================================

def page_buyer_requests(handler, conn) -> str:
    """
    Renders purchase requests belonging to the logged-in Buyer.
    Allows reviewing request history, status, admin notes, and submission date.
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    stats = get_buyer_stats(conn, user)

    # Filter query
    query_params = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    status_filter = query_params.get("status", [""])[0].strip()

    where_sql = "pr.buyer_id = ?"
    params = [user["id"]]
    if status_filter:
        where_sql += " AND pr.status = ?"
        params.append(status_filter)

    cursor.execute(f"""
        SELECT pr.id, pr.code, pr.requested_qty_kg, pr.offered_price_per_kg,
               pr.notes, pr.status, pr.admin_notes, pr.created_at, pr.updated_at,
               l.code as lot_code, l.category as lot_category, l.grade as lot_grade,
               l.source_name as supplier_name, l.location_name
        FROM purchase_requests pr
        JOIN lots l ON pr.lot_id = l.id
        WHERE {where_sql}
        ORDER BY pr.id DESC
    """, params)
    requests = cursor.fetchall()

    rows_html = []
    for pr in requests:
        code = pr["code"]
        lot_code = pr["lot_code"]
        cat = (pr["lot_category"] or "Textile").title()
        grade = pr["lot_grade"] or "A"
        qty = pr["requested_qty_kg"]
        price = pr["offered_price_per_kg"]
        total = qty * price if price > 0 else 0
        total_str = f"৳ {total:,.0f}" if total > 0 else "Negotiable"
        price_str = f"৳ {price:,.0f}/kg" if price > 0 else "Negotiable"
        supplier = pr["supplier_name"] or "Verified Supplier"
        loc = pr["location_name"] or "Dhaka"
        st = pr["status"]
        created = pr["created_at"]
        admin_notes = pr["admin_notes"] or ""

        status_cls = "buyer-status-pill pending"
        status_label = "Pending Admin Review"
        if st == "admin_approved":
            status_cls = "buyer-status-pill approved"
            status_label = "Approved by Admin"
        elif st == "fulfilled":
            status_cls = "buyer-status-pill completed"
            status_label = "Fulfilled / In Order"
        elif st == "rejected":
            status_cls = "buyer-status-pill rejected"
            status_label = "Rejected"

        admin_badge = f'<div style="margin-top: 4px; font-size: 11.5px; color: #F59E0B;">Admin feedback: {e(admin_notes)}</div>' if admin_notes else ""

        rows_html.append(f"""
        <tr>
          <td><strong style="color: #10B981;">{e(code)}</strong></td>
          <td>
            <strong>{e(lot_code)}</strong> &bull; {e(cat)}
            <div style="font-size: 12px; color: #94A3B8;">Grade {e(grade)} &bull; {e(supplier)} ({e(loc)})</div>
          </td>
          <td><strong>{qty:,.0f} kg</strong></td>
          <td>{price_str}</td>
          <td><strong>{total_str}</strong></td>
          <td>
            <span class="{status_cls}">{status_label}</span>
            {admin_badge}
          </td>
          <td style="color: #94A3B8; font-size: 12.5px;">{e(created)}</td>
        </tr>
        """)

    table_body = "\n".join(rows_html) if rows_html else """
      <tr>
        <td colspan="7" style="text-align: center; padding: 40px; color: #94A3B8;">
          No purchase requests match this filter.<br>
          <a href="/buyer/materials" style="color: #10B981; font-weight: 600; text-decoration: underline; margin-top: 8px; display: inline-block;">Browse Approved Lots & Submit a Request &rarr;</a>
        </td>
      </tr>
    """

    body = f"""
    <div class="buyer-page-header">
      <div>
        <h1 class="buyer-page-title">Purchase Requests Ledger</h1>
        <div class="buyer-page-subtitle">Track intake approval, supplier negotiation, and transaction readiness</div>
      </div>
      <div class="buyer-header-actions">
        <a href="/buyer/materials" class="buyer-btn-primary">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>New Purchase Request</span>
        </a>
      </div>
    </div>

    <!-- REQUEST STATUS STRIP -->
    <div class="buyer-summary-strip">
      <a href="/buyer/requests" class="buyer-strip-pill {'active' if not status_filter else ''}">
        <span class="lbl">Total Requests</span>
        <span class="val">{stats['total_requests']}</span>
      </a>
      <a href="/buyer/requests?status=pending_admin" class="buyer-strip-pill {'active' if status_filter == 'pending_admin' else ''}">
        <span class="lbl">Pending Admin Review</span>
        <span class="val" style="color: #F59E0B;">{stats['pending_requests']}</span>
      </a>
      <a href="/buyer/requests?status=admin_approved" class="buyer-strip-pill {'active' if status_filter == 'admin_approved' else ''}">
        <span class="lbl">Admin Approved</span>
        <span class="val" style="color: #10B981;">{stats['approved_requests']}</span>
      </a>
      <a href="/buyer/requests?status=fulfilled" class="buyer-strip-pill {'active' if status_filter == 'fulfilled' else ''}">
        <span class="lbl">Fulfilled / Orders</span>
        <span class="val" style="color: #06B6D4;">{stats['fulfilled_requests']}</span>
      </a>
      <a href="/buyer/requests?status=rejected" class="buyer-strip-pill {'active' if status_filter == 'rejected' else ''}">
        <span class="lbl">Rejected</span>
        <span class="val" style="color: #EF4444;">{stats['rejected_requests']}</span>
      </a>
    </div>

    <!-- REQUESTS TABLE PANEL -->
    <div class="buyer-section-panel">
      <div class="buyer-table-responsive">
        <table class="buyer-data-table">
          <thead>
            <tr>
              <th>Request ID</th>
              <th>Material Lot</th>
              <th>Quantity</th>
              <th>Offered Price</th>
              <th>Total Estimate</th>
              <th>Intake Status</th>
              <th>Submitted Date</th>
            </tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
      </div>
    </div>
    """
    return buyer_layout("Purchase Requests", "requests", body, user, stats, csrf_token)

# ==============================================================================
# PAGE 5: MY ORDERS & TRANSACTIONS (/buyer/orders)
# ==============================================================================

def page_buyer_orders(handler, conn) -> str:
    """
    Displays transactions & orders for the authenticated Buyer.
    Shows Order ID, Lot, Supplier, Quantity, Amount, Handover Status, Passport link.
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    stats = get_buyer_stats(conn, user)

    cursor.execute("""
        SELECT tx.id, tx.code, tx.qty_kg, tx.price_per_kg, tx.total_amount,
               tx.handover_status, tx.passport_code, tx.created_at, tx.completed_at,
               l.code as lot_code, l.category as lot_category,
               u.org_name as seller_name, u.location_name as seller_location
        FROM transactions tx
        JOIN lots l ON tx.lot_id = l.id
        JOIN users u ON tx.seller_id = u.id
        WHERE tx.buyer_id = ?
        ORDER BY tx.id DESC
    """, (user["id"],))
    transactions = cursor.fetchall()

    rows_html = []
    for tx in transactions:
        code = tx["code"]
        lot_code = tx["lot_code"]
        cat = (tx["lot_category"] or "Textile").title()
        seller = tx["seller_name"] or "Supplier"
        loc = tx["seller_location"] or "Dhaka"
        qty = tx["qty_kg"]
        price = tx["price_per_kg"]
        amt = tx["total_amount"]
        status = tx["handover_status"]
        passport = tx["passport_code"]
        created = tx["created_at"]
        completed = tx["completed_at"] or "In Progress"

        status_cls = "buyer-status-pill approved" if status == "completed" else "buyer-status-pill pending"
        status_lbl = status.replace("_", " ").title()

        passport_html = f'<a href="/passports" class="buyer-passport-link" title="View Digital Product Passport"><span>{e(passport)}</span> ↗</a>' if passport else '<span style="color:#94A3B8;">Pending Completion</span>'

        rows_html.append(f"""
        <tr>
          <td><strong style="color: #00E599;">{e(code)}</strong></td>
          <td><strong>{e(lot_code)}</strong> &bull; {e(cat)}</td>
          <td>{e(seller)} <span style="font-size: 12px; color: #94A3B8;">({e(loc)})</span></td>
          <td><strong>{qty:,.0f} kg</strong></td>
          <td>৳ {price:,.0f}/kg</td>
          <td><strong style="color: #FFFFFF;">৳ {amt:,.0f}</strong></td>
          <td><span class="{status_cls}">{status_lbl}</span></td>
          <td>{passport_html}</td>
          <td style="color: #94A3B8; font-size: 12px;">{e(completed)}</td>
        </tr>
        """)

    table_body = "\n".join(rows_html) if rows_html else """
      <tr>
        <td colspan="9" style="text-align: center; padding: 40px; color: #94A3B8;">
          No completed procurement orders yet.<br>
          <a href="/buyer/materials" style="color: #10B981; font-weight: 600; text-decoration: underline; margin-top: 8px; display: inline-block;">Browse Approved Waste & Submit Requests &rarr;</a>
        </td>
      </tr>
    """

    body = f"""
    <div class="buyer-page-header">
      <div>
        <h1 class="buyer-page-title">Procurement Orders & Handover</h1>
        <div class="buyer-page-subtitle">Track physical material delivery, supplier settlement, and circular passports</div>
      </div>
    </div>

    <!-- ORDER STATS STRIP -->
    <div class="buyer-stats-grid" style="margin-bottom: 24px;">
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{stats['total_orders']}</div>
            <div class="buyer-stat-label">Total Transactions</div>
          </div>
        </div>
      </div>
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{stats['purchased_kg']:,.0f} kg</div>
            <div class="buyer-stat-label">Procured Material</div>
          </div>
        </div>
      </div>
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">৳ {stats['total_spend']:,.0f}</div>
            <div class="buyer-stat-label">Total Procurement Value</div>
          </div>
        </div>
      </div>
      <div class="buyer-stat-card">
        <div class="buyer-stat-header">
          <div class="buyer-stat-icon-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
          </div>
          <div class="buyer-stat-info">
            <div class="buyer-stat-value">{stats['passports_count']}</div>
            <div class="buyer-stat-label">Verified Passports</div>
          </div>
        </div>
      </div>
    </div>

    <!-- TRANSACTIONS TABLE -->
    <div class="buyer-section-panel">
      <div class="buyer-table-responsive">
        <table class="buyer-data-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Material Lot</th>
              <th>Supplier Facility</th>
              <th>Delivered Qty</th>
              <th>Unit Rate</th>
              <th>Settlement Amount</th>
              <th>Handover Status</th>
              <th>Digital Passport</th>
              <th>Completed Date</th>
            </tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
      </div>
    </div>
    """
    return buyer_layout("My Orders", "orders", body, user, stats, csrf_token)

# ==============================================================================
# PAGE 6: MATERIAL PASSPORTS (/buyer/passports)
# ==============================================================================

def page_buyer_passports(handler, conn) -> str:
    """
    Shows digital material passports associated with the Buyer's transactions or batches.
    Reuses the existing Material Passport system and circular passport verification links.
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    stats = get_buyer_stats(conn, user)

    # Query passports linked to this buyer's transactions
    cursor.execute("""
        SELECT tx.id, tx.code as tx_code, tx.passport_code, tx.qty_kg, tx.created_at, tx.completed_at,
               l.code as lot_code, l.category, l.grade, l.colour, l.source_name, l.location_name
        FROM transactions tx
        JOIN lots l ON tx.lot_id = l.id
        WHERE tx.buyer_id = ? AND tx.passport_code != ''
        ORDER BY tx.id DESC
    """, (user["id"],))
    tx_passports = cursor.fetchall()

    passports_cards_html = []
    if tx_passports:
        for p in tx_passports:
            pass_code = p["passport_code"]
            lot_code = p["lot_code"]
            cat = (p["category"] or "Textile Waste").title()
            supplier = p["source_name"] or "Verified Supplier"
            loc = p["location_name"] or "Dhaka"
            qty = p["qty_kg"]
            comp_date = p["completed_at"] or p["created_at"]

            passports_cards_html.append(f"""
            <div class="buyer-passport-card">
              <div class="buyer-passport-top">
                <div class="passport-seal">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
                </div>
                <div>
                  <div class="passport-id">{e(pass_code)}</div>
                  <div class="passport-sub">Verified Circular Material Passport</div>
                </div>
              </div>
              <div class="buyer-passport-specs">
                <div class="p-cell"><span class="k">Procured Lot:</span> <span class="v">{e(lot_code)} ({e(cat)})</span></div>
                <div class="p-cell"><span class="k">Certified Quantity:</span> <span class="v highlight">{qty:,.0f} kg</span></div>
                <div class="p-cell"><span class="k">Source Facility:</span> <span class="v">{e(supplier)}</span></div>
                <div class="p-cell"><span class="k">Intake Hub:</span> <span class="v">{e(loc)}</span></div>
                <div class="p-cell"><span class="k">Avoided Landfill CO₂:</span> <span class="v" style="color: #00E599;">{qty * 2.8:,.0f} kg CO₂ eq</span></div>
                <div class="p-cell"><span class="k">Certification Date:</span> <span class="v">{e(comp_date)}</span></div>
              </div>
              <div class="buyer-passport-actions">
                <a href="/passports" class="buyer-btn-primary" style="flex: 1; text-align: center; text-decoration: none;">
                  <span>Inspect Passport & QR</span>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
              </div>
            </div>
            """)
    else:
        passports_cards_html.append("""
          <div style="grid-column: 1 / -1; padding: 60px 24px; text-align: center; background: #0d1a15; border-radius: 16px; border: 1px dashed rgba(16, 185, 129, 0.3);">
            <div style="font-size: 40px; margin-bottom: 16px;">🛡️</div>
            <h3 style="color: #FFFFFF; font-size: 18px; margin-bottom: 8px;">No Completed Passports Yet</h3>
            <p style="color: #94A3B8; font-size: 14px; margin-bottom: 20px;">Digital Material Passports are automatically issued upon completion of physical waste handover and intake QA verification.</p>
            <a href="/passports" class="buyer-btn-outline" style="display: inline-flex;">View Platform Passports Hub &rarr;</a>
          </div>
        """)

    cards_rendered = "\n".join(passports_cards_html)

    body = f"""
    <div class="buyer-page-header">
      <div>
        <h1 class="buyer-page-title">Digital Material Passports</h1>
        <div class="buyer-page-subtitle">Cryptographically verified traceability records for your procured textile waste</div>
      </div>
      <div class="buyer-header-actions">
        <a href="/passports" class="buyer-btn-outline">
          <span>Public Passport Viewer</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        </a>
      </div>
    </div>

    <!-- PASSPORTS GRID -->
    <div class="buyer-materials-grid" style="grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));">
      {cards_rendered}
    </div>
    """
    return buyer_layout("Material Passports", "passports", body, user, stats, csrf_token)

# ==============================================================================
# PAGE 7: ACCOUNT SETTINGS (/buyer/settings)
# ==============================================================================

def page_buyer_settings(handler, conn) -> str:
    """
    Profile and procurement settings page for the authenticated Buyer.
    Allows editing Full Name / Contact Person, Organization Name, Phone, and Hub Location.
    Email is read-only. Protected by CSRF.
    """
    user, csrf_token = require_buyer(handler, conn)
    if not user:
        return ""

    cursor = conn.cursor()
    cursor.execute("SELECT id, email, role, org_name, contact_name, phone, location_name, created_at FROM users WHERE id = ?", (user["id"],))
    u_row = cursor.fetchone()

    stats = get_buyer_stats(conn, user)

    body = f"""
    <div class="buyer-page-header">
      <div>
        <h1 class="buyer-page-title">Buyer Account & Facility Settings</h1>
        <div class="buyer-page-subtitle">Manage organization profile, procurement contact details, and intake preferences</div>
      </div>
    </div>

    <div class="buyer-settings-grid">
      <!-- SETTINGS FORM PANEL -->
      <div class="buyer-section-panel" style="padding: 28px 32px;">
        <h3 class="buyer-panel-title" style="margin-bottom: 20px;">Procurement Organization Profile</h3>
        <form id="buyerSettingsForm" onsubmit="saveBuyerSettings(event)">
          <div class="buyer-form-group">
            <label class="buyer-label">Sign-in Email <span style="font-size: 11.5px; color: #94A3B8;">(Read-only)</span></label>
            <input type="email" value="{e(u_row['email'])}" class="buyer-input" readonly style="opacity: 0.7; cursor: not-allowed; background: rgba(0,0,0,0.3);">
            <div class="buyer-hint">Email address cannot be modified directly to preserve secure session tokens.</div>
          </div>

          <div class="buyer-form-row">
            <div class="buyer-form-group">
              <label class="buyer-label">Authorized Contact Person</label>
              <input type="text" id="setContactName" name="contact_name" value="{e(u_row['contact_name'] or 'James Rahman')}" class="buyer-input" placeholder="e.g. James Rahman" required>
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Organization / Recycler Name</label>
              <input type="text" id="setOrgName" name="org_name" value="{e(u_row['org_name'])}" class="buyer-input" placeholder="e.g. Recycler X (Dhaka)" required>
            </div>
          </div>

          <div class="buyer-form-row">
            <div class="buyer-form-group">
              <label class="buyer-label">Contact Phone</label>
              <input type="text" id="setPhone" name="phone" value="{e(u_row['phone'] or '+880 1711-234567')}" class="buyer-input" placeholder="+880 17XX-XXXXXX">
            </div>
            <div class="buyer-form-group">
              <label class="buyer-label">Intake Facility / Location Hub</label>
              <input type="text" id="setLocationName" name="location_name" value="{e(u_row['location_name'] or 'Dhaka')}" class="buyer-input" placeholder="e.g. Dhaka, Gazipur, Narayanganj">
            </div>
          </div>

          <div class="buyer-form-group">
            <label class="buyer-label">Procurement Role</label>
            <input type="text" value="Verified Textile Waste Recycler / Procurement Buyer" class="buyer-input" readonly style="opacity: 0.7; background: rgba(0,0,0,0.3);">
          </div>

          <div style="margin-top: 24px; display: flex; justify-content: flex-end;">
            <button type="submit" class="buyer-btn-primary" id="saveSettingsBtn" style="padding: 12px 28px;">
              <span>Save Changes</span>
            </button>
          </div>
        </form>
      </div>

      <!-- ACCOUNT SUMMARY SIDE CARD -->
      <div class="buyer-section-panel" style="padding: 28px 24px;">
        <h3 class="buyer-panel-title" style="margin-bottom: 16px;">Security & Verification</h3>
        <div class="buyer-user-card" style="margin-bottom: 20px;">
          <div class="buyer-user-avatar">
            <span>{e(get_user_initials(u_row['contact_name'] or u_row['org_name']))}</span>
            <span class="buyer-online-status"></span>
          </div>
          <div class="buyer-user-info">
            <div class="buyer-user-name">{e(u_row['contact_name'] or u_row['org_name'])}</div>
            <div class="buyer-user-role">
              <span>Verified Buyer</span>
              <span class="verified-check">✔</span>
            </div>
          </div>
        </div>

        <div style="font-size: 13px; color: #94A3B8; line-height: 1.6; margin-bottom: 20px;">
          <div style="margin-bottom: 8px;"><strong style="color: #FFFFFF;">Role Authority:</strong> Procurement Buyer</div>
          <div style="margin-bottom: 8px;"><strong style="color: #FFFFFF;">Account Created:</strong> {e(u_row['created_at'])}</div>
          <div style="margin-bottom: 8px;"><strong style="color: #FFFFFF;">Session Security:</strong> PBKDF2-HMAC-SHA256 & SameSite HttpOnly</div>
          <div><strong style="color: #FFFFFF;">Active Requests:</strong> {stats['total_requests']} requests submitted</div>
        </div>

        <div style="padding: 14px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 8px; font-size: 12.5px; color: #94A3B8;">
          <strong style="color: #10B981;">Procurement Integrity:</strong> Only Admin-verified waste lots are presented for buyer procurement. All transactions are logged with digital material passport traceability.
        </div>
      </div>
    </div>

    <script>
      async function saveBuyerSettings(e) {{
        e.preventDefault();
        const btn = document.getElementById('saveSettingsBtn');
        btn.disabled = true;
        btn.innerHTML = '<span>Saving Profile...</span>';

        try {{
          const res = await fetch('/api/buyer/settings', {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
              'X-CSRF-Token': getCsrfToken()
            }},
            body: JSON.stringify({{
              contact_name: document.getElementById('setContactName').value,
              org_name: document.getElementById('setOrgName').value,
              phone: document.getElementById('setPhone').value,
              location_name: document.getElementById('setLocationName').value
            }})
          }});
          const data = await res.json();
          if (data.ok) {{
            showToast('Account settings updated successfully!', 'success');
            setTimeout(() => window.location.reload(), 1000);
          }} else {{
            alert('Error: ' + (data.error || 'Failed to update settings'));
            btn.disabled = false;
            btn.innerHTML = '<span>Save Changes</span>';
          }}
        }} catch(err) {{
          console.error(err);
          alert('Network communication error');
          btn.disabled = false;
          btn.innerHTML = '<span>Save Changes</span>';
        }}
      }}
    </script>
    """
    return buyer_layout("Account Settings", "settings", body, user, stats, csrf_token)

# ==============================================================================
# API ENDPOINTS FOR BUYER WORKSPACE
# ==============================================================================

def api_buyer_create_request(handler, payload: dict, conn) -> dict:
    """
    POST /api/buyer/requests/create
    Submits a purchase request for an approved available waste lot.
    Validations:
    - User must have 'buyer' role.
    - CSRF token must be verified.
    - Lot must exist, status = 'verified', allocated = 0.
    - Requested quantity must be > 0 and <= lot['qty_kg'].
    - Generates unique code PR-YYYY-NNN.
    - Inserts into purchase_requests table.
    - Records audit log in events table.
    """
    sess_id = auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None
    user, csrf_token = auth.get_session_and_user(conn, sess_id)
    if not user:
        return {"ok": False, "error": "Authentication required. Please sign in as a Buyer."}
    if user["role"] != "buyer":
        return {"ok": False, "error": "Access denied. Only registered Buyer accounts may submit purchase requests."}

    req_csrf = handler.headers.get("X-CSRF-Token") or payload.get("csrf_token")
    if not auth.verify_csrf(csrf_token, req_csrf):
        return {"ok": False, "error": "CSRF validation failed. Please refresh and try again."}

    lot_id = payload.get("lot_id")
    try:
        qty = float(payload.get("requested_qty_kg", 0))
    except (ValueError, TypeError):
        return {"ok": False, "error": "Invalid requested quantity."}

    try:
        offered_price = float(payload.get("offered_price_per_kg", 0.0))
    except (ValueError, TypeError):
        offered_price = 0.0

    notes = str(payload.get("notes", "")).strip()

    if not lot_id:
        return {"ok": False, "error": "Lot ID is required."}
    if qty <= 0:
        return {"ok": False, "error": "Requested quantity must be greater than zero."}

    cursor = conn.cursor()

    # Validate lot status
    cursor.execute("SELECT id, code, qty_kg, status, allocated, category, source_name FROM lots WHERE id = ?", (lot_id,))
    lot = cursor.fetchone()
    if not lot:
        return {"ok": False, "error": "Waste lot not found."}

    if lot["status"] != "verified":
        return {"ok": False, "error": "This lot is not yet verified by Admin and cannot be requested."}

    if lot["allocated"] == 1:
        return {"ok": False, "error": "This lot is already allocated or fulfilled and unavailable for procurement."}

    if qty > float(lot["qty_kg"]):
        return {"ok": False, "error": f"Requested quantity ({qty:,.0f} kg) exceeds available lot quantity ({lot['qty_kg']:,.0f} kg)."}

    # Generate unique request code
    now = datetime.datetime.now()
    year = now.strftime("%Y")
    cursor.execute("SELECT COUNT(*) FROM purchase_requests WHERE code LIKE ?", (f"PR-{year}-%",))
    cnt = cursor.fetchone()[0] + 1
    code = f"PR-{year}-{cnt:03d}"

    # Verify uniqueness
    cursor.execute("SELECT id FROM purchase_requests WHERE code = ?", (code,))
    if cursor.fetchone():
        code = f"PR-{year}-{cnt:03d}-{secrets.token_hex(2)}"

    now_iso = now.strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO purchase_requests (
            code, buyer_id, lot_id, batch_id, requested_qty_kg,
            offered_price_per_kg, notes, status, admin_notes, created_at, updated_at
        ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'pending_admin', '', ?, ?)
    """, (code, user["id"], lot_id, qty, offered_price, notes, now_iso, now_iso))

    # Audit event record
    audit_msg = f"New purchase request submitted: {code} for {lot['code']} ({qty:,.0f} kg) by {user.get('org_name') or 'Buyer'}. Pending Admin review."
    cursor.execute("""
        INSERT INTO events (batch_id, ts, description)
        VALUES (NULL, ?, ?)
    """, (now_iso, audit_msg))

    conn.commit()

    return {
        "ok": True,
        "code": code,
        "message": f"Purchase request {code} submitted successfully for {qty:,.0f} kg of {lot['code']}."
    }

def api_buyer_toggle_saved(handler, payload: dict, conn) -> dict:
    """
    POST /api/buyer/saved/toggle
    Adds or removes a bookmark for a waste lot scoped to authenticated Buyer.
    """
    sess_id = auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None
    user, csrf_token = auth.get_session_and_user(conn, sess_id)
    if not user:
        return {"ok": False, "error": "Authentication required."}
    if user["role"] != "buyer":
        return {"ok": False, "error": "Access denied. Buyer role required."}

    req_csrf = handler.headers.get("X-CSRF-Token") or payload.get("csrf_token")
    if not auth.verify_csrf(csrf_token, req_csrf):
        return {"ok": False, "error": "CSRF validation failed."}

    lot_id = payload.get("lot_id")
    if not lot_id:
        return {"ok": False, "error": "Lot ID required."}

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM saved_lots WHERE user_id = ? AND lot_id = ?", (user["id"], lot_id))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("DELETE FROM saved_lots WHERE id = ?", (existing[0],))
        conn.commit()
        return {"ok": True, "saved": False, "message": "Lot removed from bookmarks."}
    else:
        now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor.execute("INSERT INTO saved_lots (user_id, lot_id, created_at) VALUES (?, ?, ?)", (user["id"], lot_id, now_iso))
        conn.commit()
        return {"ok": True, "saved": True, "message": "Lot saved to bookmarks."}

def api_buyer_update_settings(handler, payload: dict, conn) -> dict:
    """
    POST /api/buyer/settings
    Updates profile details for the authenticated Buyer.
    """
    sess_id = auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None
    user, csrf_token = auth.get_session_and_user(conn, sess_id)
    if not user:
        return {"ok": False, "error": "Authentication required."}
    if user["role"] != "buyer":
        return {"ok": False, "error": "Access denied. Buyer role required."}

    req_csrf = handler.headers.get("X-CSRF-Token") or payload.get("csrf_token")
    if not auth.verify_csrf(csrf_token, req_csrf):
        return {"ok": False, "error": "CSRF validation failed."}

    contact_name = str(payload.get("contact_name", "")).strip()
    org_name = str(payload.get("org_name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    location_name = str(payload.get("location_name", "")).strip()

    if not org_name:
        return {"ok": False, "error": "Organization name cannot be empty."}

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET contact_name = ?, org_name = ?, phone = ?, location_name = ?
        WHERE id = ?
    """, (contact_name, org_name, phone, location_name, user["id"]))
    conn.commit()

    return {"ok": True, "message": "Buyer profile updated successfully."}
