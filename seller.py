# ==============================================================================
# PUNORAI — SELLER WORKSPACE (WASTE SUPPLIER) MODULE
# ==============================================================================
import base64
import datetime
import html
import json
import math
import os
import re
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
        return "SE"
    parts = [p for p in name_or_org.strip().split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    elif len(parts) == 1 and len(parts[0]) == 1:
        return (parts[0][0] + "S").upper()
    return "SE"

def get_seller_stats(conn, user: dict) -> dict:
    """
    Computes real database-derived statistics for the authenticated Seller.
    Scopes lots strictly by:
      lots.seller_id = ? OR (lots.seller_id IS NULL AND lots.source_name = ?)
    """
    user_id = user["id"]
    org_name = user.get("org_name", "")
    cursor = conn.cursor()

    # Query lots strictly scoped to this seller
    cursor.execute("""
        SELECT
            COUNT(*) as total_lots,
            COALESCE(SUM(qty_kg), 0.0) as total_kg,
            COALESCE(SUM(CASE WHEN status = 'verified' THEN qty_kg ELSE 0 END), 0.0) as verified_kg,
            COUNT(CASE WHEN status = 'verified' THEN 1 END) as verified_lots,
            COALESCE(SUM(CASE WHEN status = 'pending' THEN qty_kg ELSE 0 END), 0.0) as pending_kg,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_lots,
            COALESCE(SUM(CASE WHEN status = 'rejected' THEN qty_kg ELSE 0 END), 0.0) as rejected_kg,
            COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_lots,
            COALESCE(SUM(CASE WHEN allocated = 1 THEN qty_kg ELSE 0 END), 0.0) as allocated_kg,
            COUNT(CASE WHEN allocated = 1 THEN 1 END) as allocated_lots
        FROM lots
        WHERE seller_id = ? OR (seller_id IS NULL AND source_name = ?)
    """, (user_id, org_name))
    row = cursor.fetchone()

    total_lots = row["total_lots"] if row else 0
    total_kg = float(row["total_kg"]) if row else 0.0
    verified_kg = float(row["verified_kg"]) if row else 0.0
    verified_lots = row["verified_lots"] if row else 0
    pending_kg = float(row["pending_kg"]) if row else 0.0
    pending_lots = row["pending_lots"] if row else 0
    rejected_kg = float(row["rejected_kg"]) if row else 0.0
    rejected_lots = row["rejected_lots"] if row else 0
    allocated_kg = float(row["allocated_kg"]) if row else 0.0
    allocated_lots = row["allocated_lots"] if row else 0

    # Query purchase requests for lots owned by this seller
    cursor.execute("""
        SELECT COUNT(*) as total_requests,
               COUNT(CASE WHEN pr.status = 'pending_admin' THEN 1 END) as pending_requests
        FROM purchase_requests pr
        JOIN lots l ON pr.lot_id = l.id
        WHERE l.seller_id = ? OR (l.seller_id IS NULL AND l.source_name = ?)
    """, (user_id, org_name))
    req_row = cursor.fetchone()
    total_requests = req_row["total_requests"] if req_row else 0
    pending_requests = req_row["pending_requests"] if req_row else 0

    # Query completed transactions for this seller
    cursor.execute("""
        SELECT COUNT(*) as total_tx,
               COALESCE(SUM(total_amount), 0.0) as total_revenue,
               COALESCE(SUM(qty_kg), 0.0) as transacted_kg
        FROM transactions
        WHERE seller_id = ?
    """, (user_id,))
    tx_row = cursor.fetchone()
    total_transactions = tx_row["total_tx"] if tx_row else 0
    total_revenue = float(tx_row["total_revenue"]) if tx_row else 0.0
    transacted_kg = float(tx_row["transacted_kg"]) if tx_row else 0.0

    return {
        "total_lots": total_lots,
        "total_kg": total_kg,
        "verified_kg": verified_kg,
        "verified_lots": verified_lots,
        "pending_kg": pending_kg,
        "pending_lots": pending_lots,
        "rejected_kg": rejected_kg,
        "rejected_lots": rejected_lots,
        "allocated_kg": allocated_kg,
        "allocated_lots": allocated_lots,
        "total_requests": total_requests,
        "pending_requests": pending_requests,
        "total_transactions": total_transactions,
        "total_revenue": total_revenue,
        "transacted_kg": transacted_kg
    }


def render_seller_sparkline_svg(color="#10B981", height=38, width=110, trend_type="submitted"):
    """Renders a smooth mini SVG sparkline matching the visual reference."""
    points = {
        "submitted": "M0,28 Q22,30 40,20 T75,16 T105,7",
        "verified": "M0,32 Q25,28 45,18 T80,12 T105,5",
        "pending": "M0,30 Q22,26 44,22 T75,15 T105,8",
        "allocated": "M0,34 Q25,26 50,19 T80,10 T105,4"
    }.get(trend_type, "M0,28 Q22,30 40,20 T75,16 T105,7")

    area_points = f"{points} L105,{height} L0,{height} Z"
    grad_id = f"sellerSparkGrad_{trend_type}"

    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" class="seller-stat-sparkline" aria-hidden="true">
      <defs>
        <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="{color}" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <path d="{area_points}" fill="url(#{grad_id})"/>
      <path d="{points}" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """


def render_seller_donut_svg(total_kg, verified_kg, pending_kg, rejected_kg, allocated_kg):
    """
    Renders the SVG Donut Chart for Inventory Overview matching the reference image:
    Center: total submitted kg (or '1,250 kg'), 'Total'.
    Segments: Verified (green), Pending (amber), Rejected (red), Allocated (cyan).
    """
    total_val = max(total_kg, 1.0)
    circ = 2 * math.pi * 50 # ~314.16

    # Avoid zero total display issues
    if total_kg <= 0:
        return """
        <div class="seller-donut-wrapper">
          <svg width="150" height="150" viewBox="0 0 140 140" class="seller-donut-svg" aria-label="Inventory Overview Donut Chart">
            <circle cx="70" cy="70" r="50" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="18"/>
            <g class="seller-donut-center-text">
              <text x="70" y="66" text-anchor="middle" font-size="20" font-weight="700" fill="#FFFFFF">0 kg</text>
              <text x="70" y="82" text-anchor="middle" font-size="10.5" font-weight="500" fill="#94A3B8">Total</text>
            </g>
          </svg>
        </div>
        """

    p_ver = verified_kg / total_val
    p_pen = pending_kg / total_val
    p_rej = rejected_kg / total_val

    len_ver = max(0.0, p_ver * circ)
    len_pen = max(0.0, p_pen * circ)
    len_rej = max(0.0, p_rej * circ)

    off_ver = 0.0
    off_pen = -len_ver
    off_rej = -(len_ver + len_pen)

    formatted_total = f"{total_kg:,.0f} kg" if total_kg >= 1000 else f"{total_kg:g} kg"

    return f"""
    <div class="seller-donut-wrapper">
      <svg width="150" height="150" viewBox="0 0 140 140" class="seller-donut-svg" aria-label="Inventory Overview Donut Chart">
        <circle cx="70" cy="70" r="50" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="18"/>
        <!-- Verified (Green) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#10B981" stroke-width="18"
                stroke-dasharray="{len_ver:.2f} {circ:.2f}" stroke-dashoffset="{off_ver:.2f}"
                transform="rotate(-90 70 70)" stroke-linecap="round"/>
        <!-- Pending (Amber) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#F59E0B" stroke-width="18"
                stroke-dasharray="{len_pen:.2f} {circ:.2f}" stroke-dashoffset="{off_pen:.2f}"
                transform="rotate(-90 70 70)"/>
        <!-- Rejected (Red) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#EF4444" stroke-width="18"
                stroke-dasharray="{len_rej:.2f} {circ:.2f}" stroke-dashoffset="{off_rej:.2f}"
                transform="rotate(-90 70 70)"/>
        <g class="seller-donut-center-text">
          <text x="70" y="66" text-anchor="middle" font-size="18" font-weight="700" fill="#FFFFFF">{e(formatted_total)}</text>
          <text x="70" y="82" text-anchor="middle" font-size="10.5" font-weight="500" fill="#94A3B8">Total</text>
        </g>
      </svg>
    </div>
    """


# ==============================================================================
# DEDICATED SELLER WORKSPACE LAYOUT
# ==============================================================================

def seller_layout(title: str, active: str, body: str, user: dict, counts: dict = None, csrf_token: str = "") -> str:
    """
    Renders the dedicated Seller Workspace layout matching the reference image.
    Features:
      - Dedicated Seller sidebar:
        1. My Dashboard (/seller)
        2. My Waste Inventory (/seller/inventory)
        3. Submit New Waste (/seller/submit)
        4. Verification Status (/seller/verification)
        5. Purchase Requests (/seller/requests)
        6. My Transactions (/seller/transactions)
        7. Material Passports (/seller/passports)
        8. Account Settings (/seller/settings)
        - Profile card with 'SS' avatar, 'Shanto Textile Mills', and 'Seller ✔'
        - Bottom 'Better Waste Management' card and Logout button
      - Dedicated Seller topbar:
        - Mobile hamburger toggle
        - Search input with [Ctrl + K] shortcut
        - Notification bell with red badge
        - Profile dropdown pill
      - Toast notifications container and Command Palette modal
    """
    c = counts or {}
    pen_badge = f'<span class="seller-nav-badge">{c["pending_lots"]}</span>' if c.get("pending_lots") else ""
    req_badge = f'<span class="seller-nav-badge">{c["pending_requests"]}</span>' if c.get("pending_requests") else ""

    org_name = user.get("org_name") or user.get("name") or "Seller Facility"
    initials = get_user_initials(org_name)

    nav_items = [
        ("/seller", "My Dashboard", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>""", ""),
        ("/seller/inventory", "My Waste Inventory", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.29 7 12 12 20.71 7"/><line x1="12" y1="22" x2="12" y2="12"/></svg>""", ""),
        ("/seller/submit", "Submit New Waste", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>""", ""),
        ("/seller/verification", "Verification Status", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>""", pen_badge),
        ("/seller/requests", "Purchase Requests", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>""", req_badge),
        ("/seller/transactions", "My Transactions", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>""", ""),
        ("/seller/passports", "Material Passports", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>""", ""),
        ("/seller/settings", "Account Settings", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>""", "")
    ]

    sidebar_nav_html = []
    for href, label, icon, badge_html in nav_items:
        is_active = (href == active) or (href == "/seller" and active in ("/seller/dashboard", "/seller/overview"))
        active_cls = "seller-nav-item active" if is_active else "seller-nav-item"
        sidebar_nav_html.append(f"""
        <a href="{href}" class="{active_cls}">
          <span class="seller-nav-icon">{icon}</span>
          <span class="seller-nav-text">{e(label)}</span>
          {badge_html}
        </a>
        """)

    nav_links_rendered = "\n".join(sidebar_nav_html)

    brand_logo_html = render_brand_logo(
        href="/seller",
        size=26,
        extra_class="seller-brand-link",
        id_prefix="seller"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PunorAI &bull; {e(title)}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="seller-platform-body">
<div class="seller-app-layout">
  <div class="sidebar-backdrop" onclick="toggleSellerSidebar()"></div>

  <!-- DEDICATED SELLER SIDEBAR -->
  <aside class="seller-sidebar" id="sellerSidebar">
    <div class="seller-sidebar-header">
      {brand_logo_html}
    </div>

    <!-- Seller Profile Card -->
    <div class="seller-user-card">
      <div class="seller-user-avatar">{e(initials)}</div>
      <div class="seller-user-info">
        <div class="seller-user-name" title="{e(org_name)}">{e(org_name)}</div>
        <div class="seller-user-role">Seller <span class="verified-check">✔</span></div>
      </div>
    </div>

    <!-- Navigation List -->
    <nav class="seller-nav-list">
      {nav_links_rendered}
    </nav>

    <!-- Sidebar Bottom: Sustainability Promo Card -->
    <div class="seller-sidebar-footer">
      <div class="seller-eco-card">
        <div class="seller-eco-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>
        </div>
        <div class="seller-eco-title">Better Waste Management</div>
        <div class="seller-eco-sub">A Greener Tomorrow</div>
        <div class="seller-eco-visual">
          <div class="seller-eco-city-silhouette"></div>
        </div>
      </div>

      <a href="/logout" class="seller-logout-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        <span>Logout</span>
      </a>
    </div>
  </aside>

  <!-- MAIN VIEWPORT -->
  <div class="seller-viewport">
    <header class="seller-topbar">
      <div class="seller-topbar-left">
        <button class="seller-mobile-toggle" onclick="toggleSellerSidebar()" aria-label="Toggle Navigation">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="seller-search-wrapper" onclick="openSellerPalette()">
          <svg class="seller-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <span class="seller-search-placeholder">Search in your workspace...</span>
          <kbd class="seller-search-badge">Ctrl + K</kbd>
        </div>
      </div>

      <div class="seller-topbar-right">
        <!-- Notification Bell -->
        <div class="seller-notif-container">
          <button class="seller-icon-btn" onclick="toggleSellerNotifs(event)" aria-label="Notifications">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            <span class="seller-notif-pill">3</span>
          </button>
          <div class="seller-notif-dropdown" id="sellerNotifDropdown">
            <div class="seller-notif-header">
              <span>Workspace Notifications</span>
              <button class="seller-notif-mark" onclick="clearSellerNotifs()">Mark all read</button>
            </div>
            <div class="seller-notif-list">
              <div class="seller-notif-item">
                <div class="seller-notif-dot green"></div>
                <div class="seller-notif-content">
                  <div class="seller-notif-title">Intake Verification Queue active</div>
                  <div class="seller-notif-time">Admin QA online &bull; Just now</div>
                </div>
              </div>
              <div class="seller-notif-item">
                <div class="seller-notif-dot cyan"></div>
                <div class="seller-notif-content">
                  <div class="seller-notif-title">Verified lot eligible for buyer requests</div>
                  <div class="seller-notif-time">Automated matchmaking active</div>
                </div>
              </div>
              <div class="seller-notif-item">
                <div class="seller-notif-dot amber"></div>
                <div class="seller-notif-content">
                  <div class="seller-notif-title">Session secured with PBKDF2 + CSRF</div>
                  <div class="seller-notif-time">Authenticated securely</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Profile Pill -->
        <div class="seller-profile-container">
          <div class="seller-profile-pill" onclick="toggleSellerProfileMenu(event)">
            <div class="seller-pill-avatar">{e(initials)}</div>
            <div class="seller-pill-meta">
              <span class="seller-pill-name">{e(org_name)}</span>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
          <div class="seller-profile-dropdown" id="sellerProfileDropdown">
            <div style="padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.06);">
              <div style="color: #FFFFFF; font-weight: 600; font-size: 13px;">{e(org_name)}</div>
              <div style="color: #94A3B8; font-size: 11px;">{e(user['email'])}</div>
            </div>
            <a href="/seller/settings" class="seller-profile-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
              <span>Account Settings</span>
            </a>
            <a href="/logout" class="seller-profile-item" style="color: #EF4444;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              <span>Sign Out</span>
            </a>
          </div>
        </div>
      </div>
    </header>

    <!-- VIEWPORT BODY CONTENT -->
    <main class="seller-main-content">
      {body}
    </main>
  </div>
</div>

<!-- COMMAND PALETTE SPOTLIGHT MODAL -->
<div class="seller-palette-modal" id="sellerPaletteModal" onclick="closeSellerPalette(event)">
  <div class="seller-palette-card" onclick="event.stopPropagation()">
    <div class="seller-palette-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" id="sellerPaletteInput" placeholder="Quick jump to inventory, submit lot, verification, requests..." oninput="filterSellerPalette(this.value)">
      <kbd>ESC</kbd>
    </div>
    <div class="seller-palette-results" id="sellerPaletteResults">
      <a href="/seller" class="seller-palette-item">
        <span class="seller-palette-label">My Dashboard</span>
        <span class="seller-palette-meta">Workspace Overview</span>
      </a>
      <a href="/seller/inventory" class="seller-palette-item">
        <span class="seller-palette-label">My Waste Inventory</span>
        <span class="seller-palette-meta">Filter and view your factory waste lots</span>
      </a>
      <a href="/seller/submit" class="seller-palette-item">
        <span class="seller-palette-label">Submit New Waste</span>
        <span class="seller-palette-meta">Add characterization & upload lot for intake QA</span>
      </a>
      <a href="/seller/verification" class="seller-palette-item">
        <span class="seller-palette-label">Verification Status</span>
        <span class="seller-palette-meta">Track intake QA clearance and inspector notes</span>
      </a>
      <a href="/seller/requests" class="seller-palette-item">
        <span class="seller-palette-label">Purchase Requests</span>
        <span class="seller-palette-meta">Buyer procurement requests for your verified lots</span>
      </a>
      <a href="/seller/transactions" class="seller-palette-item">
        <span class="seller-palette-label">My Transactions</span>
        <span class="seller-palette-meta">Completed circular offtake and payout history</span>
      </a>
      <a href="/seller/passports" class="seller-palette-item">
        <span class="seller-palette-label">Material Passports</span>
        <span class="seller-palette-meta">Circular custody certificates & QR verification</span>
      </a>
      <a href="/seller/settings" class="seller-palette-item">
        <span class="seller-palette-label">Account Settings</span>
        <span class="seller-palette-meta">Update facility details & mill profile</span>
      </a>
    </div>
  </div>
</div>

<!-- TOAST CONTAINER -->
<div id="sellerToast" class="seller-toast"></div>

<script>
function toggleSellerSidebar() {{
  document.getElementById('sellerSidebar').classList.toggle('open');
  document.querySelector('.sidebar-backdrop').classList.toggle('active');
}}
function toggleSellerNotifs(e) {{
  e.stopPropagation();
  document.getElementById('sellerNotifDropdown').classList.toggle('open');
  document.getElementById('sellerProfileDropdown').classList.remove('open');
}}
function toggleSellerProfileMenu(e) {{
  e.stopPropagation();
  document.getElementById('sellerProfileDropdown').classList.toggle('open');
  document.getElementById('sellerNotifDropdown').classList.remove('open');
}}
function clearSellerNotifs() {{
  document.querySelectorAll('.seller-notif-dot').forEach(d => d.style.opacity = '0.2');
  const pill = document.querySelector('.seller-notif-pill');
  if (pill) pill.style.display = 'none';
}}
function openSellerPalette() {{
  document.getElementById('sellerPaletteModal').classList.add('open');
  const input = document.getElementById('sellerPaletteInput');
  input.value = '';
  input.focus();
  filterSellerPalette('');
}}
function closeSellerPalette(e) {{
  document.getElementById('sellerPaletteModal').classList.remove('open');
}}
function filterSellerPalette(q) {{
  q = (q || '').toLowerCase();
  document.querySelectorAll('.seller-palette-item').forEach(el => {{
    const txt = el.innerText.toLowerCase();
    el.style.display = txt.includes(q) ? 'flex' : 'none';
  }});
}}
window.addEventListener('keydown', function(e) {{
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {{
    e.preventDefault();
    openSellerPalette();
  }}
  if (e.key === 'Escape') {{
    closeSellerPalette();
  }}
}});
document.addEventListener('click', function() {{
  const nd = document.getElementById('sellerNotifDropdown');
  if (nd) nd.classList.remove('open');
  const pd = document.getElementById('sellerProfileDropdown');
  if (pd) pd.classList.remove('open');
}});

function showSellerToast(msg, type='success') {{
  const t = document.getElementById('sellerToast');
  if (!t) return;
  t.innerText = msg;
  t.className = 'seller-toast show ' + type;
  setTimeout(() => {{ t.className = 'seller-toast'; }}, 3800);
}}
</script>
</body>
</html>
"""


def render_seller_access_denied(user, role_needed="Seller"):
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PunorAI &bull; Access Denied</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="seller-platform-body">
  <div class="card" style="max-width: 600px; margin: 60px auto; text-align: center; padding: 40px 24px; background: rgba(14,23,30,0.9); border: 1px solid rgba(239,68,68,0.3); border-radius: 16px;">
    <div style="font-size: 44px; margin-bottom: 16px;">🚫</div>
    <h2 style="color: #EF4444; margin-bottom: 12px; font-size: 22px;">Access Denied — {e(role_needed)} Role Required</h2>
    <p style="color: #94A3B8; margin-bottom: 24px; font-size: 14px; line-height: 1.6;">
      Your account ({e(user.get('email', ''))}) is registered as a <strong>{user.get('role', 'user').title()}</strong>.
      You do not have permission to access the Waste Supplier Workspace.
    </p>
    <a href="/{user.get('role', '')}" class="seller-btn-primary" style="display: inline-block;">Go to Your {user.get('role', 'user').title()} Workspace</a>
  </div>
</body>
</html>'''

# ==============================================================================
# SELLER PAGE: 1. OVERVIEW DASHBOARD (/seller)
# ==============================================================================

def page_seller_dashboard(handler, conn) -> str:
    """
    Renders the dedicated Seller Overview Dashboard matching media_1793804148892_776790c2.jpg:
    - Welcome hero with personalized greeting and CTAs
    - 4 KPI cards with sparklines
    - Middle row: Inventory Overview Donut Chart & Recent Activity timeline
    - Bottom row: My Recent Waste Submissions & Recent Purchase Requests
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?role=seller&redirect=/seller")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    stats = get_seller_stats(conn, user)
    org_name = user.get("org_name") or "Shanto Textile Mills"
    user_id = user["id"]

    cursor = conn.cursor()

    # Query recent waste submissions for this seller
    cursor.execute("""
        SELECT id, code, category, qty_kg, grade, created_at, status
        FROM lots
        WHERE seller_id = ? OR (seller_id IS NULL AND source_name = ?)
        ORDER BY id DESC
        LIMIT 5
    """, (user_id, org_name))
    recent_lots = cursor.fetchall()

    # Query recent purchase requests for this seller's lots
    cursor.execute("""
        SELECT pr.id, pr.code, pr.requested_qty_kg, pr.status, pr.created_at,
               u.org_name as buyer_name, l.code as lot_code
        FROM purchase_requests pr
        JOIN lots l ON pr.lot_id = l.id
        JOIN users u ON pr.buyer_id = u.id
        WHERE l.seller_id = ? OR (l.seller_id IS NULL AND l.source_name = ?)
        ORDER BY pr.id DESC
        LIMIT 5
    """, (user_id, org_name))
    recent_requests = cursor.fetchall()

    # Query recent activity events for this seller
    # Fetch events mentioning the seller's lot codes or seller's org name
    seller_lot_codes = [r["code"] for r in recent_lots]
    event_query_terms = [org_name] + seller_lot_codes
    
    events_clause = " OR ".join(["description LIKE ?" for _ in event_query_terms]) if event_query_terms else "1=0"
    params = [f"%{term}%" for term in event_query_terms]
    
    cursor.execute(f"""
        SELECT id, ts, description
        FROM events
        WHERE {events_clause}
        ORDER BY id DESC
        LIMIT 5
    """, params)
    recent_events = cursor.fetchall()

    # If no specific events yet, build realistic audit items from lot submissions & transactions
    activity_items_html = []
    if recent_events:
        for ev in recent_events:
            desc = ev["description"]
            # Icon styling based on event description
            icon_svg = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>"""
            icon_cls = "act-icon green"
            if "VERIFIED" in desc or "Approved" in desc:
                icon_svg = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#06B6D4" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>"""
                icon_cls = "act-icon blue"
            elif "request" in desc.lower():
                icon_svg = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A855F7" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>"""
                icon_cls = "act-icon purple"
            elif "completed" in desc.lower() or "transaction" in desc.lower():
                icon_svg = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2.5"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>"""
                icon_cls = "act-icon emerald"

            activity_items_html.append(f"""
            <div class="seller-activity-item">
              <div class="{icon_cls}">{icon_svg}</div>
              <div class="seller-activity-text">
                <div class="seller-activity-title">{e(desc)}</div>
              </div>
              <div class="seller-activity-time">{e(ev['ts'])}</div>
            </div>
            """)
    else:
        # Build dynamic activity from recent submissions and transactions
        for lot in recent_lots[:3]:
            st_text = "Verification approved" if lot["status"] == "verified" else "New lot submitted"
            time_str = lot["created_at"] or "Recent"
            icon_cls = "act-icon green" if lot["status"] == "verified" else "act-icon blue"
            activity_items_html.append(f"""
            <div class="seller-activity-item">
              <div class="{icon_cls}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              </div>
              <div class="seller-activity-text">
                <div class="seller-activity-title">{st_text}: {e(lot['code'])} ({lot['qty_kg']:g} kg)</div>
              </div>
              <div class="seller-activity-time">{e(time_str)}</div>
            </div>
            """)
        for req in recent_requests[:2]:
            activity_items_html.append(f"""
            <div class="seller-activity-item">
              <div class="act-icon purple">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A855F7" stroke-width="2.5"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>
              </div>
              <div class="seller-activity-text">
                <div class="seller-activity-title">Purchase request from {e(req['buyer_name'])} for {e(req['lot_code'])}</div>
              </div>
              <div class="seller-activity-time">{e(req['created_at'])}</div>
            </div>
            """)

    if not activity_items_html:
        activity_items_html.append("""
        <div style="padding: 24px; text-align: center; color: #94A3B8; font-size: 13.5px;">
          No recent activity recorded yet. Submit a new waste lot to begin circular tracking.
        </div>
        """)

    # Render Submissions Table Rows
    submissions_rows_html = []
    if recent_lots:
        for lot in recent_lots:
            status = lot["status"]
            badge_cls = "seller-badge b-pending"
            badge_label = "Pending"
            if status == "verified":
                badge_cls = "seller-badge b-verified"
                badge_label = "Verified"
            elif status == "rejected":
                badge_cls = "seller-badge b-rejected"
                badge_label = "Rejected"

            submissions_rows_html.append(f"""
            <tr>
              <td><strong style="color: #FFFFFF;">{e(lot['code'])}</strong></td>
              <td>{e(lot['category'].title())}</td>
              <td><strong>{lot['qty_kg']:g} kg</strong></td>
              <td><span class="grade-pill">{e(lot['grade'])}</span></td>
              <td style="color: #94A3B8; font-size: 12.5px;">{e(lot['created_at'][:10] if lot['created_at'] else '—')}</td>
              <td><span class="{badge_cls}">{badge_label}</span></td>
            </tr>
            """)
    else:
        submissions_rows_html.append("""
        <tr>
          <td colspan="6" style="text-align: center; color: #94A3B8; padding: 24px;">
            No waste lots submitted yet. Click <strong>Submit New Waste</strong> to create your first lot.
          </td>
        </tr>
        """)

    # Render Requests Table Rows
    requests_rows_html = []
    if recent_requests:
        for req in recent_requests:
            st = req["status"]
            req_badge_cls = "seller-badge b-pending"
            req_label = "Pending"
            if st in ("admin_approved", "approved"):
                req_badge_cls = "seller-badge b-verified"
                req_label = "Approved"
            elif st == "rejected":
                req_badge_cls = "seller-badge b-rejected"
                req_label = "Rejected"

            requests_rows_html.append(f"""
            <tr>
              <td><strong style="color: #FFFFFF;">{e(req['code'])}</strong></td>
              <td>{e(req['buyer_name'])}</td>
              <td><span style="color: #10B981;">{e(req['lot_code'])}</span></td>
              <td><strong>{req['requested_qty_kg']:g} kg</strong></td>
              <td><span class="{req_badge_cls}">{req_label}</span></td>
            </tr>
            """)
    else:
        requests_rows_html.append("""
        <tr>
          <td colspan="5" style="text-align: center; color: #94A3B8; padding: 24px;">
            No buyer purchase requests received yet. Verified lots will appear for buyer matching.
          </td>
        </tr>
        """)

    # Donut percentages
    tot = max(stats["total_kg"], 1.0)
    ver_pct = round((stats["verified_kg"] / tot) * 100) if stats["total_kg"] > 0 else 0
    pen_pct = round((stats["pending_kg"] / tot) * 100) if stats["total_kg"] > 0 else 0
    rej_pct = round((stats["rejected_kg"] / tot) * 100) if stats["total_kg"] > 0 else 0
    alc_pct = round((stats["allocated_kg"] / tot) * 100) if stats["total_kg"] > 0 else 0

    donut_svg = render_seller_donut_svg(stats["total_kg"], stats["verified_kg"], stats["pending_kg"], stats["rejected_kg"], stats["allocated_kg"])

    body = f"""
    <!-- WELCOME HERO BANNER -->
    <div class="seller-hero-banner">
      <div class="seller-hero-content">
        <div class="seller-hero-title">
          <div class="sun-icon">☀️</div>
          <h1>Good Morning, <span class="highlight-green">{e(org_name)}!</span></h1>
        </div>
        <p class="seller-hero-sub">
          Manage your waste inventory and track your contributions to a circular economy.
        </p>
        <div class="seller-hero-ctas">
          <a href="/seller/submit" class="seller-btn-primary">
            <span>Submit New Waste</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </a>
          <a href="/seller/inventory" class="seller-btn-outline">
            View My Inventory
          </a>
        </div>
      </div>
      <div class="seller-hero-quote-box">
        <div class="seller-quote-inner">
          <div class="seller-quote-icon">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="1.8">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
            </svg>
          </div>
          <div class="seller-quote-text">
            &ldquo;Together for a circular future.&rdquo;
          </div>
        </div>
      </div>
    </div>

    <!-- 4 KPI STAT CARDS -->
    <div class="seller-stats-grid">
      <!-- Card 1: Total Waste Submitted -->
      <div class="seller-stat-card">
        <div class="seller-stat-top">
          <div class="seller-stat-icon-box green">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
          </div>
          <div class="seller-stat-meta">
            <span class="seller-stat-label">Total Waste Submitted</span>
            <div class="seller-stat-value">{stats['total_kg']:,.0f} kg</div>
          </div>
        </div>
        <div class="seller-stat-bottom">
          <span class="seller-stat-trend trend-green">&uarr; 12% vs. last month</span>
          {render_seller_sparkline_svg("#10B981", trend_type="submitted")}
        </div>
      </div>

      <!-- Card 2: Verified Waste -->
      <div class="seller-stat-card">
        <div class="seller-stat-top">
          <div class="seller-stat-icon-box teal">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#06B6D4" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
          </div>
          <div class="seller-stat-meta">
            <span class="seller-stat-label">Verified Waste</span>
            <div class="seller-stat-value">{stats['verified_kg']:,.0f} kg</div>
          </div>
        </div>
        <div class="seller-stat-bottom">
          <span class="seller-stat-trend trend-teal">&uarr; 18% vs. last month</span>
          {render_seller_sparkline_svg("#06B6D4", trend_type="verified")}
        </div>
      </div>

      <!-- Card 3: Pending Verification -->
      <div class="seller-stat-card">
        <div class="seller-stat-top">
          <div class="seller-stat-icon-box amber">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          </div>
          <div class="seller-stat-meta">
            <span class="seller-stat-label">Pending Verification</span>
            <div class="seller-stat-value">{stats['pending_kg']:,.0f} kg</div>
          </div>
        </div>
        <div class="seller-stat-bottom">
          <span class="seller-stat-trend trend-amber">&uarr; 5% vs. last month</span>
          {render_seller_sparkline_svg("#F59E0B", trend_type="pending")}
        </div>
      </div>

      <!-- Card 4: Allocated/Sold Waste -->
      <div class="seller-stat-card">
        <div class="seller-stat-top">
          <div class="seller-stat-icon-box mint">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#34D399" stroke-width="2"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>
          </div>
          <div class="seller-stat-meta">
            <span class="seller-stat-label">Allocated/Sold Waste</span>
            <div class="seller-stat-value">{stats['allocated_kg']:,.0f} kg</div>
          </div>
        </div>
        <div class="seller-stat-bottom">
          <span class="seller-stat-trend trend-mint">&uarr; 20% vs. last month</span>
          {render_seller_sparkline_svg("#34D399", trend_type="allocated")}
        </div>
      </div>
    </div>

    <!-- MIDDLE ROW: INVENTORY OVERVIEW DONUT & RECENT ACTIVITY -->
    <div class="seller-grid-middle">
      <!-- Left: Inventory Overview Donut Card -->
      <div class="seller-card">
        <div class="seller-card-header">
          <div class="seller-card-title">Inventory Overview</div>
          <span class="seller-card-subtitle" style="color: #94A3B8; font-size: 12px;">Characterized Stock</span>
        </div>
        <div class="seller-card-body" style="display: flex; align-items: center; justify-content: space-around; padding: 20px 10px;">
          {donut_svg}
          <div class="seller-donut-legend">
            <div class="seller-legend-item">
              <span class="seller-legend-dot" style="background: #10B981;"></span>
              <span class="seller-legend-name">Verified</span>
              <span class="seller-legend-pct">{ver_pct}%</span>
            </div>
            <div class="seller-legend-item">
              <span class="seller-legend-dot" style="background: #F59E0B;"></span>
              <span class="seller-legend-name">Pending</span>
              <span class="seller-legend-pct">{pen_pct}%</span>
            </div>
            <div class="seller-legend-item">
              <span class="seller-legend-dot" style="background: #EF4444;"></span>
              <span class="seller-legend-name">Rejected</span>
              <span class="seller-legend-pct">{rej_pct}%</span>
            </div>
            <div class="seller-legend-item">
              <span class="seller-legend-dot" style="background: #06B6D4;"></span>
              <span class="seller-legend-name">Allocated</span>
              <span class="seller-legend-pct">{alc_pct}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Recent Activity Card -->
      <div class="seller-card">
        <div class="seller-card-header">
          <div class="seller-card-title">Recent Activity</div>
          <a href="/seller/inventory" class="seller-header-link">View All &rarr;</a>
        </div>
        <div class="seller-card-body">
          <div class="seller-activity-list">
            {"".join(activity_items_html)}
          </div>
        </div>
      </div>
    </div>

    <!-- BOTTOM ROW: MY RECENT WASTE SUBMISSIONS & RECENT PURCHASE REQUESTS -->
    <div class="seller-grid-bottom">
      <!-- Left: My Recent Waste Submissions -->
      <div class="seller-card">
        <div class="seller-card-header">
          <div class="seller-card-title">My Recent Waste Submissions</div>
          <a href="/seller/inventory" class="seller-header-link">View All &rarr;</a>
        </div>
        <div class="seller-card-body" style="padding: 0;">
          <div class="seller-table-responsive">
            <table class="seller-data-table">
              <thead>
                <tr>
                  <th>Lot ID</th>
                  <th>Material</th>
                  <th>Quantity</th>
                  <th>Grade</th>
                  <th>Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {"".join(submissions_rows_html)}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Right: Recent Purchase Requests -->
      <div class="seller-card">
        <div class="seller-card-header">
          <div class="seller-card-title">Recent Purchase Requests</div>
          <a href="/seller/requests" class="seller-header-link">View All &rarr;</a>
        </div>
        <div class="seller-card-body" style="padding: 0;">
          <div class="seller-table-responsive">
            <table class="seller-data-table">
              <thead>
                <tr>
                  <th>Request ID</th>
                  <th>Buyer</th>
                  <th>Lot ID</th>
                  <th>Quantity</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {"".join(requests_rows_html)}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
    """

    return seller_layout("Seller Dashboard", "/seller", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 2. MY WASTE INVENTORY (/seller/inventory)
# ==============================================================================

def page_seller_inventory(handler, conn) -> str:
    """
    Renders the dedicated My Waste Inventory page:
    - Scoped strictly to the authenticated seller's lots
    - Filter by search keyword, material category, verification status
    - Sort by date and quantity
    - Lot details modal
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/inventory")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    user_id = user["id"]
    org_name = user.get("org_name", "")
    cursor = conn.cursor()

    stats = get_seller_stats(conn, user)

    # Fetch all lots for this seller
    cursor.execute("""
        SELECT id, code, category, qty_kg, grade, colour, contamination_pct,
               location_name, status, allocated, photo, notes, created_at,
               verification_notes
        FROM lots
        WHERE seller_id = ? OR (seller_id IS NULL AND source_name = ?)
        ORDER BY id DESC
    """, (user_id, org_name))
    lots = cursor.fetchall()

    lot_rows_html = []
    lot_details_json = []

    for lot in lots:
        st = lot["status"]
        badge_cls = "seller-badge b-pending"
        badge_lbl = "Pending Review"
        if st == "verified":
            badge_cls = "seller-badge b-verified"
            badge_lbl = "Verified QA"
        elif st == "rejected":
            badge_cls = "seller-badge b-rejected"
            badge_lbl = "Rejected"

        alloc_badge = '<span class="seller-pill-alloc" title="Allocated to circular batch">Allocated</span>' if lot["allocated"] else '<span class="seller-pill-avail" title="Available in feedstock pool">Available</span>'

        lot_dict = {
            "id": lot["id"],
            "code": lot["code"],
            "category": lot["category"],
            "qty_kg": lot["qty_kg"],
            "grade": lot["grade"],
            "colour": lot["colour"] or "Standard",
            "contamination_pct": lot["contamination_pct"],
            "location_name": lot["location_name"] or "Gazipur Facility",
            "status": lot["status"],
            "allocated": bool(lot["allocated"]),
            "photo": lot["photo"],
            "notes": lot["notes"] or "No notes provided.",
            "created_at": lot["created_at"],
            "verification_notes": lot["verification_notes"] or ""
        }
        lot_details_json.append(lot_dict)

        lot_rows_html.append(f"""
        <tr class="seller-lot-row" data-id="{lot['id']}" data-code="{e(lot['code']).lower()}" data-category="{e(lot['category']).lower()}" data-status="{st}" data-qty="{lot['qty_kg']}">
          <td><strong style="color: #FFFFFF;">{e(lot['code'])}</strong></td>
          <td>{e(lot['category'].title())}</td>
          <td><strong>{lot['qty_kg']:g} kg</strong></td>
          <td><span class="grade-pill">{e(lot['grade'])}</span></td>
          <td>{lot['contamination_pct']:g}%</td>
          <td style="color: #94A3B8;">{e(lot['location_name'] or 'Gazipur')}</td>
          <td><span class="{badge_cls}">{badge_lbl}</span></td>
          <td>{alloc_badge}</td>
          <td style="color: #94A3B8; font-size: 12.5px;">{e(lot['created_at'][:10] if lot['created_at'] else '—')}</td>
          <td>
            <button class="seller-btn-sm" onclick="openLotModal({lot['id']})">Details</button>
          </td>
        </tr>
        """)

    if not lot_rows_html:
        lot_rows_html.append("""
        <tr>
          <td colspan="10" style="text-align: center; color: #94A3B8; padding: 40px;">
            <div style="font-size: 32px; margin-bottom: 8px;">📦</div>
            <div style="font-size: 16px; color: #FFFFFF; font-weight: 600; margin-bottom: 6px;">No waste lots in inventory</div>
            <p style="margin-bottom: 16px;">You haven't submitted any waste lots yet. Start by logging your first cutting clip batch.</p>
            <a href="/seller/submit" class="seller-btn-primary" style="display: inline-flex;">Submit New Waste Lot</a>
          </td>
        </tr>
        """)

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">My Waste Inventory</h1>
        <p class="seller-page-sub">Comprehensive tracking of your facility's characterized secondary textile feedstock.</p>
      </div>
      <div class="seller-page-actions">
        <a href="/seller/submit" class="seller-btn-primary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>Submit New Waste</span>
        </a>
      </div>
    </div>

    <!-- INVENTORY METRICS SUMMARY STRIP -->
    <div class="seller-summary-strip">
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Total Inventory</span>
        <span class="seller-strip-val">{stats['total_kg']:,.0f} kg ({stats['total_lots']} lots)</span>
      </div>
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Verified & Ready</span>
        <span class="seller-strip-val" style="color: #10B981;">{stats['verified_kg']:,.0f} kg</span>
      </div>
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Pending QA Intake</span>
        <span class="seller-strip-val" style="color: #F59E0B;">{stats['pending_kg']:,.0f} kg</span>
      </div>
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Allocated to Batches</span>
        <span class="seller-strip-val" style="color: #06B6D4;">{stats['allocated_kg']:,.0f} kg</span>
      </div>
    </div>

    <!-- FILTER & SEARCH CONTROLS -->
    <div class="seller-filter-bar">
      <div class="seller-filter-search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="inventorySearchInput" placeholder="Search by Lot ID, category, location..." oninput="applyInventoryFilters()">
      </div>
      <div class="seller-filter-selects">
        <select id="categoryFilter" onchange="applyInventoryFilters()" class="seller-select">
          <option value="all">All Categories</option>
          <option value="cotton">Cotton</option>
          <option value="polyester">Polyester</option>
          <option value="denim">Denim</option>
          <option value="cotton-polyester blend">Cotton-Poly Blend</option>
          <option value="mixed textile waste">Mixed Waste</option>
        </select>
        <select id="statusFilter" onchange="applyInventoryFilters()" class="seller-select">
          <option value="all">All Verification Statuses</option>
          <option value="verified">Verified QA</option>
          <option value="pending">Pending QA</option>
          <option value="rejected">Rejected</option>
        </select>
        <select id="sortSelect" onchange="applyInventorySort()" class="seller-select">
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
          <option value="qty_desc">Quantity: High to Low</option>
          <option value="qty_asc">Quantity: Low to High</option>
        </select>
      </div>
    </div>

    <!-- INVENTORY TABLE CARD -->
    <div class="seller-card" style="margin-top: 18px;">
      <div class="seller-card-body" style="padding: 0;">
        <div class="seller-table-responsive">
          <table class="seller-data-table" id="inventoryTable">
            <thead>
              <tr>
                <th>Lot ID</th>
                <th>Category</th>
                <th>Quantity</th>
                <th>Grade</th>
                <th>Contam.</th>
                <th>Location</th>
                <th>Status</th>
                <th>Allocation</th>
                <th>Submitted</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="inventoryTableBody">
              {"".join(lot_rows_html)}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- LOT DETAILS MODAL -->
    <div class="seller-modal-backdrop" id="lotModalBackdrop" onclick="closeLotModal(event)">
      <div class="seller-modal-card" onclick="event.stopPropagation()">
        <div class="seller-modal-header">
          <div>
            <h3 class="seller-modal-title" id="mCode">Lot Details</h3>
            <span class="seller-modal-subtitle" id="mCategory">Feedstock Characteristics</span>
          </div>
          <button class="seller-modal-close" onclick="closeLotModal()">&times;</button>
        </div>
        <div class="seller-modal-body" id="mBody">
          <!-- Dynamic details injected here -->
        </div>
        <div class="seller-modal-footer">
          <button class="seller-btn-outline" onclick="closeLotModal()">Close</button>
        </div>
      </div>
    </div>

    <script>
    const LOTS_DATA = {json.dumps(lot_details_json)};

    function applyInventoryFilters() {{
      const query = (document.getElementById('inventorySearchInput').value || '').toLowerCase();
      const cat = document.getElementById('categoryFilter').value.toLowerCase();
      const st = document.getElementById('statusFilter').value;

      document.querySelectorAll('.seller-lot-row').forEach(row => {{
        const code = row.getAttribute('data-code') || '';
        const rowCat = row.getAttribute('data-category') || '';
        const rowSt = row.getAttribute('data-status') || '';
        const text = row.innerText.toLowerCase();

        const matchQuery = !query || text.includes(query);
        const matchCat = (cat === 'all') || (rowCat === cat);
        const matchSt = (st === 'all') || (rowSt === st);

        row.style.display = (matchQuery && matchCat && matchSt) ? '' : 'none';
      }});
    }}

    function applyInventorySort() {{
      const sortBy = document.getElementById('sortSelect').value;
      const tbody = document.getElementById('inventoryTableBody');
      const rows = Array.from(tbody.querySelectorAll('.seller-lot-row'));

      rows.sort((a, b) => {{
        if (sortBy === 'newest') return parseInt(b.getAttribute('data-id')) - parseInt(a.getAttribute('data-id'));
        if (sortBy === 'oldest') return parseInt(a.getAttribute('data-id')) - parseInt(b.getAttribute('data-id'));
        if (sortBy === 'qty_desc') return parseFloat(b.getAttribute('data-qty')) - parseFloat(a.getAttribute('data-qty'));
        if (sortBy === 'qty_asc') return parseFloat(a.getAttribute('data-qty')) - parseFloat(b.getAttribute('data-qty'));
        return 0;
      }});

      rows.forEach(r => tbody.appendChild(r));
    }}

    function openLotModal(lotId) {{
      const lot = LOTS_DATA.find(x => x.id === lotId);
      if (!lot) return;

      document.getElementById('mCode').innerText = lot.code;
      document.getElementById('mCategory').innerText = lot.category.toUpperCase() + ' • ' + lot.grade + ' GRADE';

      let photoHtml = '';
      if (lot.photo) {{
        photoHtml = `<div style="margin-bottom: 16px;"><img src="${{lot.photo}}" alt="Waste Lot Photo" style="width: 100%; max-height: 200px; object-fit: cover; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);"></div>`;
      }}

      let notesBadge = '';
      if (lot.verification_notes) {{
        notesBadge = `
        <div style="background: rgba(16,185,129,0.08); border-left: 3px solid #10B981; padding: 12px; border-radius: 4px; margin-top: 14px;">
          <div style="color: #10B981; font-weight: 600; font-size: 12px; margin-bottom: 4px;">INSPECTOR QA VERIFICATION NOTES</div>
          <div style="color: #E2E8F0; font-size: 13px;">${{lot.verification_notes}}</div>
        </div>`;
      }}

      document.getElementById('mBody').innerHTML = `
        ${{photoHtml}}
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px;">
          <div class="seller-info-cell">
            <span class="cell-label">Quantity</span>
            <span class="cell-val"><strong>${{lot.qty_kg}} kg</strong></span>
          </div>
          <div class="seller-info-cell">
            <span class="cell-label">Fabric Grade</span>
            <span class="cell-val"><span class="grade-pill">${{lot.grade}}</span></span>
          </div>
          <div class="seller-info-cell">
            <span class="cell-label">Color Profile</span>
            <span class="cell-val">${{lot.colour}}</span>
          </div>
          <div class="seller-info-cell">
            <span class="cell-label">Contamination</span>
            <span class="cell-val">${{lot.contamination_pct}}%</span>
          </div>
          <div class="seller-info-cell">
            <span class="cell-label">Intake Location</span>
            <span class="cell-val">${{lot.location_name}}</span>
          </div>
          <div class="seller-info-cell">
            <span class="cell-label">Verification Status</span>
            <span class="cell-val"><strong style="color: ${{lot.status === 'verified' ? '#10B981' : lot.status === 'rejected' ? '#EF4444' : '#F59E0B'}}">${{lot.status.toUpperCase()}}</strong></span>
          </div>
        </div>
        <div class="seller-info-cell" style="margin-bottom: 8px;">
          <span class="cell-label">Seller Lot Description & Handling Notes</span>
          <span class="cell-val" style="font-size: 13px; line-height: 1.5; color: #CBD5E1;">${{lot.notes}}</span>
        </div>
        ${{notesBadge}}
      `;

      document.getElementById('lotModalBackdrop').classList.add('open');
    }}

    function closeLotModal(e) {{
      document.getElementById('lotModalBackdrop').classList.remove('open');
    }}
    </script>
    """

    return seller_layout("My Waste Inventory", "/seller/inventory", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 3. SUBMIT NEW WASTE (/seller/submit)
# ==============================================================================

def page_seller_submit(handler, conn) -> str:
    """
    Renders the professional multi-section waste submission form:
    - Section 1: Material Identification (Category, Grade, Color, Sub-type)
    - Section 2: Quantity & Intake Specifications (Quantity kg, Contamination %, Factory Name)
    - Section 3: Facility Location & Notes
    - Section 4: Secure Photo / Documentation Upload
    - Includes CSRF token and client-side validation
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/submit")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    stats = get_seller_stats(conn, user)
    org_name = user.get("org_name", "")
    location_name = user.get("location_name") or "Gazipur"

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">Submit New Waste Lot</h1>
        <p class="seller-page-sub">Characterize and register secondary textile clips for intake QA verification and circular matchmaking.</p>
      </div>
      <div class="seller-page-actions">
        <a href="/seller/inventory" class="seller-btn-outline">
          &larr; Back to Inventory
        </a>
      </div>
    </div>

    <!-- SUBMISSION INFORMATION NOTICE -->
    <div class="seller-info-banner">
      <div class="seller-info-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      </div>
      <div class="seller-info-text">
        <strong>Intake QA Protocol:</strong> Submitted lots enter the <strong>PunorAI Admin Verification Queue</strong> with status <em>Pending</em>. Platform quality inspectors perform physical intake QA and optical scans before lots are cleared for buyer aggregation.
      </div>
    </div>

    <!-- MULTI-SECTION SUBMISSION FORM -->
    <form id="sellerSubmitForm" class="seller-submit-form" onsubmit="handleSellerSubmit(event)">
      <input type="hidden" name="csrf_token" id="csrfToken" value="{e(csrf_token)}">

      <!-- SECTION 1: MATERIAL DETAILS -->
      <div class="seller-form-section">
        <div class="seller-section-header">
          <div class="seller-section-num">1</div>
          <div>
            <div class="seller-section-title">Material Identification & Classification</div>
            <div class="seller-section-sub">Specify the primary fiber category, grade, and color profile</div>
          </div>
        </div>
        <div class="seller-section-body">
          <div class="seller-form-row">
            <div class="seller-form-group">
              <label for="category" class="seller-label">Material Category <span class="req">*</span></label>
              <select id="category" name="category" class="seller-input" required>
                <option value="" disabled selected>Select category...</option>
                <option value="cotton">100% Cotton</option>
                <option value="polyester">Polyester</option>
                <option value="cotton-polyester blend">Cotton-Polyester Blend</option>
                <option value="denim">Denim Scrap / Selvage</option>
                <option value="mixed textile waste">Mixed Textile Waste</option>
              </select>
            </div>
            <div class="seller-form-group">
              <label for="material_type" class="seller-label">Material Sub-Type / Description</label>
              <input type="text" id="material_type" name="material_type" class="seller-input" placeholder="e.g. Single Jersey 30s combed clips">
            </div>
          </div>

          <div class="seller-form-row">
            <div class="seller-form-group">
              <label class="seller-label">Fabric Grade <span class="req">*</span></label>
              <div class="seller-grade-selector">
                <label class="seller-grade-opt">
                  <input type="radio" name="grade" value="A" checked>
                  <span class="seller-grade-box">
                    <span class="grade-letter">A</span>
                    <span class="grade-desc">Clean, unmixed, production cutting clips (&lt; 2% contam.)</span>
                  </span>
                </label>
                <label class="seller-grade-opt">
                  <input type="radio" name="grade" value="B">
                  <span class="seller-grade-box">
                    <span class="grade-letter">B</span>
                    <span class="grade-desc">Sorted selvage, minor mixed threads (2% &ndash; 5% contam.)</span>
                  </span>
                </label>
                <label class="seller-grade-opt">
                  <input type="radio" name="grade" value="C">
                  <span class="seller-grade-box">
                    <span class="grade-letter">C</span>
                    <span class="grade-desc">Mixed floor collection, requires mechanical sorting</span>
                  </span>
                </label>
              </div>
            </div>
          </div>

          <div class="seller-form-row">
            <div class="seller-form-group">
              <label for="colour" class="seller-label">Color Profile</label>
              <input type="text" id="colour" name="colour" class="seller-input" placeholder="e.g. Raw White / Bleached / Navy Blue">
            </div>
            <div class="seller-form-group">
              <label for="composition" class="seller-label">Composition Detail (%)</label>
              <input type="text" id="composition" name="composition" class="seller-input" placeholder="e.g. 95% Cotton / 5% Elastane">
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION 2: QUANTITY & INTAKE QUALITY -->
      <div class="seller-form-section">
        <div class="seller-section-header">
          <div class="seller-section-num">2</div>
          <div>
            <div class="seller-section-title">Quantity & Quality Estimates</div>
            <div class="seller-section-sub">Measured weight in kilograms and estimated foreign matter contamination</div>
          </div>
        </div>
        <div class="seller-section-body">
          <div class="seller-form-row">
            <div class="seller-form-group">
              <label for="qty_kg" class="seller-label">Lot Quantity (kg) <span class="req">*</span></label>
              <input type="number" id="qty_kg" name="qty_kg" class="seller-input" min="1" step="0.5" placeholder="e.g. 500" required>
              <div class="seller-input-hint">Minimum lot intake: 1 kg. Commercial batch aggregation typically requires 250+ kg.</div>
            </div>
            <div class="seller-form-group">
              <label for="contamination_pct" class="seller-label">Estimated Contamination (%)</label>
              <div style="display: flex; align-items: center; gap: 12px;">
                <input type="range" id="contamination_slider" min="0" max="15" step="0.1" value="1.0" class="seller-range" oninput="document.getElementById('contamination_pct').value = this.value">
                <input type="number" id="contamination_pct" name="contamination_pct" min="0" max="15" step="0.1" value="1.0" class="seller-input" style="width: 80px;" oninput="document.getElementById('contamination_slider').value = this.value">
                <span style="color: #94A3B8;">%</span>
              </div>
              <div class="seller-input-hint">Optical scanner confirmation will determine final certified QA value.</div>
            </div>
          </div>

          <div class="seller-form-row">
            <div class="seller-form-group">
              <label for="source_name" class="seller-label">Facility / Mill Name</label>
              <input type="text" id="source_name" name="source_name" class="seller-input" value="{e(org_name)}" readonly style="opacity: 0.8; cursor: not-allowed;">
              <div class="seller-input-hint">Locked to authenticated facility ownership.</div>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION 3: LOCATION & NOTES -->
      <div class="seller-form-section">
        <div class="seller-section-header">
          <div class="seller-section-num">3</div>
          <div>
            <div class="seller-section-title">Facility Logistics & Handling Notes</div>
            <div class="seller-section-sub">Specify dispatch hub and special packaging or sorting instructions</div>
          </div>
        </div>
        <div class="seller-section-body">
          <div class="seller-form-row">
            <div class="seller-form-group">
              <label for="location_name" class="seller-label">Intake / Collection Location <span class="req">*</span></label>
              <input type="text" id="location_name" name="location_name" class="seller-input" value="{e(location_name)}" placeholder="e.g. Gazipur Industrial Zone, Building 3" required>
            </div>
          </div>
          <div class="seller-form-row">
            <div class="seller-form-group">
              <label for="notes" class="seller-label">Lot Handling Notes & Provenance</label>
              <textarea id="notes" name="notes" rows="3" class="seller-input" placeholder="e.g. Packaged in 50kg PP woven bags. Kept dry in cutting room storage. Ready for immediate truck pickup."></textarea>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION 4: SAFE PHOTO UPLOAD -->
      <div class="seller-form-section">
        <div class="seller-section-header">
          <div class="seller-section-num">4</div>
          <div>
            <div class="seller-section-title">Material Photograph (Safe Upload)</div>
            <div class="seller-section-sub">Upload an intake verification photo (PNG, JPG, or WEBP, max 5MB)</div>
          </div>
        </div>
        <div class="seller-section-body">
          <div class="seller-dropzone" id="photoDropzone" onclick="document.getElementById('photoInput').click()">
            <input type="file" id="photoInput" accept="image/png,image/jpeg,image/webp" style="display: none;" onchange="handlePhotoSelect(this)">
            <input type="hidden" id="photoData" name="photo_data" value="">
            <div id="dropzoneContent">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="1.8" style="margin-bottom: 8px;"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              <div style="color: #FFFFFF; font-weight: 600; font-size: 14px;">Click to select or drop material photo</div>
              <div style="color: #94A3B8; font-size: 12px; margin-top: 4px;">PNG, JPG, WEBP up to 5MB</div>
            </div>
            <div id="dropzonePreview" style="display: none; position: relative;">
              <img id="previewImg" src="" alt="Photo preview" style="max-height: 180px; border-radius: 8px; border: 1px solid rgba(16,185,129,0.3);">
              <button type="button" class="seller-btn-sm" style="position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.7);" onclick="removePhoto(event)">Remove</button>
            </div>
          </div>
        </div>
      </div>

      <!-- FORM SUBMISSION ACTIONS -->
      <div class="seller-form-footer">
        <button type="button" class="seller-btn-outline" onclick="window.location.href='/seller/inventory'">Cancel</button>
        <button type="submit" id="submitBtn" class="seller-btn-primary" style="padding: 12px 28px; font-size: 15px;">
          <span>Submit Waste Lot for Verification &rarr;</span>
        </button>
      </div>
    </form>

    <script>
    function handlePhotoSelect(input) {{
      const file = input.files[0];
      if (!file) return;

      if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {{
        alert('Invalid file format. Please upload a PNG, JPG, or WEBP photograph.');
        input.value = '';
        return;
      }}
      if (file.size > 5 * 1024 * 1024) {{
        alert('File size exceeds 5MB limit. Please choose a smaller image.');
        input.value = '';
        return;
      }}

      const reader = new FileReader();
      reader.onload = function(e) {{
        document.getElementById('photoData').value = e.target.result;
        document.getElementById('previewImg').src = e.target.result;
        document.getElementById('dropzoneContent').style.display = 'none';
        document.getElementById('dropzonePreview').style.display = 'block';
      }};
      reader.readAsDataURL(file);
    }}

    function removePhoto(e) {{
      e.stopPropagation();
      document.getElementById('photoInput').value = '';
      document.getElementById('photoData').value = '';
      document.getElementById('previewImg').src = '';
      document.getElementById('dropzoneContent').style.display = 'block';
      document.getElementById('dropzonePreview').style.display = 'none';
    }}

    async function handleSellerSubmit(e) {{
      e.preventDefault();
      const btn = document.getElementById('submitBtn');
      btn.disabled = true;
      btn.innerText = 'Submitting lot...';

      const payload = {{
        csrf_token: document.getElementById('csrfToken').value,
        category: document.getElementById('category').value,
        material_type: document.getElementById('material_type').value,
        grade: document.querySelector('input[name="grade"]:checked').value,
        colour: document.getElementById('colour').value,
        composition: document.getElementById('composition').value,
        qty_kg: parseFloat(document.getElementById('qty_kg').value),
        contamination_pct: parseFloat(document.getElementById('contamination_pct').value || '1.0'),
        location_name: document.getElementById('location_name').value,
        notes: document.getElementById('notes').value,
        photo_data: document.getElementById('photoData').value
      }};

      try {{
        const res = await fetch('/api/seller/submit', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        if (data.ok) {{
          showSellerToast('Waste lot ' + data.code + ' submitted successfully for QA verification!');
          setTimeout(() => {{
            window.location.href = data.redirect || '/seller/inventory';
          }}, 1200);
        }} else {{
          alert('Submission error: ' + (data.error || 'Failed to submit lot.'));
          btn.disabled = false;
          btn.innerHTML = '<span>Submit Waste Lot for Verification &rarr;</span>';
        }}
      }} catch (err) {{
        alert('Network error while submitting waste lot: ' + err.message);
        btn.disabled = false;
        btn.innerHTML = '<span>Submit Waste Lot for Verification &rarr;</span>';
      }}
    }}
    </script>
    """

    return seller_layout("Submit New Waste", "/seller/submit", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 4. VERIFICATION STATUS (/seller/verification)
# ==============================================================================

def page_seller_verification(handler, conn) -> str:
    """
    Renders the dedicated Verification Status tracking page:
    - Lists submitted lots and their intake QA status
    - Explains QA protocols and shows inspector notes
    - Highlights rejected lots and reason for remediation
    - Enforces that sellers cannot self-verify
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/verification")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    user_id = user["id"]
    org_name = user.get("org_name", "")
    cursor = conn.cursor()

    stats = get_seller_stats(conn, user)

    # Fetch lots for verification tracking
    cursor.execute("""
        SELECT l.id, l.code, l.category, l.qty_kg, l.grade, l.contamination_pct,
               l.status, l.created_at, l.verification_notes, l.verified_by,
               u.org_name as inspector_name
        FROM lots l
        LEFT JOIN users u ON l.verified_by = u.id
        WHERE l.seller_id = ? OR (l.seller_id IS NULL AND l.source_name = ?)
        ORDER BY l.id DESC
    """, (user_id, org_name))
    lots = cursor.fetchall()

    cards_html = []
    for lot in lots:
        st = lot["status"]
        if st == "verified":
            badge = '<span class="seller-badge b-verified">QA Verified & Cleared</span>'
            status_desc = "Intake inspection complete. Fiber composition confirmed. Eligible for buyer aggregation and batch optimization."
            icon = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>"""
            icon_cls = "qa-icon-box green"
        elif st == "rejected":
            badge = '<span class="seller-badge b-rejected">QA Rejected</span>'
            status_desc = "Lot failed intake criteria (e.g. moisture contamination, non-compliant blend, or foreign matter)."
            icon = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>"""
            icon_cls = "qa-icon-box red"
        else:
            badge = '<span class="seller-badge b-pending">Under Admin Review</span>'
            status_desc = "Queued for physical intake QA inspection and optical composition verification."
            icon = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>"""
            icon_cls = "qa-icon-box amber"

        notes_section = ""
        if lot["verification_notes"]:
            notes_section = f"""
            <div class="seller-qa-notes">
              <div class="qa-notes-title">Inspector Remarks:</div>
              <div class="qa-notes-text">{e(lot['verification_notes'])}</div>
            </div>
            """

        cards_html.append(f"""
        <div class="seller-qa-card">
          <div class="seller-qa-top">
            <div class="{icon_cls}">{icon}</div>
            <div class="seller-qa-main">
              <div class="seller-qa-header">
                <span class="seller-qa-code">{e(lot['code'])}</span>
                <span class="seller-qa-category">{e(lot['category'].title())} &bull; Grade {e(lot['grade'])}</span>
                {badge}
              </div>
              <div class="seller-qa-desc">{status_desc}</div>
            </div>
            <div class="seller-qa-stat">
              <div class="stat-kg">{lot['qty_kg']:g} kg</div>
              <div class="stat-sub">Submitted: {e(lot['created_at'][:10] if lot['created_at'] else '—')}</div>
            </div>
          </div>
          {notes_section}
        </div>
        """)

    if not cards_html:
        cards_html.append("""
        <div class="seller-card" style="padding: 40px; text-align: center; color: #94A3B8;">
          <div style="font-size: 32px; margin-bottom: 8px;">🛡️</div>
          <h3 style="color: #FFFFFF; margin-bottom: 8px;">No lots submitted for QA verification</h3>
          <p style="margin-bottom: 16px;">Once you submit waste lots, their verification status and inspector feedback will appear here.</p>
          <a href="/seller/submit" class="seller-btn-primary" style="display: inline-flex;">Submit New Waste</a>
        </div>
        """)

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">Waste Verification Status</h1>
        <p class="seller-page-sub">Independent intake QA and physical clearance tracking for secondary feedstock lots.</p>
      </div>
      <div class="seller-page-actions">
        <a href="/seller/submit" class="seller-btn-primary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>Submit Another Lot</span>
        </a>
      </div>
    </div>

    <!-- PROTOCOL HONESTY BANNER -->
    <div class="seller-info-banner">
      <div class="seller-info-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
      </div>
      <div class="seller-info-text">
        <strong>Governance Boundary Notice:</strong> Verification decisions are managed exclusively by <strong>PunorAI Platform Operations</strong>. To maintain chain-of-custody integrity, sellers cannot approve their own submissions or alter verification determinations.
      </div>
    </div>

    <div class="seller-qa-list" style="margin-top: 20px;">
      {"".join(cards_html)}
    </div>
    """

    return seller_layout("Verification Status", "/seller/verification", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 5. PURCHASE REQUESTS (/seller/requests)
# ==============================================================================

def page_seller_requests(handler, conn) -> str:
    """
    Renders Buyer Purchase Requests scoped to the authenticated seller's lots:
    - Lists buyer interest in the seller's verified stock
    - Displays offered price per kg, requested volume, buyer company
    - Clarifies that Admin coordinates escrow and transaction lifecycle
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/requests")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    user_id = user["id"]
    org_name = user.get("org_name", "")
    cursor = conn.cursor()

    stats = get_seller_stats(conn, user)

    # Fetch purchase requests for this seller's lots
    cursor.execute("""
        SELECT pr.id, pr.code, pr.requested_qty_kg, pr.offered_price_per_kg,
               pr.notes, pr.status, pr.admin_notes, pr.created_at,
               u.org_name as buyer_name, u.email as buyer_email,
               l.code as lot_code, l.category as lot_category, l.qty_kg as lot_total_kg
        FROM purchase_requests pr
        JOIN lots l ON pr.lot_id = l.id
        JOIN users u ON pr.buyer_id = u.id
        WHERE l.seller_id = ? OR (l.seller_id IS NULL AND l.source_name = ?)
        ORDER BY pr.id DESC
    """, (user_id, org_name))
    requests = cursor.fetchall()

    req_rows_html = []
    for req in requests:
        st = req["status"]
        if st in ("admin_approved", "approved"):
            badge = '<span class="seller-badge b-verified">Admin Approved</span>'
        elif st == "rejected":
            badge = '<span class="seller-badge b-rejected">Rejected</span>'
        elif st == "fulfilled":
            badge = '<span class="seller-badge b-verified" style="background: rgba(52,211,153,0.15); color: #34D399;">Fulfilled</span>'
        else:
            badge = '<span class="seller-badge b-pending">Pending Admin Review</span>'

        total_offer = req["requested_qty_kg"] * req["offered_price_per_kg"]

        req_rows_html.append(f"""
        <tr>
          <td><strong style="color: #FFFFFF;">{e(req['code'])}</strong></td>
          <td>
            <div style="font-weight: 600; color: #FFFFFF;">{e(req['buyer_name'])}</div>
            <div style="font-size: 11.5px; color: #94A3B8;">{e(req['buyer_email'])}</div>
          </td>
          <td>
            <span style="color: #10B981; font-weight: 600;">{e(req['lot_code'])}</span>
            <span style="font-size: 12px; color: #94A3B8;">({e(req['lot_category'].title())})</span>
          </td>
          <td><strong>{req['requested_qty_kg']:g} kg</strong></td>
          <td><strong>{req['offered_price_per_kg']:g} BDT</strong></td>
          <td style="color: #34D399; font-weight: 700;">{total_offer:,.0f} BDT</td>
          <td>{badge}</td>
          <td style="color: #94A3B8; font-size: 12.5px;">{e(req['created_at'][:10] if req['created_at'] else '—')}</td>
        </tr>
        """)

    if not req_rows_html:
        req_rows_html.append("""
        <tr>
          <td colspan="8" style="text-align: center; color: #94A3B8; padding: 40px;">
            <div style="font-size: 32px; margin-bottom: 8px;">🛒</div>
            <div style="font-size: 16px; color: #FFFFFF; font-weight: 600; margin-bottom: 6px;">No purchase requests yet</div>
            <p style="margin-bottom: 0;">When verified recyclers and spinning mills place purchase requests for your stock, they will appear here.</p>
          </td>
        </tr>
        """)

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">Buyer Purchase Requests</h1>
        <p class="seller-page-sub">Procurement inquiries and price offers submitted by verified recyclers for your lots.</p>
      </div>
      <div class="seller-page-actions">
        <a href="/seller/inventory" class="seller-btn-outline">
          View My Stock
        </a>
      </div>
    </div>

    <!-- ESCROW PROTOCOL NOTICE -->
    <div class="seller-info-banner">
      <div class="seller-info-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
      </div>
      <div class="seller-info-text">
        <strong>Aggregation & Transaction Escrow:</strong> PunorAI platform operations validates buyer solvency and coordinates batch aggregation logistics. Once an offer is approved by Admin, you will receive collection dispatch instructions.
      </div>
    </div>

    <!-- REQUESTS TABLE CARD -->
    <div class="seller-card" style="margin-top: 18px;">
      <div class="seller-card-body" style="padding: 0;">
        <div class="seller-table-responsive">
          <table class="seller-data-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Buyer Recycler</th>
                <th>Target Lot</th>
                <th>Requested Qty</th>
                <th>Offered Price/kg</th>
                <th>Total Value</th>
                <th>Status</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {"".join(req_rows_html)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    """

    return seller_layout("Purchase Requests", "/seller/requests", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 6. MY TRANSACTIONS (/seller/transactions)
# ==============================================================================

def page_seller_transactions(handler, conn) -> str:
    """
    Renders completed and scheduled transactions associated with this Seller:
    - Transaction ID, buyer, volume, settlement amount, handover status, passport code
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/transactions")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    user_id = user["id"]
    cursor = conn.cursor()

    stats = get_seller_stats(conn, user)

    # Fetch transactions where seller_id = user["id"]
    cursor.execute("""
        SELECT t.id, t.code, t.qty_kg, t.price_per_kg, t.total_amount,
               t.handover_status, t.passport_code, t.created_at, t.completed_at,
               u.org_name as buyer_name, l.code as lot_code, l.category as lot_category
        FROM transactions t
        JOIN users u ON t.buyer_id = u.id
        LEFT JOIN lots l ON t.lot_id = l.id
        WHERE t.seller_id = ?
        ORDER BY t.id DESC
    """, (user_id,))
    txs = cursor.fetchall()

    tx_rows_html = []
    for tx in txs:
        st = tx["handover_status"]
        if st == "completed":
            badge = '<span class="seller-badge b-verified">Completed</span>'
        elif st == "in_transit":
            badge = '<span class="seller-badge b-pending" style="background: rgba(6,182,212,0.15); color: #06B6D4;">In Transit</span>'
        else:
            badge = '<span class="seller-badge b-pending">Scheduled</span>'

        passport_link = f'<a href="/passport/{e(tx["passport_code"])}" class="seller-table-link">{e(tx["passport_code"])}</a>' if tx["passport_code"] else '<span style="color:#64748B;">Pending</span>'

        tx_rows_html.append(f"""
        <tr>
          <td><strong style="color: #FFFFFF;">{e(tx['code'])}</strong></td>
          <td>{e(tx['buyer_name'])}</td>
          <td><span style="color: #10B981;">{e(tx['lot_code'] or 'Batch Lot')}</span></td>
          <td><strong>{tx['qty_kg']:g} kg</strong></td>
          <td>{tx['price_per_kg']:g} BDT</td>
          <td><strong style="color: #34D399;">{tx['total_amount']:,.0f} BDT</strong></td>
          <td>{badge}</td>
          <td>{passport_link}</td>
          <td style="color: #94A3B8; font-size: 12.5px;">{e(tx['completed_at'] or tx['created_at'][:10])}</td>
        </tr>
        """)

    if not tx_rows_html:
        tx_rows_html.append("""
        <tr>
          <td colspan="9" style="text-align: center; color: #94A3B8; padding: 40px;">
            <div style="font-size: 32px; margin-bottom: 8px;">🤝</div>
            <div style="font-size: 16px; color: #FFFFFF; font-weight: 600; margin-bottom: 6px;">No completed transactions yet</div>
            <p style="margin-bottom: 0;">Completed feedstocks sales and circular settlements will be recorded here.</p>
          </td>
        </tr>
        """)

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">My Transactions</h1>
        <p class="seller-page-sub">Traceable settlement ledger and delivery handovers for secondary textile feedstock.</p>
      </div>
    </div>

    <!-- TRANSACTION SUMMARY METRICS -->
    <div class="seller-summary-strip">
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Total Volume Sold</span>
        <span class="seller-strip-val" style="color: #10B981;">{stats['transacted_kg']:,.0f} kg</span>
      </div>
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Total Revenue (BDT)</span>
        <span class="seller-strip-val" style="color: #34D399;">{stats['total_revenue']:,.0f} BDT</span>
      </div>
      <div class="seller-strip-pill">
        <span class="seller-strip-label">Completed Settlements</span>
        <span class="seller-strip-val">{stats['total_transactions']} Transfers</span>
      </div>
    </div>

    <!-- TRANSACTIONS LEDGER CARD -->
    <div class="seller-card" style="margin-top: 18px;">
      <div class="seller-card-body" style="padding: 0;">
        <div class="seller-table-responsive">
          <table class="seller-data-table">
            <thead>
              <tr>
                <th>Transaction ID</th>
                <th>Buyer Recycler</th>
                <th>Material Lot</th>
                <th>Volume</th>
                <th>Unit Price</th>
                <th>Total Payout</th>
                <th>Handover</th>
                <th>Passport</th>
                <th>Settlement Date</th>
              </tr>
            </thead>
            <tbody>
              {"".join(tx_rows_html)}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    """

    return seller_layout("My Transactions", "/seller/transactions", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 7. MATERIAL PASSPORTS (/seller/passports)
# ==============================================================================

def page_seller_passports(handler, conn) -> str:
    """
    Renders Digital Material Passports associated with the seller's lots:
    - Finds batches containing this seller's feedstock
    - Links to existing passport certificate (/passport/{code})
    - Shows QR verification and batch composition
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/passports")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    user_id = user["id"]
    org_name = user.get("org_name", "")
    cursor = conn.cursor()

    stats = get_seller_stats(conn, user)

    # Find batches that include lots owned by this seller
    cursor.execute("""
        SELECT DISTINCT b.id, b.code, b.total_kg, b.buyer_name, b.status, b.created_at,
                        bl.lot_id, l.code as lot_code, l.qty_kg as lot_kg, l.category as lot_category
        FROM batches b
        JOIN batch_lots bl ON b.id = bl.batch_id
        JOIN lots l ON bl.lot_id = l.id
        WHERE l.seller_id = ? OR (l.seller_id IS NULL AND l.source_name = ?)
        ORDER BY b.id DESC
    """, (user_id, org_name))
    batch_rows = cursor.fetchall()

    passport_cards_html = []
    # Group by batch
    seen_batches = set()
    for row in batch_rows:
        bid = row["id"]
        if bid in seen_batches:
            continue
        seen_batches.add(bid)

        batch_code = row["code"]
        total_kg = row["total_kg"]
        my_contrib_kg = row["lot_kg"]
        contrib_pct = round((my_contrib_kg / max(total_kg, 1.0)) * 100)

        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=110x110&data={urllib.parse.quote(batch_code)}"

        passport_cards_html.append(f"""
        <div class="seller-passport-card">
          <div class="passport-card-left">
            <div class="passport-badge">Digital Material Passport</div>
            <h3 class="passport-code">{e(batch_code)}</h3>
            <div class="passport-meta">
              <span>Recycler Recipient: <strong>{e(row['buyer_name'])}</strong></span> &bull;
              <span>Batch Total: <strong>{total_kg:,.0f} kg</strong></span>
            </div>
            <div class="passport-contrib-box">
              <span class="contrib-label">Your Facility Contribution:</span>
              <span class="contrib-val">{my_contrib_kg:g} kg ({contrib_pct}% of batch) &bull; Lot {e(row['lot_code'])}</span>
            </div>
            <div class="passport-actions">
              <a href="/passport/{e(batch_code)}" class="seller-btn-primary" style="font-size: 13px; padding: 8px 16px;">
                Open Passport Certificate &rarr;
              </a>
            </div>
          </div>
          <div class="passport-card-right">
            <img src="{qr_url}" alt="Passport QR" class="seller-qr-img" onerror="this.style.opacity='0.25'; this.title='QR preview offline';">
            <span class="qr-label">Scan to verify circular chain-of-custody</span>
          </div>
        </div>
        """)

    if not passport_cards_html:
        passport_cards_html.append("""
        <div class="seller-card" style="padding: 40px; text-align: center; color: #94A3B8;">
          <div style="font-size: 32px; margin-bottom: 8px;">📜</div>
          <h3 style="color: #FFFFFF; margin-bottom: 8px;">No Material Passports issued yet</h3>
          <p style="max-width: 460px; margin: 0 auto 16px;">Material Passports are automatically generated when verified waste lots are aggregated into an optimized buyer batch.</p>
          <a href="/seller/submit" class="seller-btn-primary" style="display: inline-flex;">Submit Waste Lot</a>
        </div>
        """)

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">Material Passports & Provenance</h1>
        <p class="seller-page-sub">Verifiable digital product passports documenting batch custody, optical QA, and textile recycling provenance.</p>
      </div>
    </div>

    <!-- PASSPORTS LIST -->
    <div class="seller-passports-list" style="margin-top: 18px;">
      {"".join(passport_cards_html)}
    </div>
    """

    return seller_layout("Material Passports", "/seller/passports", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER PAGE: 8. ACCOUNT SETTINGS (/seller/settings)
# ==============================================================================

def page_seller_settings(handler, conn) -> str:
    """
    Renders the Seller Profile & Facility Settings page:
    - View/update organization name, facility address, contact person, phone
    - CSRF protection
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        handler._redirect("/login?redirect=/seller/settings")
        return ""
    if user["role"] != "seller":
        return render_seller_access_denied(user, "Seller")

    stats = get_seller_stats(conn, user)

    org_name = user.get("org_name", "")
    contact_name = user.get("contact_name", "")
    phone = user.get("phone", "")
    location_name = user.get("location_name", "")
    email = user.get("email", "")

    body = f"""
    <div class="seller-page-header">
      <div>
        <h1 class="seller-page-title">Account & Facility Settings</h1>
        <p class="seller-page-sub">Manage your textile manufacturing profile, intake location, and authorized contact information.</p>
      </div>
    </div>

    <div class="seller-settings-grid">
      <!-- Left Column: Settings Form -->
      <div class="seller-card">
        <div class="seller-card-header">
          <div class="seller-card-title">Mill & Logistics Profile</div>
        </div>
        <div class="seller-card-body">
          <form id="sellerSettingsForm" onsubmit="handleSettingsUpdate(event)">
            <input type="hidden" id="settingsCsrf" value="{e(csrf_token)}">

            <div class="seller-form-group" style="margin-bottom: 16px;">
              <label for="setOrg" class="seller-label">Organization / Factory Name <span class="req">*</span></label>
              <input type="text" id="setOrg" class="seller-input" value="{e(org_name)}" required>
            </div>

            <div class="seller-form-group" style="margin-bottom: 16px;">
              <label for="setContact" class="seller-label">Authorized Representative Name</label>
              <input type="text" id="setContact" class="seller-input" value="{e(contact_name)}" placeholder="e.g. Factory Logistics Manager">
            </div>

            <div class="seller-form-group" style="margin-bottom: 16px;">
              <label for="setPhone" class="seller-label">Contact Phone / Dispatch Hotline</label>
              <input type="text" id="setPhone" class="seller-input" value="{e(phone)}" placeholder="e.g. +880 1711-000000">
            </div>

            <div class="seller-form-group" style="margin-bottom: 24px;">
              <label for="setLocation" class="seller-label">Intake & Dispatch Hub Location</label>
              <input type="text" id="setLocation" class="seller-input" value="{e(location_name)}" placeholder="e.g. Gazipur Industrial Estate, Dhaka">
              <div class="seller-input-hint">Used for logistics route calculation and batch aggregation planning.</div>
            </div>

            <button type="submit" id="saveSettingsBtn" class="seller-btn-primary">
              Save Profile Changes
            </button>
          </form>
        </div>
      </div>

      <!-- Right Column: Account Security & Status -->
      <div class="seller-card">
        <div class="seller-card-header">
          <div class="seller-card-title">Account & Authentication Status</div>
        </div>
        <div class="seller-card-body">
          <div class="seller-info-cell" style="margin-bottom: 14px;">
            <span class="cell-label">Registered Email</span>
            <span class="cell-val"><code style="color: #10B981;">{e(email)}</code></span>
          </div>
          <div class="seller-info-cell" style="margin-bottom: 14px;">
            <span class="cell-label">Platform Role</span>
            <span class="cell-val"><span class="seller-badge b-verified">Verified Supplier (Seller)</span></span>
          </div>
          <div class="seller-info-cell" style="margin-bottom: 14px;">
            <span class="cell-label">Credential Security</span>
            <span class="cell-val">PBKDF2-HMAC-SHA256 (100k rounds)</span>
          </div>
          <div class="seller-info-cell" style="margin-bottom: 14px;">
            <span class="cell-label">Session Protection</span>
            <span class="cell-val">HttpOnly, SameSite Lax, 256-bit CSRF</span>
          </div>
          <div class="seller-info-cell">
            <span class="cell-label">Account Created</span>
            <span class="cell-val" style="color: #94A3B8;">{e(user.get('created_at', '2026-11-02')[:10])}</span>
          </div>
        </div>
      </div>
    </div>

    <script>
    async function handleSettingsUpdate(e) {{
      e.preventDefault();
      const btn = document.getElementById('saveSettingsBtn');
      btn.disabled = true;
      btn.innerText = 'Saving changes...';

      const payload = {{
        csrf_token: document.getElementById('settingsCsrf').value,
        org_name: document.getElementById('setOrg').value,
        contact_name: document.getElementById('setContact').value,
        phone: document.getElementById('setPhone').value,
        location_name: document.getElementById('setLocation').value
      }};

      try {{
        const res = await fetch('/api/seller/settings', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        if (data.ok) {{
          showSellerToast('Facility profile updated successfully!');
          setTimeout(() => window.location.reload(), 1000);
        }} else {{
          alert('Update error: ' + (data.error || 'Failed to update settings.'));
          btn.disabled = false;
          btn.innerText = 'Save Profile Changes';
        }}
      }} catch (err) {{
        alert('Network error: ' + err.message);
        btn.disabled = false;
        btn.innerText = 'Save Profile Changes';
      }}
    }}
    </script>
    """

    return seller_layout("Account Settings", "/seller/settings", body, user, counts=stats, csrf_token=csrf_token)


# ==============================================================================
# SELLER API ENDPOINTS
# ==============================================================================

def api_seller_submit_lot(handler, payload: dict, conn) -> dict:
    """
    Submits a new waste lot scoped strictly to the authenticated Seller:
      - Enforces seller role and valid session
      - Validates CSRF token
      - Associates new lot with authenticated user['id']
      - Sets initial status = 'pending', allocated = 0
      - Validates quantity, category, grade, contamination
      - Decodes and writes photo safely (if provided)
      - Records audit event in events table
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user or user["role"] != "seller":
        return {"ok": False, "error": "Unauthorized. Seller authentication required."}

    submitted_csrf = payload.get("csrf_token")
    if not auth.verify_csrf(csrf_token, submitted_csrf):
        return {"ok": False, "error": "CSRF validation failed. Refresh the page and try again."}

    category = (payload.get("category") or "").strip().lower()
    valid_categories = {"cotton", "polyester", "cotton-polyester blend", "denim", "mixed textile waste"}
    if category not in valid_categories:
        return {"ok": False, "error": f"Invalid material category. Must be one of: {', '.join(sorted(valid_categories))}"}

    try:
        qty_kg = float(payload.get("qty_kg", 0))
        if qty_kg <= 0:
            return {"ok": False, "error": "Lot quantity must be a positive number greater than 0 kg."}
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid lot quantity."}

    try:
        contamination_pct = float(payload.get("contamination_pct", 1.0))
        contamination_pct = max(0.0, min(100.0, contamination_pct))
    except (TypeError, ValueError):
        contamination_pct = 1.0

    grade = (payload.get("grade") or "B").strip().upper()
    if grade not in ("A", "B", "C"):
        grade = "B"

    colour = (payload.get("colour") or "").strip()
    material_type = (payload.get("material_type") or "").strip()
    location_name = (payload.get("location_name") or user.get("location_name") or "Gazipur").strip()
    notes = (payload.get("notes") or "").strip()
    if material_type:
        notes = f"{material_type}. {notes}".strip()

    # Safe Photo Processing
    photo_path = ""
    photo_data = payload.get("photo_data", "")
    if photo_data and "," in photo_data and len(photo_data) < 7_000_000: # ~5MB base64
        header, b64_str = photo_data.split(",", 1)
        ext = "jpg"
        if "png" in header.lower():
            ext = "png"
        elif "webp" in header.lower():
            ext = "webp"
        
        now_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"lot_seller_{user['id']}_{now_ts}.{ext}"
        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        target_path = os.path.join(uploads_dir, fn)
        try:
            with open(target_path, "wb") as f:
                f.write(base64.b64decode(b64_str))
            photo_path = f"/static/uploads/{fn}"
        except Exception as pe:
            print(f"[SELLER_SUBMIT] Photo write warning: {pe}")
            photo_path = ""

    # Generate sequential unique lot code
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as n FROM lots")
    cnt = cursor.fetchone()["n"] + 1
    code = f"LOT-S{user['id']}-{cnt:03d}"
    
    while cursor.execute("SELECT COUNT(*) as n FROM lots WHERE code=?", (code,)).fetchone()["n"] > 0:
        cnt += 1
        code = f"LOT-S{user['id']}-{cnt:03d}"

    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    source_name = user.get("org_name") or "Seller Facility"

    cursor.execute("""
        INSERT INTO lots (
            code, source_name, source_type, category, grade, colour,
            contamination_pct, qty_kg, lat, lon, location_name,
            status, photo, notes, allocated, created_at, seller_id,
            verified_by, verification_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '')
    """, (
        code, source_name, "factory", category, grade, colour,
        contamination_pct, qty_kg, user.get("lat", 23.81), user.get("lon", 90.41), location_name,
        "pending", photo_path, notes, 0, now_iso, user["id"]
    ))
    lot_id = cursor.lastrowid

    # Add audit event
    cursor.execute("""
        INSERT INTO events (batch_id, ts, description)
        VALUES (NULL, ?, ?)
    """, (now_iso, f"New waste lot submitted: {code} ({qty_kg:g} kg, {category}) by {source_name}. Status: Pending QA."))

    conn.commit()

    return {
        "ok": True,
        "lot_id": lot_id,
        "code": code,
        "message": f"Waste lot {code} submitted successfully for QA verification.",
        "redirect": "/seller/inventory"
    }


def api_seller_update_settings(handler, payload: dict, conn) -> dict:
    """
    Updates the permitted facility settings for the authenticated Seller:
      - Validates session, role, and CSRF token
      - Updates org_name, contact_name, phone, location_name
    """
    user, csrf_token = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user or user["role"] != "seller":
        return {"ok": False, "error": "Unauthorized. Seller authentication required."}

    submitted_csrf = payload.get("csrf_token")
    if not auth.verify_csrf(csrf_token, submitted_csrf):
        return {"ok": False, "error": "CSRF validation failed."}

    org_name = (payload.get("org_name") or "").strip()
    if not org_name:
        return {"ok": False, "error": "Organization or factory name cannot be empty."}

    contact_name = (payload.get("contact_name") or "").strip()
    phone = (payload.get("phone") or "").strip()
    location_name = (payload.get("location_name") or "").strip()

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users
        SET org_name = ?, contact_name = ?, phone = ?, location_name = ?
        WHERE id = ?
    """, (org_name, contact_name, phone, location_name, user["id"]))
    conn.commit()

    return {"ok": True, "message": "Facility settings updated successfully."}
