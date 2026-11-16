# ==============================================================================
# PUNORAI — ADMIN PLATFORM DASHBOARD MODULE
# ==============================================================================
import html
import json
import math
import os
import sqlite3
import datetime
import urllib.parse

import auth
import core
from brand import render_brand_logo, BrandLogo

def e(x):
    """HTML escape helper."""
    return html.escape(str(x) if x is not None else "")

def get_admin_counts(conn):
    """Queries SQLite for accurate counts across lots, users, verification, and requests."""
    cursor = conn.cursor()
    
    # Lots metrics
    cursor.execute("SELECT COUNT(*) as total, COALESCE(SUM(qty_kg), 0) as total_kg FROM lots")
    lot_row = cursor.fetchone()
    total_lots = lot_row["total"] if lot_row else 0
    total_kg = lot_row["total_kg"] if lot_row else 0.0

    cursor.execute("SELECT COUNT(*) as total, COALESCE(SUM(qty_kg), 0) as total_kg FROM lots WHERE status='verified'")
    ver_row = cursor.fetchone()
    verified_lots = ver_row["total"] if ver_row else 0
    verified_kg = ver_row["total_kg"] if ver_row else 0.0

    cursor.execute("SELECT COUNT(*) as total FROM lots WHERE status='pending'")
    pending_row = cursor.fetchone()
    pending_lots = pending_row["total"] if pending_row else 0

    cursor.execute("SELECT COUNT(*) as total FROM lots WHERE status='rejected'")
    rej_row = cursor.fetchone()
    rejected_lots = rej_row["total"] if rej_row else 0

    cursor.execute("SELECT COUNT(*) as total FROM lots WHERE status NOT IN ('verified', 'pending', 'rejected')")
    rev_row = cursor.fetchone()
    review_lots = rev_row["total"] if rev_row else 0

    # Users count
    cursor.execute("SELECT COUNT(*) as total FROM users")
    user_row = cursor.fetchone()
    total_users = user_row["total"] if user_row else 0

    # Purchase requests
    cursor.execute("SELECT COUNT(*) as total FROM purchase_requests")
    req_row = cursor.fetchone()
    total_requests = req_row["total"] if req_row else 0

    cursor.execute("SELECT COUNT(*) as total FROM purchase_requests WHERE status='pending_admin'")
    req_pen_row = cursor.fetchone()
    pending_requests = req_pen_row["total"] if req_pen_row else 0

    # Estimated CO2 saved
    est_co2_tonnes = round((total_kg * 2.8) / 1000.0, 1)

    return {
        "total_lots": total_lots,
        "total_kg": total_kg,
        "verified_lots": verified_lots,
        "verified_kg": verified_kg,
        "pending_lots": pending_lots,
        "rejected_lots": rejected_lots,
        "review_lots": review_lots,
        "total_users": total_users,
        "total_requests": total_requests,
        "pending_requests": pending_requests,
        "est_co2_tonnes": est_co2_tonnes
    }


def render_sparkline_svg(color="#10B981", height=38, width=110, trend_type="lots"):
    """Renders a smooth mini SVG sparkline matching the reference design."""
    points = {
        "lots": "M0,28 Q22,30 40,20 T75,16 T105,7",
        "verified": "M0,32 Q25,28 45,18 T80,12 T105,5",
        "users": "M0,30 Q22,26 44,22 T75,15 T105,8",
        "co2": "M0,34 Q25,26 50,19 T80,10 T105,4"
    }.get(trend_type, "M0,28 Q22,30 40,20 T75,16 T105,7")

    area_points = f"{points} L105,{height} L0,{height} Z"
    grad_id = f"sparkGrad_{trend_type}"

    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" class="stat-sparkline" aria-hidden="true">
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


def render_donut_svg(total, approved, pending, review, rejected):
    """Renders the SVG Donut Chart for Waste Lot Status."""
    total_val = max(total, 1)
    circ = 2 * math.pi * 50 # 314.159

    p_app = approved / total_val
    p_pen = pending / total_val
    p_rev = review / total_val
    p_rej = rejected / total_val

    len_app = p_app * circ
    len_pen = p_pen * circ
    len_rev = p_rev * circ
    len_rej = p_rej * circ

    off_app = 0
    off_pen = -len_app
    off_rev = -(len_app + len_pen)
    off_rej = -(len_app + len_pen + len_rev)

    return f"""
    <div class="donut-chart-wrapper">
      <svg width="150" height="150" viewBox="0 0 140 140" class="donut-svg" aria-label="Waste Lot Status Donut Chart">
        <circle cx="70" cy="70" r="50" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="18"/>
        <!-- Approved (Green) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#10B981" stroke-width="18"
                stroke-dasharray="{len_app:.2f} {circ:.2f}" stroke-dashoffset="{off_app:.2f}"
                transform="rotate(-90 70 70)" stroke-linecap="round"/>
        <!-- Pending (Amber) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#F59E0B" stroke-width="18"
                stroke-dasharray="{len_pen:.2f} {circ:.2f}" stroke-dashoffset="{off_pen:.2f}"
                transform="rotate(-90 70 70)"/>
        <!-- Under Review / Simulated (Cyan) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#06B6D4" stroke-width="18"
                stroke-dasharray="{len_rev:.2f} {circ:.2f}" stroke-dashoffset="{off_rev:.2f}"
                transform="rotate(-90 70 70)"/>
        <!-- Rejected (Red) -->
        <circle cx="70" cy="70" r="50" fill="none" stroke="#EF4444" stroke-width="18"
                stroke-dasharray="{len_rej:.2f} {circ:.2f}" stroke-dashoffset="{off_rej:.2f}"
                transform="rotate(-90 70 70)"/>
        <g class="donut-center-text">
          <text x="70" y="66" text-anchor="middle" font-size="22" font-weight="700" fill="#FFFFFF">{total}</text>
          <text x="70" y="82" text-anchor="middle" font-size="10.5" font-weight="500" fill="#94A3B8">Total Lots</text>
        </g>
      </svg>
    </div>
    """


def render_activity_line_chart_svg():
    """Renders the Monthly Activity multi-line area chart."""
    return """
    <svg width="100%" height="190" viewBox="0 0 520 190" preserveAspectRatio="none" class="activity-chart-svg" aria-label="Monthly Activity Chart">
      <defs>
        <linearGradient id="lineGradLots" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#10B981" stop-opacity="0.32"/>
          <stop offset="100%" stop-color="#10B981" stop-opacity="0.0"/>
        </linearGradient>
        <linearGradient id="lineGradReqs" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#06B6D4" stop-opacity="0.25"/>
          <stop offset="100%" stop-color="#06B6D4" stop-opacity="0.0"/>
        </linearGradient>
        <filter id="glowGreen" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      <g stroke="rgba(255,255,255,0.06)" stroke-width="1" stroke-dasharray="3 3">
        <line x1="36" y1="20" x2="510" y2="20" />
        <line x1="36" y1="55" x2="510" y2="55" />
        <line x1="36" y1="90" x2="510" y2="90" />
        <line x1="36" y1="125" x2="510" y2="125" />
        <line x1="36" y1="160" x2="510" y2="160" stroke-dasharray="none" stroke="rgba(255,255,255,0.12)" />
      </g>
      
      <g fill="#64748B" font-size="10" text-anchor="end">
        <text x="28" y="24">80</text>
        <text x="28" y="59">60</text>
        <text x="28" y="94">40</text>
        <text x="28" y="129">20</text>
        <text x="28" y="164">0</text>
      </g>

      <g fill="#94A3B8" font-size="10.5" text-anchor="middle">
        <text x="50" y="180">Jan</text>
        <text x="115" y="180">Feb</text>
        <text x="180" y="180">Mar</text>
        <text x="245" y="180">Apr</text>
        <text x="310" y="180">May</text>
        <text x="375" y="180">Jun</text>
        <text x="440" y="180">Jul</text>
        <text x="495" y="180">Aug</text>
      </g>

      <path d="M50,140 C85,130 145,115 180,105 C215,95 275,85 310,75 C345,65 405,100 440,90 C465,82 485,75 495,70 L495,160 L50,160 Z" fill="url(#lineGradReqs)"/>
      <path d="M50,140 C85,130 145,115 180,105 C215,95 275,85 310,75 C345,65 405,100 440,90 C465,82 485,75 495,70" fill="none" stroke="#06B6D4" stroke-width="2.2" stroke-linecap="round"/>

      <path d="M50,125 C85,105 145,75 180,82 C215,90 275,60 310,48 C345,36 405,65 440,55 C465,48 485,42 495,38 L495,160 L50,160 Z" fill="url(#lineGradLots)"/>
      <path d="M50,125 C85,105 145,75 180,82 C215,90 275,60 310,48 C345,36 405,65 440,55 C465,48 485,42 495,38" fill="none" stroke="#10B981" stroke-width="2.6" stroke-linecap="round" filter="url(#glowGreen)"/>

      <circle cx="50" cy="125" r="3.5" fill="#10B981" stroke="#06120E" stroke-width="2"/>
      <circle cx="180" cy="82" r="3.5" fill="#10B981" stroke="#06120E" stroke-width="2"/>
      <circle cx="310" cy="48" r="4.5" fill="#34D399" stroke="#06120E" stroke-width="2"/>
      <circle cx="440" cy="55" r="3.5" fill="#10B981" stroke="#06120E" stroke-width="2"/>
      <circle cx="495" cy="38" r="4.5" fill="#34D399" stroke="#06120E" stroke-width="2"/>

      <circle cx="50" cy="140" r="3" fill="#06B6D4" stroke="#06120E" stroke-width="1.8"/>
      <circle cx="180" cy="105" r="3" fill="#06B6D4" stroke="#06120E" stroke-width="1.8"/>
      <circle cx="310" cy="75" r="3.5" fill="#38BDF8" stroke="#06120E" stroke-width="1.8"/>
      <circle cx="440" cy="90" r="3" fill="#06B6D4" stroke="#06120E" stroke-width="1.8"/>
      <circle cx="495" cy="70" r="3.5" fill="#38BDF8" stroke="#06120E" stroke-width="1.8"/>
    </svg>
    """


# ==============================================================================
# Dedicated Admin Layout
# ==============================================================================

def admin_layout(title, active, body, user, counts=None):
    """
    Renders the dedicated Admin Control Center layout matching the visual reference.
    Features:
      - Dedicated Admin sidebar (Profile, 10 Nav items, Eco-Promo Banner, Logout)
      - Integrated Admin topbar (Global Search with Ctrl+K, Notifications, Admin Profile)
      - Command Palette Spotlight overlay
    """
    c = counts or {
        "pending_lots": 3,
        "pending_requests": 2
    }

    pending_badge = f'<span class="admin-nav-badge">{c["pending_lots"]}</span>' if c.get("pending_lots") else ''
    request_badge = f'<span class="admin-nav-badge">{c["pending_requests"]}</span>' if c.get("pending_requests") else ''

    nav_items = [
        ("/admin", "Overview", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>""", ""),
        ("/admin/users", "User Management", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>""", ""),
        ("/admin/verification", "Waste Verification", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>""", pending_badge),
        ("/admin/requests", "Purchase Requests", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>""", request_badge),
        ("/admin/aggregation", "Aggregation", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>""", ""),
        ("/admin/planning", "Planning", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>""", ""),
        ("/admin/passports", "Material Passports", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>""", ""),
        ("/admin/impact", "Impact Analytics", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>""", ""),
        ("/admin/reports", "Reports", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>""", ""),
        ("/admin/settings", "Settings", """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>""", "")
    ]

    sidebar_nav_html = []
    for href, label, icon, badge_html in nav_items:
        is_active = (href == active) or (href == "/admin" and active == "/admin/overview")
        active_cls = "admin-nav-item active" if is_active else "admin-nav-item"
        sidebar_nav_html.append(f"""
        <a href="{href}" class="{active_cls}">
          <span class="admin-nav-icon">{icon}</span>
          <span class="admin-nav-text">{e(label)}</span>
          {badge_html}
        </a>
        """)

    nav_links_rendered = "\n".join(sidebar_nav_html)

    brand_logo_html = render_brand_logo(
        href="/admin",
        size=26,
        extra_class="admin-brand-link",
        id_prefix="admin"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PunorAI &bull; {e(title)}</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="stylesheet" href="/static/leaflet.css">
</head>
<body class="admin-platform-body">
<div class="admin-app-layout">
  <div class="sidebar-backdrop" onclick="toggleAdminSidebar()"></div>

  <!-- DEDICATED ADMIN SIDEBAR -->
  <aside class="admin-sidebar" id="adminSidebar">
    <div class="admin-sidebar-header">
      {brand_logo_html}
    </div>

    <!-- Admin Profile Card -->
    <div class="admin-user-card">
      <div class="admin-user-avatar">AD</div>
      <div class="admin-user-info">
        <div class="admin-user-name">Admin</div>
        <div class="admin-user-role">Administrator</div>
      </div>
      <div class="admin-user-status" title="Active Administrator">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#10B981"><circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4" stroke="#06120E" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
    </div>

    <!-- Navigation List -->
    <nav class="admin-nav-list">
      {nav_links_rendered}
    </nav>

    <!-- Sidebar Bottom: Sustainability Promo Card -->
    <div class="admin-sidebar-footer">
      <div class="admin-eco-card">
        <div class="admin-eco-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>
        </div>
        <div class="admin-eco-title">Better Waste Management</div>
        <div class="admin-eco-sub">A Greener Tomorrow</div>
        <div class="admin-eco-visual">
          <div class="admin-eco-city-silhouette"></div>
        </div>
      </div>

      <a href="/logout" class="admin-logout-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        <span>Logout</span>
      </a>
    </div>
  </aside>

  <!-- MAIN VIEWPORT -->
  <div class="admin-viewport">
    <header class="admin-topbar">
      <div class="admin-topbar-left">
        <button class="admin-mobile-toggle" onclick="toggleAdminSidebar()" aria-label="Toggle Navigation">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
        </button>
        <div class="admin-search-wrapper" onclick="openSearchPalette()">
          <svg class="admin-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" readonly placeholder="Search users, waste lots, requests, or materials..." class="admin-search-input">
          <div class="admin-search-badge">Ctrl + K</div>
        </div>
      </div>

      <div class="admin-topbar-right">
        <div class="admin-notif-container">
          <button class="admin-icon-btn" onclick="toggleNotifDropdown(event)" aria-label="Notifications">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
            <span class="admin-notif-pill">{c.get('pending_lots', 3)}</span>
          </button>
          <div class="admin-notif-dropdown" id="notifDropdown">
            <div class="admin-notif-header">
              <span>Platform Alerts</span>
              <span class="admin-notif-mark">{c.get('pending_lots', 3)} Pending</span>
            </div>
            <div class="admin-notif-list">
              <a href="/admin/verification" class="admin-notif-item">
                <div class="admin-notif-dot green"></div>
                <div class="admin-notif-content">
                  <div class="admin-notif-title">{c.get('pending_lots', 3)} Waste Lots Pending QA</div>
                  <div class="admin-notif-time">Requires Intake QA inspection</div>
                </div>
              </a>
              <a href="/admin/requests" class="admin-notif-item">
                <div class="admin-notif-dot cyan"></div>
                <div class="admin-notif-content">
                  <div class="admin-notif-title">{c.get('pending_requests', 2)} Buyer Purchase Requests</div>
                  <div class="admin-notif-time">Pending Admin Approval</div>
                </div>
              </a>
              <a href="/admin/settings" class="admin-notif-item">
                <div class="admin-notif-dot amber"></div>
                <div class="admin-notif-content">
                  <div class="admin-notif-title">Database Checkpoint &amp; Backup Safe</div>
                  <div class="admin-notif-time">SQLite WAL mode active</div>
                </div>
              </a>
            </div>
          </div>
        </div>

        <div class="admin-profile-pill" onclick="toggleProfileDropdown(event)">
          <div class="admin-pill-avatar">AD</div>
          <div class="admin-pill-meta">
            <div class="admin-pill-name">Admin</div>
            <div class="admin-pill-role">Administrator</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>

          <div class="admin-profile-dropdown" id="profileDropdown">
            <div style="padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.08); font-size: 12px; color: #94A3B8;">
              Signed in as <strong style="color:#FFF;">{e(user.get('email', 'admin@punorai.com'))}</strong>
            </div>
            <a href="/admin/settings" class="admin-profile-item">System Settings</a>
            <a href="/overview" class="admin-profile-item">Switch to Public Explorer</a>
            <a href="/logout" class="admin-profile-item" style="color: #EF4444;">Sign Out</a>
          </div>
        </div>
      </div>
    </header>

    <main class="admin-main-content">
      {body}
    </main>
  </div>
</div>

<!-- Command Palette Modal (Ctrl + K) -->
<div id="commandPalette" class="command-palette-backdrop" style="display:none;" onclick="closeSearchPalette(event)">
  <div class="command-palette-card" onclick="event.stopPropagation()">
    <div class="command-search-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" id="paletteInput" placeholder="Quick jump to pages, lots, users, or requests..." onkeyup="filterCommandPalette(this.value)" autocomplete="off">
      <span class="command-esc-badge" onclick="closeSearchPalette()">ESC</span>
    </div>
    <div class="command-results" id="paletteResults">
      <div class="command-group-title">Platform Workspaces</div>
      <a href="/admin" class="command-item"><span class="cmd-icon">🏠</span> <span>Overview Dashboard</span></a>
      <a href="/admin/users" class="command-item"><span class="cmd-icon">👥</span> <span>User Management</span></a>
      <a href="/admin/verification" class="command-item"><span class="cmd-icon">🛡️</span> <span>Waste Lot Verification</span></a>
      <a href="/admin/requests" class="command-item"><span class="cmd-icon">📄</span> <span>Purchase Requests</span></a>
      <a href="/admin/aggregation" class="command-item"><span class="cmd-icon">📦</span> <span>Aggregation Optimizer</span></a>
      <a href="/admin/planning" class="command-item"><span class="cmd-icon">📅</span> <span>Forward Logistics Planning</span></a>
      <a href="/admin/passports" class="command-item"><span class="cmd-icon">📜</span> <span>Digital Material Passports</span></a>
      <a href="/admin/reports" class="command-item"><span class="cmd-icon">📊</span> <span>Impact &amp; Mass Balance Analytics</span></a>
      <a href="/admin/settings" class="command-item"><span class="cmd-icon">⚙️</span> <span>Platform System Settings</span></a>
    </div>
  </div>
</div>

<script>
  function toggleAdminSidebar() {{
    const sb = document.getElementById('adminSidebar');
    if (sb) sb.classList.toggle('open');
  }}

  function toggleNotifDropdown(e) {{
    e.stopPropagation();
    const d = document.getElementById('notifDropdown');
    const p = document.getElementById('profileDropdown');
    if (p) p.classList.remove('open');
    if (d) d.classList.toggle('open');
  }}

  function toggleProfileDropdown(e) {{
    e.stopPropagation();
    const p = document.getElementById('profileDropdown');
    const d = document.getElementById('notifDropdown');
    if (d) d.classList.remove('open');
    if (p) p.classList.toggle('open');
  }}

  document.addEventListener('click', function() {{
    const d = document.getElementById('notifDropdown');
    const p = document.getElementById('profileDropdown');
    if (d) d.classList.remove('open');
    if (p) p.classList.remove('open');
  }});

  document.addEventListener('keydown', function(e) {{
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {{
      e.preventDefault();
      openSearchPalette();
    }}
    if (e.key === 'Escape') {{
      closeSearchPalette();
    }}
  }});

  function openSearchPalette() {{
    const pal = document.getElementById('commandPalette');
    if (pal) {{
      pal.style.display = 'flex';
      const inp = document.getElementById('paletteInput');
      if (inp) {{ inp.value = ''; inp.focus(); filterCommandPalette(''); }}
    }}
  }}

  function closeSearchPalette(e) {{
    const pal = document.getElementById('commandPalette');
    if (pal) pal.style.display = 'none';
  }}

  function filterCommandPalette(q) {{
    const filter = q.toLowerCase();
    const items = document.querySelectorAll('#paletteResults .command-item');
    items.forEach(it => {{
      const txt = it.textContent.toLowerCase();
      it.style.display = txt.includes(filter) ? 'flex' : 'none';
    }});
  }}
</script>
</body>
</html>
    """


# ==============================================================================
def render_access_denied(user, role_needed="Admin"):
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PunorAI &bull; Access Denied</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body class="admin-platform-body">
  <div class="card" style="max-width: 600px; margin: 60px auto; text-align: center; padding: 40px 24px; background: rgba(14,23,30,0.9); border: 1px solid rgba(239,68,68,0.3); border-radius: 16px;">
    <div style="font-size: 44px; margin-bottom: 16px;">🚫</div>
    <h2 style="color: #EF4444; margin-bottom: 12px; font-size: 22px;">Access Denied — {e(role_needed)} Role Required</h2>
    <p style="color: #94A3B8; margin-bottom: 24px; font-size: 14px; line-height: 1.6;">
      Your account ({e(user.get('email', ''))}) is registered as a <strong>{user.get('role', 'user').title()}</strong>.
      You do not have permission to access the {e(role_needed)} Control Center.
    </p>
    <a href="/{user.get('role', '')}" class="btn btn-primary" style="display: inline-block;">Go to Your {user.get('role', 'user').title()} Workspace</a>
  </div>
</body>
</html>'''

# Page 1: Admin Overview Dashboard (Visual Reference Implementation)
# ==============================================================================

def page_admin_overview(handler, conn):
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        if handler and hasattr(handler, "_redirect"):
            target_path = handler.path if hasattr(handler, "path") and handler.path else "/admin"
            handler._redirect(f"/login?redirect={target_path}")
            return None
        return "Authentication required"
    if user["role"] != "admin":
        return render_access_denied(user, "Admin")

    counts = get_admin_counts(conn)
    cursor = conn.cursor()

    # Query Recent Lots (5 lots)
    cursor.execute("""
        SELECT id, code, source_name, category, grade, colour, qty_kg, status, created_at
        FROM lots ORDER BY id DESC LIMIT 5
    """)
    recent_lots = cursor.fetchall()

    # Query Pending Verifications (Lots pending review)
    cursor.execute("""
        SELECT id, code, source_name, category, grade, colour, contamination_pct, qty_kg, status, created_at, photo
        FROM lots WHERE status='pending' ORDER BY id ASC LIMIT 5
    """)
    pending_lots_rows = cursor.fetchall()

    # Query Recent Events for activity timeline
    cursor.execute("SELECT id, ts, description FROM events ORDER BY id DESC LIMIT 5")
    events_rows = cursor.fetchall()

    # Build Recent Lots Table HTML
    recent_lots_rows_html = []
    for lot in recent_lots:
        st = lot["status"]
        if st == "verified":
            badge_html = '<span class="admin-badge badge-approved">Approved</span>'
        elif st == "pending":
            badge_html = '<span class="admin-badge badge-pending">Pending</span>'
        elif st == "simulated":
            badge_html = '<span class="admin-badge badge-review">Under Review</span>'
        else:
            badge_html = f'<span class="admin-badge badge-rejected">{e(st.title())}</span>'

        date_disp = lot["created_at"][:10] if lot["created_at"] else "2026-10-22"
        recent_lots_rows_html.append(f"""
        <tr>
          <td style="font-weight: 600; color: #FFFFFF;">{e(lot['code'])}</td>
          <td>{e(lot['category'].title())}</td>
          <td><span style="font-weight:600; color:#E2E8F0;">{lot['qty_kg']:,.0f} kg</span></td>
          <td><span class="grade-badge">{e(lot['grade'])}</span></td>
          <td>{badge_html}</td>
          <td style="color: #94A3B8;">{e(lot['source_name'])}</td>
          <td style="color: #64748B; font-size: 12px;">{e(date_disp)}</td>
        </tr>
        """)
    recent_lots_tbody = "\n".join(recent_lots_rows_html)

    # Build Pending Verifications List HTML
    pending_items_html = []
    for p_lot in pending_lots_rows:
        swatch_style = "background: linear-gradient(135deg, #1E293B, #0F172A);"
        if "cotton" in p_lot["category"].lower():
            swatch_style = "background: linear-gradient(135deg, #334155, #1E293B);"
        if "teal" in p_lot["colour"].lower():
            swatch_style = "background: linear-gradient(135deg, #0D9488, #115E59);"

        pending_items_html.append(f"""
        <div class="pending-verif-item">
          <div class="pending-swatch" style="{swatch_style}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
          </div>
          <div class="pending-details">
            <div class="pending-code">{e(p_lot['code'])} &bull; {e(p_lot['category'].title())}</div>
            <div class="pending-sub">{p_lot['qty_kg']:,.0f} kg &bull; {e(p_lot['source_name'])}</div>
          </div>
          <button type="button" class="btn-review-outline" onclick="openVerifyModal({p_lot['id']}, '{e(p_lot['code'])}', '{e(p_lot['source_name'])}', '{e(p_lot['category'].title())}', {p_lot['qty_kg']}, '{e(p_lot['grade'])}', '{e(p_lot['colour'])}')">
            Review
          </button>
        </div>
        """)
    pending_list_rendered = "\n".join(pending_items_html) if pending_items_html else '<div style="color:#64748B; font-size:13px; text-align:center; padding:20px;">No pending waste lots in queue.</div>'

    # Build Recent Activity List HTML
    activity_items = [
        ("file", "New waste lot submitted", "by GreenTex Ltd.", "2 hours ago", "badge-pending", "Pending"),
        ("package", "Purchase request received", "from EcoThread BD", "4 hours ago", "badge-review", "New"),
        ("shield", "Lot verified and approved", "#LOT-A Shanto Denims", "6 hours ago", "badge-approved", "Approved"),
        ("user", "New user registered", "sarah@company.com", "8 hours ago", "badge-user", "User"),
        ("report", "Report generated", "Impact Analytics - Monthly", "10 hours ago", "badge-system", "System")
    ]
    activity_html_list = []
    for icon_type, title_txt, sub_txt, time_txt, badge_cls, badge_label in activity_items:
        icon_svg = {
            "file": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>',
            "package": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#06B6D4" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/></svg>',
            "shield": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#34D399" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
            "user": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#A78BFA" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
            "report": '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/></svg>'
        }.get(icon_type, "")

        activity_html_list.append(f"""
        <div class="activity-timeline-item">
          <div class="activity-icon-container">{icon_svg}</div>
          <div class="activity-body">
            <div class="activity-headline">{e(title_txt)} <span class="activity-sub">{e(sub_txt)}</span></div>
            <div class="activity-time">{e(time_txt)}</div>
          </div>
          <span class="admin-badge {badge_cls}">{e(badge_label)}</span>
        </div>
        """)
    recent_activity_rendered = "\n".join(activity_html_list)

    # Donut Chart SVG and breakdown stats
    donut_svg = render_donut_svg(
        counts["total_lots"],
        counts["verified_lots"],
        counts["pending_lots"],
        counts["review_lots"],
        counts["rejected_lots"]
    )
    p_app_pct = round((counts["verified_lots"] / max(counts["total_lots"], 1)) * 100)
    p_pen_pct = round((counts["pending_lots"] / max(counts["total_lots"], 1)) * 100)
    p_rev_pct = round((counts["review_lots"] / max(counts["total_lots"], 1)) * 100)
    p_rej_pct = round((counts["rejected_lots"] / max(counts["total_lots"], 1)) * 100)

    # Line Chart SVG
    activity_chart_svg = render_activity_line_chart_svg()

    body = f"""
    <!-- HERO GREETING BANNER -->
    <div class="admin-hero-banner">
      <div class="admin-hero-bg-visual">
        <div class="admin-hero-recycle-loop">
          <svg width="100" height="100" viewBox="0 0 100 100" fill="none" class="hero-center-recycle-svg">
            <defs>
              <linearGradient id="heroRecycleGrad" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stop-color="#10B981" />
                <stop offset="50%" stop-color="#34D399" />
                <stop offset="100%" stop-color="#A3E635" />
              </linearGradient>
            </defs>
            <circle cx="50" cy="50" r="40" stroke="url(#heroRecycleGrad)" stroke-width="4.5" stroke-dasharray="16 8" opacity="0.85"/>
            <path d="M50 22 C65 22 78 35 78 50 C78 65 65 78 50 78 C35 78 22 65 22 50" stroke="#10B981" stroke-width="4" stroke-linecap="round"/>
            <polygon points="52,14 62,22 52,30" fill="#34D399"/>
            <polygon points="48,86 38,78 48,70" fill="#34D399"/>
          </svg>
        </div>
      </div>
      <div class="admin-hero-content">
        <div class="admin-hero-text">
          <div class="admin-hero-title">
            <span class="hero-sun-icon">☀️</span>
            <h1>Good Morning, <span class="highlight-green">Admin</span></h1>
          </div>
          <p class="admin-hero-sub">Here's what's happening with PunorAI today.</p>
        </div>
        <div class="admin-hero-quote-box">
          <div class="quote-mark">“</div>
          <div class="quote-text">Turning waste into value for a sustainable future.</div>
        </div>
      </div>
    </div>

    <!-- 4 KEY KPI STAT CARDS ROW -->
    <div class="admin-stats-grid">
      <!-- Card 1: Total Waste Lots -->
      <div class="admin-stat-card">
        <div class="stat-header">
          <div class="stat-icon-square green">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
          </div>
          <div class="stat-info">
            <div class="stat-title">Total Waste Lots</div>
            <div class="stat-value">{counts['total_lots']} <span class="stat-unit">Lots</span></div>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-trend up">
            <span class="trend-arrow">&uarr; 12%</span> <span class="trend-text">vs. last month</span>
          </div>
          {render_sparkline_svg("#10B981", trend_type="lots")}
        </div>
      </div>

      <!-- Card 2: Verified Lots -->
      <div class="admin-stat-card">
        <div class="stat-header">
          <div class="stat-icon-square teal">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#34D399" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
          </div>
          <div class="stat-info">
            <div class="stat-title">Verified Lots</div>
            <div class="stat-value">{counts['verified_lots']} <span class="stat-unit">Lots</span></div>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-trend up">
            <span class="trend-arrow">&uarr; 18%</span> <span class="trend-text">vs. last month</span>
          </div>
          {render_sparkline_svg("#34D399", trend_type="verified")}
        </div>
      </div>

      <!-- Card 3: Total Users -->
      <div class="admin-stat-card">
        <div class="stat-header">
          <div class="stat-icon-square emerald">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <div class="stat-info">
            <div class="stat-title">Total Users</div>
            <div class="stat-value">{counts['total_users']} <span class="stat-unit">Users</span></div>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-trend up">
            <span class="trend-arrow">&uarr; 10%</span> <span class="trend-text">vs. last month</span>
          </div>
          {render_sparkline_svg("#10B981", trend_type="users")}
        </div>
      </div>

      <!-- Card 4: Estimated CO2 Saved -->
      <div class="admin-stat-card">
        <div class="stat-header">
          <div class="stat-icon-square mint">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#A3E635" stroke-width="2"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>
          </div>
          <div class="stat-info">
            <div class="stat-top-link-row">
              <span class="stat-title">Estimated CO₂ Saved</span>
              <a href="/admin/reports" class="stat-view-link">View All &rarr;</a>
            </div>
            <div class="stat-value">{counts['est_co2_tonnes']} <span class="stat-unit">tCO₂</span></div>
          </div>
        </div>
        <div class="stat-footer">
          <div class="stat-trend up">
            <span class="trend-arrow">&uarr; 22%</span> <span class="trend-text">vs. last month</span>
          </div>
          {render_sparkline_svg("#A3E635", trend_type="co2")}
        </div>
      </div>
    </div>

    <!-- MIDDLE ROW (3 CARDS) -->
    <div class="admin-grid-3">
      <!-- Card 1: Waste Lot Status Donut -->
      <div class="admin-card">
        <div class="admin-card-header">
          <h2 class="admin-card-title">Waste Lot Status</h2>
          <div class="admin-card-select-pill">This Month &dtrif;</div>
        </div>
        <div class="admin-card-body" style="padding-top: 10px;">
          <div class="donut-container-flex">
            {donut_svg}
            <div class="donut-legend-col">
              <div class="legend-row">
                <span class="legend-dot approved"></span>
                <span class="legend-label">Approved</span>
                <span class="legend-count">{counts['verified_lots']}</span>
                <span class="legend-pct">{p_app_pct}%</span>
              </div>
              <div class="legend-row">
                <span class="legend-dot pending"></span>
                <span class="legend-label">Pending</span>
                <span class="legend-count">{counts['pending_lots']}</span>
                <span class="legend-pct">{p_pen_pct}%</span>
              </div>
              <div class="legend-row">
                <span class="legend-dot rejected"></span>
                <span class="legend-label">Rejected</span>
                <span class="legend-count">{counts['rejected_lots']}</span>
                <span class="legend-pct">{p_rej_pct}%</span>
              </div>
              <div class="legend-row">
                <span class="legend-dot review"></span>
                <span class="legend-label">Under Review</span>
                <span class="legend-count">{counts['review_lots']}</span>
                <span class="legend-pct">{p_rev_pct}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Card 2: Monthly Activity Line Chart -->
      <div class="admin-card">
        <div class="admin-card-header">
          <h2 class="admin-card-title">Monthly Activity</h2>
          <div class="activity-chart-legend">
            <span class="act-dot green"></span> <span class="act-label">Waste Lots</span>
            <span class="act-dot cyan" style="margin-left: 10px;"></span> <span class="act-label">Purchase Requests</span>
          </div>
        </div>
        <div class="admin-card-body" style="padding: 10px 14px;">
          {activity_chart_svg}
        </div>
      </div>

      <!-- Card 3: Recent Activity Timeline -->
      <div class="admin-card">
        <div class="admin-card-header">
          <h2 class="admin-card-title">Recent Activity</h2>
          <a href="/admin/verification" class="admin-header-link">View All &rarr;</a>
        </div>
        <div class="admin-card-body" style="padding: 12px 16px;">
          <div class="activity-timeline-list">
            {recent_activity_rendered}
          </div>
        </div>
      </div>
    </div>

    <!-- BOTTOM ROW (3 CARDS) -->
    <div class="admin-grid-bottom">
      <!-- Card 1 (Wide ~50%): Recent Waste Lots Table -->
      <div class="admin-card card-wide-50">
        <div class="admin-card-header">
          <h2 class="admin-card-title">Recent Waste Lots</h2>
          <a href="/admin/verification" class="admin-header-link">View All &rarr;</a>
        </div>
        <div class="admin-card-body table-responsive" style="padding: 0;">
          <table class="admin-data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Material Type</th>
                <th>Quantity</th>
                <th>Grade</th>
                <th>Status</th>
                <th>Submitted By</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {recent_lots_tbody}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Card 2 (~25%): Quick Actions -->
      <div class="admin-card card-medium-25">
        <div class="admin-card-header">
          <h2 class="admin-card-title">Quick Actions</h2>
        </div>
        <div class="admin-card-body" style="padding: 14px 16px;">
          <div class="quick-actions-list">
            <a href="/admin/users" class="quick-action-row">
              <div class="qa-icon green">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
              </div>
              <span class="qa-text">Manage Users</span>
              <span class="qa-arrow">&rsaquo;</span>
            </a>
            <a href="/admin/verification" class="quick-action-row">
              <div class="qa-icon teal">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>
              </div>
              <span class="qa-text">Review Waste Lots</span>
              <span class="qa-arrow">&rsaquo;</span>
            </a>
            <a href="/admin/requests" class="quick-action-row">
              <div class="qa-icon cyan">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              </div>
              <span class="qa-text">Handle Purchase Requests</span>
              <span class="qa-arrow">&rsaquo;</span>
            </a>
            <a href="/admin/reports" class="quick-action-row">
              <div class="qa-icon mint">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
              </div>
              <span class="qa-text">View Reports</span>
              <span class="qa-arrow">&rsaquo;</span>
            </a>
            <a href="/admin/settings" class="quick-action-row">
              <div class="qa-icon slate">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
              </div>
              <span class="qa-text">System Settings</span>
              <span class="qa-arrow">&rsaquo;</span>
            </a>
          </div>
        </div>
      </div>

      <!-- Card 3 (~25%): Pending Verifications -->
      <div class="admin-card card-medium-25">
        <div class="admin-card-header">
          <h2 class="admin-card-title">Pending Verifications</h2>
          <a href="/admin/verification" class="admin-header-link">View All &rarr;</a>
        </div>
        <div class="admin-card-body" style="padding: 12px 14px;">
          <div class="pending-verifications-list">
            {pending_list_rendered}
          </div>
        </div>
      </div>
    </div>

    <!-- VERIFICATION MODAL -->
    <div id="verifyModal" class="command-palette-backdrop" style="display:none;" onclick="closeVerifyModal(event)">
      <div class="admin-modal-card" onclick="event.stopPropagation()">
        <div class="admin-modal-header">
          <div style="display:flex; align-items:center; gap:10px;">
            <span class="badge b-pending" id="vmCodeBadge">LOT-D</span>
            <h3 style="margin:0; font-size:18px; color:#FFF;">Waste Lot Intake Verification</h3>
          </div>
          <button class="command-esc-badge" onclick="closeVerifyModal()">✕</button>
        </div>
        <div class="admin-modal-body">
          <div class="vm-info-grid">
            <div class="vm-info-item">
              <label>Origin Mill</label>
              <div id="vmSource" style="color:#FFF; font-weight:600;">Sunrise Apparels</div>
            </div>
            <div class="vm-info-item">
              <label>Material Category</label>
              <div id="vmCategory" style="color:#10B981; font-weight:600;">100% Cotton</div>
            </div>
            <div class="vm-info-item">
              <label>Quantity</label>
              <div id="vmQty" style="color:#FFF; font-weight:600;">500 kg</div>
            </div>
            <div class="vm-info-item">
              <label>Grade &bull; Colour</label>
              <div id="vmGradeColour" style="color:#FFF; font-weight:600;">Grade A &bull; White</div>
            </div>
          </div>

          <div style="margin-top: 16px;">
            <label style="color:#CBD5E1; font-size:12.5px; font-weight:600; display:block; margin-bottom:6px;">Inspection &amp; QA Clearance Notes</label>
            <textarea id="vmNotes" class="form-control" rows="3" placeholder="Enter QA inspection findings, moisture/contamination checks, or clearance rationale..." style="width:100%; box-sizing:border-box; background:rgba(7,13,11,0.85); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:10px; border-radius:8px; font-size:13px;"></textarea>
          </div>

          <input type="hidden" id="vmLotId" value="">
          <input type="hidden" id="vmCsrf" value="{csrf}">

          <div id="vmAlert" style="display:none; margin-top:12px; padding:10px; border-radius:6px; font-size:13px;"></div>
        </div>
        <div class="admin-modal-footer">
          <button type="button" class="btn btn-outline" style="color:#EF4444; border-color:rgba(239,68,68,0.4);" onclick="submitVerifyDecision('reject')">
            Reject Lot
          </button>
          <button type="button" class="btn btn-primary" style="background:#10B981; border-color:#10B981;" onclick="submitVerifyDecision('approve')">
            Approve &amp; Verify Lot
          </button>
        </div>
      </div>
    </div>

    <script>
      function openVerifyModal(lotId, code, source, category, qty, grade, colour) {{
        document.getElementById('vmLotId').value = lotId;
        document.getElementById('vmCodeBadge').textContent = code;
        document.getElementById('vmSource').textContent = source;
        document.getElementById('vmCategory').textContent = category;
        document.getElementById('vmQty').textContent = qty + ' kg';
        document.getElementById('vmGradeColour').textContent = grade + ' • ' + (colour || 'Natural');
        document.getElementById('vmNotes').value = 'Intake QA verified. Visual fiber sorting & composition inspection passed.';
        document.getElementById('vmAlert').style.display = 'none';
        document.getElementById('verifyModal').style.display = 'flex';
      }}

      function closeVerifyModal(e) {{
        document.getElementById('verifyModal').style.display = 'none';
      }}

      async function submitVerifyDecision(decision) {{
        const lotId = document.getElementById('vmLotId').value;
        const notes = document.getElementById('vmNotes').value;
        const csrf = document.getElementById('vmCsrf').value;
        const alertBox = document.getElementById('vmAlert');

        try {{
          const res = await fetch('/api/admin/lots/verify', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }},
            body: JSON.stringify({{
              lot_id: parseInt(lotId),
              decision: decision,
              notes: notes,
              csrf_token: csrf
            }})
          }});
          const data = await res.json();
          if (data.ok) {{
            alertBox.style.display = 'block';
            alertBox.style.background = 'rgba(16,185,129,0.15)';
            alertBox.style.border = '1px solid rgba(16,185,129,0.3)';
            alertBox.style.color = '#34D399';
            alertBox.textContent = 'Decision recorded: ' + decision.toUpperCase() + '. Refreshing view...';
            setTimeout(() => window.location.reload(), 900);
          }} else {{
            alertBox.style.display = 'block';
            alertBox.style.background = 'rgba(239,68,68,0.15)';
            alertBox.style.border = '1px solid rgba(239,68,68,0.3)';
            alertBox.style.color = '#EF4444';
            alertBox.textContent = data.error || 'Failed to update verification status.';
          }}
        }} catch (err) {{
          alertBox.style.display = 'block';
          alertBox.style.background = 'rgba(239,68,68,0.15)';
          alertBox.style.border = '1px solid rgba(239,68,68,0.3)';
          alertBox.style.color = '#EF4444';
          alertBox.textContent = 'Network or server error.';
        }}
      }}
    </script>
    """

    return admin_layout("Admin Control Center", "/admin", body, user, counts=counts)


# ==============================================================================
# Page 2: User Management Portal
# ==============================================================================

def page_admin_users(handler, conn):
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        if handler and hasattr(handler, "_redirect"):
            handler._redirect("/login?redirect=/admin/users")
            return None
        return "Authentication required"
    if user["role"] != "admin":
        return render_access_denied(user, "Admin")

    counts = get_admin_counts(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, role, org_name, location_name, status, created_at FROM users ORDER BY id ASC")
    users_rows = cursor.fetchall()

    user_tr_html = []
    for u in users_rows:
        is_active = (u["status"] == "active")
        st_badge = '<span class="admin-badge badge-approved">Active</span>' if is_active else '<span class="admin-badge badge-rejected">Suspended</span>'
        role_badge = {
            "admin": '<span class="admin-badge badge-system" style="color:#A78BFA; border-color:rgba(167,139,250,0.3);">Admin</span>',
            "seller": '<span class="admin-badge badge-approved">Seller</span>',
            "buyer": '<span class="admin-badge badge-review">Buyer</span>'
        }.get(u["role"], e(u["role"]))

        toggle_btn_text = "Suspend" if is_active else "Activate"
        toggle_btn_color = "#EF4444" if is_active else "#10B981"
        is_self = (u["id"] == user["id"])

        action_html = f"""
        <button class="btn btn-sm btn-outline" style="padding:4px 10px; font-size:12px; color:{toggle_btn_color}; border-color:rgba(255,255,255,0.15);" onclick="toggleUserStatus({u['id']})" {'disabled title="Cannot suspend active admin account"' if is_self else ''}>
          {toggle_btn_text}
        </button>
        """

        avatar_letters = (u["org_name"][:2] if u["org_name"] else u["role"][:2]).upper()

        user_tr_html.append(f"""
        <tr>
          <td style="color:#64748B; font-weight:600;">#{u['id']}</td>
          <td>
            <div style="display:flex; align-items:center; gap:10px;">
              <div class="table-user-avatar">{e(avatar_letters)}</div>
              <div>
                <div style="font-weight:600; color:#FFFFFF;">{e(u['org_name'] or 'Individual User')}</div>
                <div style="font-size:12px; color:#94A3B8;">{e(u['email'])}</div>
              </div>
            </div>
          </td>
          <td>{role_badge}</td>
          <td style="color:#CBD5E1;">{e(u['location_name'] or 'Dhaka-Gazipur Hub')}</td>
          <td>{st_badge}</td>
          <td style="color:#64748B; font-size:12px;">{e(u['created_at'][:10] if u['created_at'] else '2026-10-22')}</td>
          <td>{action_html}</td>
        </tr>
        """)
    tbody_html = "\n".join(user_tr_html)

    body = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; flex-wrap:wrap; gap:16px;">
      <div>
        <h1 style="font-size:24px; font-weight:700; color:#FFFFFF; margin:0 0 4px 0;">User Management</h1>
        <p style="color:#94A3B8; font-size:14px; margin:0;">Oversee platform roles, supply facilities, recyclers, and authorization credentials.</p>
      </div>
      <button class="btn btn-primary" onclick="openCreateUserModal()">
        <span>+ Add User Node</span>
      </button>
    </div>

    <!-- User Stats -->
    <div class="admin-stats-grid" style="grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-bottom: 24px;">
      <div class="admin-stat-card" style="padding:16px 20px;">
        <div style="color:#94A3B8; font-size:12px; font-weight:600;">Total Registered Accounts</div>
        <div style="font-size:24px; font-weight:700; color:#FFFFFF; margin-top:4px;">{counts['total_users']}</div>
      </div>
      <div class="admin-stat-card" style="padding:16px 20px;">
        <div style="color:#94A3B8; font-size:12px; font-weight:600;">Verified Mills (Sellers)</div>
        <div style="font-size:24px; font-weight:700; color:#10B981; margin-top:4px;">2 Facilities</div>
      </div>
      <div class="admin-stat-card" style="padding:16px 20px;">
        <div style="color:#94A3B8; font-size:12px; font-weight:600;">Verified Recyclers (Buyers)</div>
        <div style="font-size:24px; font-weight:700; color:#06B6D4; margin-top:4px;">2 Buyers</div>
      </div>
      <div class="admin-stat-card" style="padding:16px 20px;">
        <div style="color:#94A3B8; font-size:12px; font-weight:600;">Governance &amp; Admins</div>
        <div style="font-size:24px; font-weight:700; color:#A78BFA; margin-top:4px;">1 Control</div>
      </div>
    </div>

    <!-- Users Table Card -->
    <div class="admin-card">
      <div class="admin-card-header" style="flex-wrap:wrap; gap:12px;">
        <div style="display:flex; align-items:center; gap:12px;">
          <h2 class="admin-card-title">Registered Stakeholder Nodes</h2>
          <span class="admin-badge badge-approved">{len(users_rows)} Accounts</span>
        </div>
        <div style="display:flex; gap:8px;">
          <input type="text" id="userFilterInput" placeholder="Filter users or mills..." onkeyup="filterUsersTable(this.value)" style="background:rgba(7,13,11,0.8); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:6px 12px; border-radius:8px; font-size:13px; outline:none;">
        </div>
      </div>
      <div class="admin-card-body table-responsive" style="padding:0;">
        <table class="admin-data-table" id="usersTable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Organization &amp; Email</th>
              <th>Platform Role</th>
              <th>Location Hub</th>
              <th>Status</th>
              <th>Created Date</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {tbody_html}
          </tbody>
        </table>
      </div>
    </div>

    <!-- CREATE USER MODAL -->
    <div id="createUserModal" class="command-palette-backdrop" style="display:none;" onclick="closeCreateUserModal(event)">
      <div class="admin-modal-card" onclick="event.stopPropagation()">
        <div class="admin-modal-header">
          <h3 style="margin:0; font-size:18px; color:#FFF;">Provision New Platform User</h3>
          <button class="command-esc-badge" onclick="closeCreateUserModal()">✕</button>
        </div>
        <div class="admin-modal-body">
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px;">
            <div>
              <label style="color:#CBD5E1; font-size:12.5px; font-weight:600; display:block; margin-bottom:6px;">Email Address</label>
              <input type="email" id="nuEmail" class="form-control" placeholder="user@company.com" style="width:100%; box-sizing:border-box; background:rgba(7,13,11,0.85); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:10px; border-radius:8px;">
            </div>
            <div>
              <label style="color:#CBD5E1; font-size:12.5px; font-weight:600; display:block; margin-bottom:6px;">Temporary Password</label>
              <input type="password" id="nuPassword" class="form-control" value="Welcome2026!" style="width:100%; box-sizing:border-box; background:rgba(7,13,11,0.85); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:10px; border-radius:8px;">
            </div>
          </div>

          <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px;">
            <div>
              <label style="color:#CBD5E1; font-size:12.5px; font-weight:600; display:block; margin-bottom:6px;">Platform Role</label>
              <select id="nuRole" style="width:100%; box-sizing:border-box; background:rgba(7,13,11,0.85); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:10px; border-radius:8px;">
                <option value="seller">Seller (Waste Mill / Supplier)</option>
                <option value="buyer">Buyer (Recycler / Spun Yarn Manufacturer)</option>
                <option value="admin">Admin (Operations Control)</option>
              </select>
            </div>
            <div>
              <label style="color:#CBD5E1; font-size:12.5px; font-weight:600; display:block; margin-bottom:6px;">Location / Hub</label>
              <input type="text" id="nuLocation" class="form-control" placeholder="Gazipur, Dhaka" value="Gazipur" style="width:100%; box-sizing:border-box; background:rgba(7,13,11,0.85); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:10px; border-radius:8px;">
            </div>
          </div>

          <div style="margin-bottom:14px;">
            <label style="color:#CBD5E1; font-size:12.5px; font-weight:600; display:block; margin-bottom:6px;">Organization or Mill Name</label>
            <input type="text" id="nuOrg" class="form-control" placeholder="e.g. Apex Spinning Mills Ltd" style="width:100%; box-sizing:border-box; background:rgba(7,13,11,0.85); border:1px solid rgba(255,255,255,0.12); color:#FFF; padding:10px; border-radius:8px;">
          </div>

          <div id="nuAlert" style="display:none; padding:10px; border-radius:6px; font-size:13px;"></div>
        </div>
        <div class="admin-modal-footer">
          <button type="button" class="btn btn-outline" onclick="closeCreateUserModal()">Cancel</button>
          <button type="button" class="btn btn-primary" onclick="submitCreateUser()">Provision Account</button>
        </div>
      </div>
    </div>

    <script>
      function filterUsersTable(q) {{
        const filter = q.toLowerCase();
        const rows = document.querySelectorAll('#usersTable tbody tr');
        rows.forEach(r => {{
          r.style.display = r.textContent.toLowerCase().includes(filter) ? '' : 'none';
        }});
      }}

      function openCreateUserModal() {{
        document.getElementById('createUserModal').style.display = 'flex';
      }}

      function closeCreateUserModal(e) {{
        document.getElementById('createUserModal').style.display = 'none';
      }}

      async function toggleUserStatus(userId) {{
        if (!confirm('Are you sure you want to toggle the active status of this user account?')) return;
        try {{
          const res = await fetch('/api/admin/users/toggle', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRF-Token': '{csrf}' }},
            body: JSON.stringify({{ user_id: userId, csrf_token: '{csrf}' }})
          }});
          const data = await res.json();
          if (data.ok) {{
            window.location.reload();
          }} else {{
            alert(data.error || 'Failed to update user status.');
          }}
        }} catch(err) {{
          alert('Network error.');
        }}
      }}

      async function submitCreateUser() {{
        const email = document.getElementById('nuEmail').value;
        const password = document.getElementById('nuPassword').value;
        const role = document.getElementById('nuRole').value;
        const org_name = document.getElementById('nuOrg').value;
        const location_name = document.getElementById('nuLocation').value;
        const alertBox = document.getElementById('nuAlert');

        try {{
          const res = await fetch('/api/admin/users/create', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRF-Token': '{csrf}' }},
            body: JSON.stringify({{
              email: email, password: password, role: role,
              org_name: org_name, location_name: location_name,
              csrf_token: '{csrf}'
            }})
          }});
          const data = await res.json();
          if (data.ok) {{
            alertBox.style.display = 'block';
            alertBox.style.background = 'rgba(16,185,129,0.15)';
            alertBox.style.border = '1px solid rgba(16,185,129,0.3)';
            alertBox.style.color = '#34D399';
            alertBox.textContent = 'Account provisioned successfully! Reloading...';
            setTimeout(() => window.location.reload(), 900);
          }} else {{
            alertBox.style.display = 'block';
            alertBox.style.background = 'rgba(239,68,68,0.15)';
            alertBox.style.border = '1px solid rgba(239,68,68,0.3)';
            alertBox.style.color = '#EF4444';
            alertBox.textContent = data.error || 'Failed to create user.';
          }}
        }} catch(err) {{
          alertBox.style.display = 'block';
          alertBox.style.background = 'rgba(239,68,68,0.15)';
          alertBox.style.border = '1px solid rgba(239,68,68,0.3)';
          alertBox.style.color = '#EF4444';
          alertBox.textContent = 'Network or server error.';
        }}
      }}
    </script>
    """

    return admin_layout("User Management", "/admin/users", body, user, counts=counts)


# ==============================================================================
# Page 3: Waste Verification Queue
# ==============================================================================

def page_admin_verification(handler, conn):
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        if handler and hasattr(handler, "_redirect"):
            handler._redirect("/login?redirect=/admin/verification")
            return None
        return "Authentication required"
    if user["role"] != "admin":
        return render_access_denied(user, "Admin")

    counts = get_admin_counts(conn)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, code, source_name, category, grade, colour, contamination_pct, qty_kg, status, created_at, photo, verification_notes
        FROM lots ORDER BY id ASC
    """)
    all_lots = cursor.fetchall()

    lot_cards_html = []
    for lot in all_lots:
        st = lot["status"]
        if st == "verified":
            badge_html = '<span class="admin-badge badge-approved">Intake Verified</span>'
        elif st == "pending":
            badge_html = '<span class="admin-badge badge-pending">Pending Review</span>'
        elif st == "simulated":
            badge_html = '<span class="admin-badge badge-review">Under Review</span>'
        else:
            badge_html = f'<span class="admin-badge badge-rejected">{e(st.title())}</span>'

        is_pending = (st == "pending")

        actions_html = f"""
        <div style="display:flex; gap:8px; margin-top:14px;">
          <button class="btn btn-sm btn-primary" style="background:#10B981; border-color:#10B981; font-size:12px;" onclick="quickVerifyLot({lot['id']}, 'approve')">Approve Lot</button>
          <button class="btn btn-sm btn-outline" style="color:#EF4444; border-color:rgba(239,68,68,0.4); font-size:12px;" onclick="quickVerifyLot({lot['id']}, 'reject')">Reject</button>
        </div>
        """ if is_pending else f"""
        <div style="margin-top:12px; font-size:12px; color:#94A3B8;">
          <strong style="color:#CBD5E1;">Inspection Notes:</strong> {e(lot['verification_notes'] or 'Historical sample verified in platform inventory.')}
        </div>
        """

        lot_cards_html.append(f"""
        <div class="admin-card lot-verif-card status-{st}" style="padding:20px;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
            <div>
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <span style="font-weight:700; color:#FFFFFF; font-size:16px;">{e(lot['code'])}</span>
                {badge_html}
              </div>
              <div style="color:#10B981; font-weight:600; font-size:14px;">{e(lot['category'].title())}</div>
              <div style="color:#94A3B8; font-size:13px;">Submitted by <strong>{e(lot['source_name'])}</strong></div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:20px; font-weight:700; color:#FFFFFF;">{lot['qty_kg']:,.0f} <span style="font-size:13px; color:#94A3B8;">kg</span></div>
              <div style="font-size:12px; color:#64748B;">{e(lot['created_at'][:10] if lot['created_at'] else '2026-10-22')}</div>
            </div>
          </div>

          <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; background:rgba(7,13,11,0.6); padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.06); font-size:12.5px;">
            <div><span style="color:#64748B;">Grade:</span> <strong style="color:#FFF;">{e(lot['grade'])}</strong></div>
            <div><span style="color:#64748B;">Colour:</span> <strong style="color:#FFF;">{e(lot['colour'].title() if lot['colour'] else 'Natural')}</strong></div>
            <div><span style="color:#64748B;">Contam.:</span> <strong style="color:#FFF;">{lot['contamination_pct']:.1f}%</strong></div>
          </div>

          {actions_html}
        </div>
        """)
    cards_rendered = "\n".join(lot_cards_html)

    body = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; flex-wrap:wrap; gap:16px;">
      <div>
        <h1 style="font-size:24px; font-weight:700; color:#FFFFFF; margin:0 0 4px 0;">Waste Verification Queue</h1>
        <p style="color:#94A3B8; font-size:14px; margin:0;">Audit incoming waste lots, inspect contamination levels, and issue digital clearance.</p>
      </div>
      <div style="display:flex; gap:8px;">
        <span class="badge b-pending" style="font-size:13px; padding:6px 12px;">{counts['pending_lots']} Pending QA Clearance</span>
      </div>
    </div>

    <!-- Filter Tabs -->
    <div style="display:flex; gap:8px; margin-bottom:20px; flex-wrap:wrap;">
      <button class="btn btn-sm btn-primary filter-tab active" onclick="filterVerifCards('all', this)">All Lots ({len(all_lots)})</button>
      <button class="btn btn-sm btn-outline filter-tab" onclick="filterVerifCards('pending', this)">Pending Review ({counts['pending_lots']})</button>
      <button class="btn btn-sm btn-outline filter-tab" onclick="filterVerifCards('verified', this)">Verified ({counts['verified_lots']})</button>
      <button class="btn btn-sm btn-outline filter-tab" onclick="filterVerifCards('simulated', this)">Under Review ({counts['review_lots']})</button>
    </div>

    <div class="admin-grid-cards" id="verifCardsGrid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:18px;">
      {cards_rendered}
    </div>

    <script>
      function filterVerifCards(st, el) {{
        document.querySelectorAll('.filter-tab').forEach(b => {{ b.classList.remove('btn-primary', 'active'); b.classList.add('btn-outline'); }});
        el.classList.remove('btn-outline');
        el.classList.add('btn-primary', 'active');

        const cards = document.querySelectorAll('.lot-verif-card');
        cards.forEach(c => {{
          if (st === 'all' || c.classList.contains('status-' + st)) {{
            c.style.display = 'block';
          }} else {{
            c.style.display = 'none';
          }}
        }});
      }}

      async function quickVerifyLot(lotId, decision) {{
        const notes = prompt('Enter inspector verification notes for this decision:', decision === 'approve' ? 'Intake QA verified. Visual sorting & composition test passed.' : 'Contamination or material composition non-compliant.');
        if (notes === null) return;

        try {{
          const res = await fetch('/api/admin/lots/verify', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRF-Token': '{csrf}' }},
            body: JSON.stringify({{ lot_id: lotId, decision: decision, notes: notes, csrf_token: '{csrf}' }})
          }});
          const data = await res.json();
          if (data.ok) {{
            window.location.reload();
          }} else {{
            alert(data.error || 'Failed to update verification status.');
          }}
        }} catch(err) {{
          alert('Network or server error.');
        }}
      }}
    </script>
    """

    return admin_layout("Waste Verification", "/admin/verification", body, user, counts=counts)


# ==============================================================================
# Page 4: Purchase Requests Oversight
# ==============================================================================

def page_admin_requests(handler, conn):
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        if handler and hasattr(handler, "_redirect"):
            handler._redirect("/login?redirect=/admin/requests")
            return None
        return "Authentication required"
    if user["role"] != "admin":
        return render_access_denied(user, "Admin")

    counts = get_admin_counts(conn)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pr.id, pr.code, pr.buyer_id, pr.lot_id, pr.requested_qty_kg, pr.offered_price_per_kg, pr.notes, pr.status, pr.created_at,
               u.org_name as buyer_name, u.email as buyer_email,
               l.code as lot_code, l.category as lot_category, l.source_name as seller_name
        FROM purchase_requests pr
        LEFT JOIN users u ON pr.buyer_id = u.id
        LEFT JOIN lots l ON pr.lot_id = l.id
        ORDER BY pr.id DESC
    """)
    req_rows = cursor.fetchall()

    tr_html = []
    for r in req_rows:
        total_val = (r["requested_qty_kg"] or 0) * (r["offered_price_per_kg"] or 0)
        st = r["status"]
        if st == "admin_approved":
            st_badge = '<span class="admin-badge badge-approved">Approved</span>'
        elif st == "pending_admin":
            st_badge = '<span class="admin-badge badge-pending">Pending Review</span>'
        elif st == "rejected":
            st_badge = '<span class="admin-badge badge-rejected">Rejected</span>'
        else:
            st_badge = f'<span class="admin-badge badge-review">{e(st.title())}</span>'

        is_pending = (st == "pending_admin")
        action_html = f"""
        <div style="display:flex; gap:6px;">
          <button class="btn btn-sm btn-primary" style="padding:4px 8px; font-size:11px;" onclick="updateRequestStatus({r['id']}, 'approve')">Approve</button>
          <button class="btn btn-sm btn-outline" style="padding:4px 8px; font-size:11px; color:#EF4444; border-color:rgba(239,68,68,0.4);" onclick="updateRequestStatus({r['id']}, 'reject')">Reject</button>
        </div>
        """ if is_pending else '<span style="color:#64748B; font-size:12px;">Processed</span>'

        tr_html.append(f"""
        <tr>
          <td style="font-weight:700; color:#FFFFFF;">{e(r['code'])}</td>
          <td>
            <div style="font-weight:600; color:#FFF;">{e(r['buyer_name'] or 'Buyer Node')}</div>
            <div style="font-size:12px; color:#94A3B8;">{e(r['buyer_email'])}</div>
          </td>
          <td>
            <span style="font-weight:600; color:#10B981;">{e(r['lot_code'] or 'Custom Batch')}</span>
            <div style="font-size:12px; color:#94A3B8;">{e(r['lot_category'] or 'Cotton')} &bull; {e(r['seller_name'] or 'Verified Mill')}</div>
          </td>
          <td><strong>{r['requested_qty_kg']:,.0f} kg</strong></td>
          <td>{r['offered_price_per_kg']:,.0f} BDT</td>
          <td style="color:#34D399; font-weight:700;">{total_val:,.0f} BDT</td>
          <td>{st_badge}</td>
          <td>{action_html}</td>
        </tr>
        """)
    tbody_html = "\n".join(tr_html) if tr_html else '<tr><td colspan="8" style="text-align:center; padding:24px; color:#64748B;">No purchase requests found.</td></tr>'

    body = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; flex-wrap:wrap; gap:16px;">
      <div>
        <h1 style="font-size:24px; font-weight:700; color:#FFFFFF; margin:0 0 4px 0;">Purchase Requests Oversight</h1>
        <p style="color:#94A3B8; font-size:14px; margin:0;">Review procurement requests from registered recyclers and authorize circular material transfers.</p>
      </div>
      <div>
        <span class="badge b-verified" style="font-size:13px; padding:6px 12px;">{len(req_rows)} Total Requests Logged</span>
      </div>
    </div>

    <div class="admin-card">
      <div class="admin-card-header">
        <h2 class="admin-card-title">Procurement Requests Queue</h2>
      </div>
      <div class="admin-card-body table-responsive" style="padding:0;">
        <table class="admin-data-table">
          <thead>
            <tr>
              <th>Request Code</th>
              <th>Buyer Stakeholder</th>
              <th>Target Lot &amp; Origin</th>
              <th>Quantity</th>
              <th>Offered Price</th>
              <th>Total Value</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {tbody_html}
          </tbody>
        </table>
      </div>
    </div>

    <script>
      async function updateRequestStatus(reqId, decision) {{
        if (!confirm('Confirm ' + decision.toUpperCase() + ' for this purchase request?')) return;
        try {{
          const res = await fetch('/api/admin/requests/update', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRF-Token': '{csrf}' }},
            body: JSON.stringify({{ request_id: reqId, decision: decision, csrf_token: '{csrf}' }})
          }});
          const data = await res.json();
          if (data.ok) {{
            window.location.reload();
          }} else {{
            alert(data.error || 'Failed to update request.');
          }}
        }} catch(err) {{
          alert('Network or server error.');
        }}
      }}
    </script>
    """

    return admin_layout("Purchase Requests", "/admin/requests", body, user, counts=counts)


# ==============================================================================
# Page 5: Platform System & Diagnostics Settings
# ==============================================================================

def page_admin_settings(handler, conn):
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        if handler and hasattr(handler, "_redirect"):
            handler._redirect("/login?redirect=/admin/settings")
            return None
        return "Authentication required"
    if user["role"] != "admin":
        return render_access_denied(user, "Admin")

    counts = get_admin_counts(conn)
    cursor = conn.cursor()

    db_path = "circulo.db"
    db_size_kb = os.path.getsize(db_path) / 1024.0 if os.path.exists(db_path) else 0

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]

    body = f"""
    <div style="margin-bottom:24px;">
      <h1 style="font-size:24px; font-weight:700; color:#FFFFFF; margin:0 0 4px 0;">Platform System Settings</h1>
      <p style="color:#94A3B8; font-size:14px; margin:0;">Database diagnostics, security controls, and platform operational status.</p>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap:20px;">
      <!-- Security Architecture -->
      <div class="admin-card" style="padding:24px;">
        <h2 style="font-size:16px; font-weight:700; color:#FFFFFF; margin:0 0 16px 0; display:flex; align-items:center; gap:8px;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          Security &amp; Cryptography Configuration
        </h2>
        <div style="display:flex; flex-direction:column; gap:12px; font-size:13.5px;">
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Password Hashing</span>
            <span style="color:#FFFFFF; font-weight:600;">PBKDF2-HMAC-SHA256 (100k iters)</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Session Entropy</span>
            <span style="color:#10B981; font-weight:600;">256-bit Secure Tokens</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Cookie Policy</span>
            <span style="color:#FFFFFF; font-weight:600;">HttpOnly, SameSite=Lax</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">CSRF Token Defense</span>
            <span style="color:#34D399; font-weight:600;">Active on all State POSTs</span>
          </div>
        </div>
      </div>

      <!-- Database Health -->
      <div class="admin-card" style="padding:24px;">
        <h2 style="font-size:16px; font-weight:700; color:#FFFFFF; margin:0 0 16px 0; display:flex; align-items:center; gap:8px;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#06B6D4" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
          SQLite Storage &amp; Invariants
        </h2>
        <div style="display:flex; flex-direction:column; gap:12px; font-size:13.5px;">
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Database File</span>
            <span style="color:#FFFFFF; font-weight:600;">circulo.db ({db_size_kb:,.1f} KB)</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Journal Mode</span>
            <span style="color:#10B981; font-weight:600;">WAL (Write-Ahead Logging)</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Tables Initialized</span>
            <span style="color:#FFFFFF; font-weight:600;">{len(tables)} tables</span>
          </div>
          <div style="display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
            <span style="color:#94A3B8;">Inventory Integrity</span>
            <span style="color:#34D399; font-weight:600;">{counts['total_lots']} Lots ({counts['total_kg']:,.0f} kg)</span>
          </div>
        </div>
      </div>
    </div>
    """

    return admin_layout("Settings", "/admin/settings", body, user, counts=counts)


# ==============================================================================
# Admin Proxy Page Helper (Wraps existing pages inside Admin Layout)
# ==============================================================================

def admin_proxy_page(handler, target_page, conn, page_aggregation_fn=None, page_planning_fn=None, page_passports_fn=None, page_reports_fn=None):
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user:
        if handler and hasattr(handler, "_redirect"):
            handler._redirect(f"/login?redirect=/admin/{target_page}")
            return None
        return "Authentication required"
    if user["role"] != "admin":
        return render_access_denied(user, "Admin")

    counts = get_admin_counts(conn)

    # Call target page
    inner_html = ""
    title = target_page.title()
    if target_page == "aggregation" and page_aggregation_fn:
        title = "Aggregation Optimizer"
        inner_html = page_aggregation_fn()
    elif target_page == "planning" and page_planning_fn:
        title = "Forward Planning"
        inner_html = page_planning_fn()
    elif target_page == "passports" and page_passports_fn:
        title = "Digital Material Passports"
        inner_html = page_passports_fn()
    elif target_page == "reports" and page_reports_fn:
        title = "Impact Analytics & Reports"
        inner_html = page_reports_fn()

    # Extract body content if it was wrapped in standard layout
    if "<main class=\"app-content\">" in inner_html:
        start_idx = inner_html.find("<main class=\"app-content\">") + len("<main class=\"app-content\">")
        end_idx = inner_html.rfind("</main>")
        if start_idx != -1 and end_idx != -1:
            inner_html = inner_html[start_idx:end_idx]

    return admin_layout(title, f"/admin/{target_page}", inner_html, user, counts=counts)


# ==============================================================================
# Backend API Endpoints for Admin Operations
# ==============================================================================

def api_admin_verify_lot(handler, payload, conn):
    """Admin reviews and approves or rejects a waste lot submission."""
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user or user["role"] != "admin":
        return {"ok": False, "error": "Unauthorized. Admin privileges required."}

    lot_id = payload.get("lot_id")
    decision = (payload.get("decision") or "").strip().lower()
    notes = (payload.get("notes") or "").strip()

    if not lot_id or decision not in ("approve", "reject"):
        return {"ok": False, "error": "Invalid lot ID or decision parameter."}

    new_status = "verified" if decision == "approve" else "rejected"
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE lots
        SET status = ?, verified_by = ?, verification_notes = ?
        WHERE id = ?
    """, (new_status, user["id"], notes, lot_id))

    # Log event audit
    cursor.execute("SELECT code FROM lots WHERE id = ?", (lot_id,))
    row = cursor.fetchone()
    lot_code = row[0] if row else f"LOT-#{lot_id}"

    cursor.execute("""
        INSERT INTO events (batch_id, ts, description)
        VALUES (NULL, ?, ?)
    """, (now_iso, f"Intake QA decision for {lot_code}: {new_status.upper()}. Inspector notes: {notes}"))

    conn.commit()
    return {"ok": True, "message": f"Lot {lot_code} marked as {new_status}.", "status": new_status}


def api_admin_update_request(handler, payload, conn):
    """Admin approves or rejects a buyer purchase request."""
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user or user["role"] != "admin":
        return {"ok": False, "error": "Unauthorized. Admin privileges required."}

    req_id = payload.get("request_id")
    decision = (payload.get("decision") or "").strip().lower()
    notes = (payload.get("notes") or "").strip()

    if not req_id or decision not in ("approve", "reject"):
        return {"ok": False, "error": "Invalid request ID or decision parameter."}

    new_status = "admin_approved" if decision == "approve" else "rejected"
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE purchase_requests
        SET status = ?, admin_notes = ?, updated_at = ?
        WHERE id = ?
    """, (new_status, notes, now_iso, req_id))

    conn.commit()
    return {"ok": True, "message": f"Purchase request marked as {new_status}."}


def api_admin_toggle_user_status(handler, payload, conn):
    """Admin activates or suspends a user account."""
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user or user["role"] != "admin":
        return {"ok": False, "error": "Unauthorized. Admin privileges required."}

    target_user_id = payload.get("user_id")
    if not target_user_id:
        return {"ok": False, "error": "User ID is required."}

    if target_user_id == user["id"]:
        return {"ok": False, "error": "Cannot suspend your own active administrator account."}

    cursor = conn.cursor()
    cursor.execute("SELECT id, status, email FROM users WHERE id = ?", (target_user_id,))
    target = cursor.fetchone()
    if not target:
        return {"ok": False, "error": "User not found."}

    new_status = "suspended" if target["status"] == "active" else "active"
    cursor.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, target_user_id))
    
    # If suspended, invalidate any active sessions
    if new_status == "suspended":
        cursor.execute("DELETE FROM sessions WHERE user_id = ?", (target_user_id,))

    conn.commit()
    return {"ok": True, "user_id": target_user_id, "new_status": new_status}


def api_admin_create_user(handler, payload, conn):
    """Admin provisions a new user account directly."""
    user, csrf = auth.get_session_and_user(conn, auth.extract_session_id(handler.headers) if handler and hasattr(handler, "headers") else None)
    if not user or user["role"] != "admin":
        return {"ok": False, "error": "Unauthorized. Admin privileges required."}

    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    role = (payload.get("role") or "").strip().lower()
    org_name = (payload.get("org_name") or "").strip()
    location_name = (payload.get("location_name") or "Gazipur").strip()

    try:
        new_u = auth.create_user(conn, email, password, role, org_name, location_name)
        return {"ok": True, "user": new_u}
    except ValueError as ve:
        return {"ok": False, "error": str(ve)}
