/* PunorAI — Interactive Client Logic & Dashboard Enhancements */

async function post(url, data) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {})
  });
  return r.json();
}

async function resetDemo() {
  if (!confirm('Reset all demo data to initial seed state? This restores sample factories, lots, and buyers.')) return;
  const r = await post('/api/reset');
  if (r.ok) {
    showToast('Demo data successfully reset to initial seed state.', 'success');
    setTimeout(() => location.reload(), 600);
  } else {
    alert('Reset failed: ' + (r.error || 'Unknown error'));
  }
}

/* Toast Notification Manager */
function showToast(msg, type = 'success') {
  let container = document.getElementById('circulo-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'circulo-toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'circulo-toast';
  const icon = type === 'success' ? '🍃' : '⚡';
  toast.innerHTML = `
    <div class="toast-icon">${icon}</div>
    <div class="toast-content">
      <div class="toast-title">PunorAI Live Event</div>
      <div class="toast-msg">${escapeHtml(msg)}</div>
    </div>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 350);
  }, 4000);
}

/* Task 5: Simulate New Waste Intake */
async function simulateIntake(btn) {
  if (btn) {
    btn.disabled = true;
    btn.dataset.origText = btn.innerHTML;
    btn.innerHTML = '<span class="status-dot-pulse" style="display:inline-block; margin-right:5px;"></span> Ingesting LOT-K...';
  }

  try {
    const r = await post('/api/simulate-intake', {});
    if (!r.ok) {
      showToast(r.error || 'Simulated lot already ingested', 'warn');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '✓ LOT-K Ingested';
      }
      return;
    }

    // 1. Toast Notification
    showToast(`New Waste Intake Registered: ${r.lot.code} (${parseInt(r.lot.qty_kg)}kg ${r.lot.category.charAt(0).toUpperCase() + r.lot.category.slice(1)})`, 'success');

    // 2. Animate and Update Available Waste & Registered Metrics
    const metrics = document.querySelectorAll('.card.metric');
    if (metrics.length >= 4) {
      const regMv = metrics[0].querySelector('.mv');
      const regMs = metrics[0].querySelector('.ms');
      if (regMv) {
        regMv.textContent = `${r.stats.lot_count} Lots`;
        regMv.classList.add('metric-flash');
        setTimeout(() => regMv.classList.remove('metric-flash'), 1200);
      }
      if (regMs) regMs.textContent = `${r.stats.total_kg.toLocaleString()} kg total recorded`;

      const availMv = metrics[1].querySelector('.mv');
      if (availMv) {
        availMv.textContent = `${r.stats.free_kg.toLocaleString()} kg`;
        availMv.classList.add('metric-flash');
        setTimeout(() => availMv.classList.remove('metric-flash'), 1200);
      }

      const verMv = metrics[3].querySelector('.mv');
      if (verMv) {
        verMv.textContent = `6 / ${r.stats.lot_count} Lots`;
      }
    }

    // 3. Update Landfill Diverted ESG Pills
    document.querySelectorAll('.esg-landfill-val').forEach(el => {
      el.textContent = `${r.stats.landfill_tons.toFixed(2)} Tons`;
      el.classList.add('metric-flash');
      setTimeout(() => el.classList.remove('metric-flash'), 1200);
    });

    // 4. Prepend New Row to Recent Waste Lots Table with XAI Tooltip
    const tbody = document.getElementById('recent-lots-tbody');
    if (tbody) {
      const newTr = document.createElement('tr');
      newTr.className = 'new-row-pulse';
      newTr.innerHTML = `
        <td style="min-width: 85px; white-space: nowrap;"><strong class="num">${escapeHtml(r.lot.code)}</strong></td>
        <td><b>${escapeHtml(r.lot.source_name)}</b> <span class="muted">(${escapeHtml(r.lot.source_type)})</span></td>
        <td>${escapeHtml(r.lot.category)}</td>
        <td>${escapeHtml(r.lot.grade)}</td>
        <td>${escapeHtml(r.lot.colour)}</td>
        <td><span class="num">${r.lot.contamination_pct}%</span></td>
        <td><b class="num">${parseInt(r.lot.qty_kg).toLocaleString()} kg</b></td>
        <td>${escapeHtml(r.lot.location_name)}</td>
        <td>
          <div class="xai-tooltip-wrap" tabindex="0">
            <span class="badge b-pending has-xai">Pending verification <span class="xai-tag-icon">XAI</span></span>
            <div class="xai-popover">
              <div class="xai-popover-header"><span class="xai-icon">🔬</span><strong>Explainable AI (XAI) Purity Gate</strong></div>
              <div class="xai-popover-body">Visual AI detected 85% Cotton-Poly blend. Requires physical lab or supplier tag confirmation before clearance into high-grade export recycling.</div>
              <div class="xai-popover-footer"><span>Human Confirmation Required</span><span class="xai-score">Uncertainty: &plusmn;4.2%</span></div>
            </div>
          </div>
        </td>
      `;
      tbody.insertBefore(newTr, tbody.firstChild);
    }

    // 5. Trigger brief loading spinner on AI Decision Support card & reveal new insight
    const aiOverlay = document.getElementById('ai-eval-overlay');
    if (aiOverlay) {
      aiOverlay.style.display = 'flex';
      setTimeout(() => {
        aiOverlay.style.display = 'none';

        const badgeEl = document.getElementById('ai-active-insights-badge');
        if (badgeEl) badgeEl.textContent = '4 Active Insights';

        const container = document.getElementById('insights-container');
        if (container) {
          const newCard = document.createElement('div');
          newCard.className = 'insight-item-enhanced new-row-pulse';
          newCard.innerHTML = `
            <div class="insight-badge-row">
              <span class="badge-confidence badge-feasibility" style="background:rgba(245,158,11,0.15); color:#F59E0B; border-color:rgba(245,158,11,0.3);">
                No Compatible Buyer
              </span>
              <span class="badge-confidence badge-cluster">Ashulia &bull; Denim</span>
            </div>
            <div class="insight-item" style="border: none; padding: 4px 0 0; background: transparent;">
              <div class="insight-icon" style="background:#E7F3F3; color:#1D6767;">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              </div>
              <div class="insight-body">
                <div class="insight-title">${escapeHtml(r.lot.source_name)} (${escapeHtml(r.lot.location_name)}) &mdash; ${parseInt(r.lot.qty_kg)} kg Ingested</div>
                <div class="insight-text">Newly ingested ${escapeHtml(r.lot.code)} (${parseInt(r.lot.qty_kg)} kg ${escapeHtml(r.lot.category)}) registered. No active buyer currently accepts denim feedstock. Awaiting compatible buyer intake specifications.</div>
              </div>
              <a href="/aggregation" class="insight-action">View Aggregation Planner &rarr;</a>
            </div>
          `;
          container.insertBefore(newCard, container.firstChild);
        }
      }, 700);
    }

    // 6. Update Map with new marker
    if (window.addLotToMap) {
      window.addLotToMap(r.lot);
    }
    const ashuliaKg = document.getElementById('map-ashulia-kg');
    if (ashuliaKg) ashuliaKg.textContent = '1,300 kg';
    const ashuliaCount = document.getElementById('map-ashulia-count');
    if (ashuliaCount) ashuliaCount.textContent = '3';

    // 7. Keep button disabled and clearly marked to prevent duplicate simulation
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `✓ ${r.lot.code} Ingested`;
    }
  } catch (err) {
    showToast('Simulate error: ' + err.message, 'warn');
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = btn.dataset.origText || 'Simulate New Waste Intake';
    }
  }
}

/* Task 2: Interactive Regional Cluster Map Widget (Leaflet.js) */
function initRegionalClusterMap() {
  const mapEl = document.getElementById('regional-cluster-map');
  if (!mapEl || typeof L === 'undefined') return;

  // Center on Greater Dhaka textile cluster (Gazipur, Ashulia, Dhaka, Narayanganj)
  const map = L.map('regional-cluster-map', {
    center: [23.83, 90.39],
    zoom: 10.5,
    minZoom: 9,
    maxZoom: 16,
    zoomControl: true,
    scrollWheelZoom: false
  });

  // Keyless OpenStreetMap (100% Free, Zero Watermark)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" style="color:#7E968B;">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map);

  setTimeout(() => {
    map.invalidateSize();
  }, 200);

  const colorMap = {
    'cotton': '#10B981',
    'denim': '#3B82F6',
    'cotton-polyester blend': '#14B8A6',
    'polyester': '#F59E0B',
    'mixed textile waste': '#A855F7'
  };

  const markers = [];

  function makeMarker(lot) {
    const rawCat = (lot.category || '').toLowerCase().trim();
    const color = colorMap[rawCat] || '#10B981';
    const initial = (lot.code || 'LOT').replace('LOT-', '');

    const pinIcon = L.divIcon({
      className: 'custom-map-pin',
      html: `
        <div class="pin-pulse" style="border-color:${color};"></div>
        <div class="pin-core" style="background-color:${color};">
          <span>${escapeHtml(initial)}</span>
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14]
    });

    const m = L.marker([lot.lat, lot.lon], { icon: pinIcon }).addTo(map);

    // Interactive Hover Tooltip (Requirement: LOT-A: Gazipur | 500kg Cotton)
    const capCat = lot.category ? (lot.category.charAt(0).toUpperCase() + lot.category.slice(1)) : 'Textile';
    const tooltipContent = `<strong>${escapeHtml(lot.code)}: ${escapeHtml(lot.location_name)}</strong> | ${parseInt(lot.qty_kg)}kg ${escapeHtml(capCat)}`;
    m.bindTooltip(tooltipContent, {
      direction: 'top',
      offset: [0, -10],
      className: 'leaflet-tooltip'
    });

    // Detailed Click Popup
    const popupContent = `
      <div style="font-size:12px; line-height:1.5;">
        <div style="font-weight:700; font-size:13px; color:var(--accent-lime); margin-bottom:4px;">
          ${escapeHtml(lot.code)} &bull; ${escapeHtml(lot.location_name)}
        </div>
        <div><b>Source:</b> ${escapeHtml(lot.source_name)} <span style="color:#A9C2B6">(${escapeHtml(lot.source_type)})</span></div>
        <div><b>Material:</b> ${escapeHtml(lot.category)} (Grade ${escapeHtml(lot.grade)})</div>
        <div><b>Quantity:</b> <span class="num" style="font-weight:700; color:#FFFFFF;">${parseInt(lot.qty_kg).toLocaleString()} kg</span></div>
        <div><b>Contamination:</b> <span class="num">${lot.contamination_pct}%</span></div>
        <div style="margin-top:6px; border-top:1px solid rgba(255,255,255,0.12); padding-top:4px;">
          <span class="badge b-${lot.status === 'verified' ? 'verified' : 'pending'}" style="font-size:10px;">
            ${lot.status === 'verified' ? '✓ Verified Purity' : '🔬 Pending XAI Verification'}
          </span>
        </div>
      </div>
    `;
    m.bindPopup(popupContent);
    markers.push(m);
    return m;
  }

  // Plot all initial lots
  const mapLots = window.PUNORAI_MAP_LOTS || window.CIRCULO_MAP_LOTS;
  if (mapLots && Array.isArray(mapLots)) {
    mapLots.forEach(l => makeMarker(l));
  }

  // Draw animated/dotted SVG aggregation lines connecting compatible Gazipur lots
  // Gazipur cotton circuit: LOT-I (24.0100, 90.4300) -> LOT-A (23.9999, 90.4203) -> LOT-B (23.9900, 90.4100)
  const gazipurCoords = [
    [24.0100, 90.4300],
    [23.9999, 90.4203],
    [23.9900, 90.4100]
  ];

  const gazipurLine = L.polyline(gazipurCoords, {
    color: '#B8D96B',
    weight: 4,
    opacity: 0.95,
    dashArray: '8, 8',
    className: 'corridor-flow-line'
  }).addTo(map);

  gazipurLine.bindTooltip('<strong>Aggregation in progress:</strong> Gazipur Cotton Circuit (LOT-I &rarr; LOT-A &rarr; LOT-B &bull; 730 kg)', {
    sticky: true
  });

  // Secondary extension connecting Gazipur -> Ashulia LOT-D -> Recycler X (Dhaka)
  const macroCorridorCoords = [
    [23.9900, 90.4100],
    [23.8700, 90.2700],
    [23.8103, 90.4125]
  ];

  const macroLine = L.polyline(macroCorridorCoords, {
    color: '#2A7F7F',
    weight: 3,
    opacity: 0.8,
    dashArray: '6, 6',
    className: 'corridor-flow-line-sec'
  }).addTo(map);

  macroLine.bindTooltip('<strong>Active Aggregation Routing:</strong> Ashulia &rarr; Recycler X Depot Batch Delivery (1,050 kg target)', {
    sticky: true
  });

  // Helper to dynamically add new marker live during presentation
  window.addLotToMap = function(lot) {
    const m = makeMarker(lot);
    map.panTo([lot.lat, lot.lon], { animate: true, duration: 0.8 });
    setTimeout(() => {
      m.openTooltip();
    }, 900);
  };

  window.CIRCULO_LEAFLET_MAP = map;
  window.PUNORAI_LEAFLET_MAP = map;

  window.toggleMapExpand = function() {
    const mapWrap = document.getElementById('regional-cluster-map');
    if (!mapWrap) return;
    if (mapWrap.style.height === '650px') {
      mapWrap.style.height = '460px';
    } else {
      mapWrap.style.height = '650px';
    }
    setTimeout(() => {
      map.invalidateSize();
    }, 200);
  };
}

/* Aggregation Solver Form Submission & Preselection Handling */
async function runAgg(ev) {
  if (ev) ev.preventDefault();
  const f = ev ? ev.target : document.querySelector('form[onsubmit*="runAgg"]');
  if (!f) return false;

  const resEl = document.getElementById('agg-result');
  if (resEl) {
    resEl.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted);"><div class="status-dot-pulse" style="display:inline-block; margin-right:8px;"></div> Running constraint solver over inventory...</div>';
  }

  const buyerId = f.buyer_id ? f.buyer_id.value : 1;
  const r = await post('/api/aggregate', { buyer_id: buyerId });
  if (resEl) {
    resEl.innerHTML = r.html || 'No result.';

    // Task 3: Check if lot IDs were pre-selected from AI Insight query params
    const params = new URLSearchParams(window.location.search);
    const lotsParam = params.get('lots');
    if (lotsParam) {
      const preselectedCodes = lotsParam.split(',').map(s => s.trim().toUpperCase());
      const rows = resEl.querySelectorAll('table tbody tr');
      rows.forEach(row => {
        const codeEl = row.querySelector('strong.num');
        if (codeEl && preselectedCodes.includes(codeEl.textContent.trim().toUpperCase())) {
          row.classList.add('row-preselected');
          const lastCell = row.cells[row.cells.length - 1];
          if (lastCell) {
            lastCell.innerHTML += ' <span class="badge b-verified" style="font-size:10px; margin-left:6px;">✨ Pre-Selected from AI Insight</span>';
          }
        }
      });

      // Add prominent pre-selection notification banner
      const banner = document.createElement('div');
      banner.className = 'preselected-info-banner';
      banner.innerHTML = `<strong>💡 AI Decision Support Active:</strong> Pre-selected lots (<strong>${escapeHtml(preselectedCodes.join(', '))}</strong>) automatically loaded from Dashboard constraint analysis for Recycler X. Target: 1,000 kg cotton with &le;5% contamination.`;
      resEl.insertBefore(banner, resEl.firstChild);
    }
  }
  return false;
}

async function createBatch(buyer_id, lot_ids) {
  if (!confirm(`Create candidate batch with ${lot_ids.length} selected lots and issue a Digital Material Passport?`)) return;
  const r = await post('/api/batches', { buyer_id, lot_ids });
  if (r.ok) {
    alert(`Batch ${r.code} created with Digital Material Passport.`);
    location.href = '/passports';
  } else {
    alert('Failed to create batch: ' + (r.error || ''));
  }
}

async function addLot(ev) {
  ev.preventDefault();
  const f = ev.target;
  const submitBtn = f.querySelector('button[type="submit"]');
  const originalBtnText = submitBtn ? submitBtn.innerHTML : '';
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = 'Registering lot...';
  }

  const o = {};
  new FormData(f).forEach((v, k) => o[k] = v);

  if (f.photo && f.photo.files[0]) {
    o.photo_data = await new Promise(res => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.readAsDataURL(f.photo.files[0]);
    });
  }

  try {
    const r = await post('/api/lots', o);
    const msgEl = document.getElementById('lot-msg');
    if (r.ok) {
      if (msgEl) {
        msgEl.className = 'msg';
        msgEl.innerHTML = `<strong>Success!</strong> Lot ${r.code} registered. <span class="muted">${r.note || ''}</span>`;
      }
      setTimeout(() => location.reload(), 900);
    } else {
      if (msgEl) {
        msgEl.className = 'warn';
        msgEl.textContent = 'Error: ' + (r.error || 'Failed to register lot');
      }
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalBtnText;
      }
    }
  } catch (err) {
    alert('Submission failed: ' + err.message);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnText;
    }
  }
  return false;
}

// Client-side UI enhancements: Live Search, Filter Pills, Upload Preview, Mobile Drawer, Map Init
document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize Regional Cluster Map Widget (Task 2)
  initRegionalClusterMap();

  // 2. Global / Table Live Search
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const tables = document.querySelectorAll('table');
      tables.forEach(table => {
        const rows = table.querySelectorAll('tbody tr');
        let visibleCount = 0;
        rows.forEach(row => {
          if (row.closest('thead')) return;
          const text = row.textContent.toLowerCase();
          const match = text.includes(q);
          row.style.display = match ? '' : 'none';
          if (match) visibleCount++;
        });

        let noResultRow = table.querySelector('.no-search-results');
        if (visibleCount === 0 && q.length > 0) {
          if (!noResultRow) {
            noResultRow = document.createElement('tr');
            noResultRow.className = 'no-search-results';
            noResultRow.innerHTML = `<td colspan="12" style="text-align: center; padding: 24px; color: var(--text-muted);">No records matching "<strong>${escapeHtml(q)}</strong>"</td>`;
            table.querySelector('tbody')?.appendChild(noResultRow);
          } else {
            noResultRow.style.display = '';
          }
        } else if (noResultRow) {
          noResultRow.style.display = 'none';
        }
      });
    });
  }

  // 3. Photo Upload Preview & Simulated AI Suggestion
  const photoInput = document.querySelector('input[name="photo"]');
  if (photoInput) {
    photoInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      let previewWrap = document.getElementById('photo-preview-wrap');
      if (!previewWrap) {
        previewWrap = document.createElement('div');
        previewWrap.id = 'photo-preview-wrap';
        previewWrap.className = 'upload-preview-wrap';
        photoInput.parentElement.appendChild(previewWrap);
      }
      if (file) {
        const reader = new FileReader();
        reader.onload = (re) => {
          previewWrap.innerHTML = `
            <img src="${re.target.result}" class="upload-preview-img" alt="Lot preview" />
            <div style="font-size: 12px; line-height: 1.4;">
              <span class="badge b-verified" style="margin-bottom: 4px;">AI Visual Suggestion (Simulated)</span>
              <div>Detected: <strong>High-Purity Cotton / Grade B</strong> (89% confidence)</div>
              <div class="muted">Human confirmation mandatory per platform traceability policy.</div>
            </div>
          `;
        };
        reader.readAsDataURL(file);
      } else {
        previewWrap.innerHTML = '';
      }
    });
  }

  // 4. Category & Status Filter Pills
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const parent = btn.parentElement;
      parent.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const filterVal = btn.dataset.filter?.toLowerCase() || 'all';
      const table = document.querySelector('table');
      if (!table) return;
      table.querySelectorAll('tbody tr').forEach(row => {
        if (filterVal === 'all') {
          row.style.display = '';
        } else {
          const rowText = row.textContent.toLowerCase();
          row.style.display = rowText.includes(filterVal) ? '' : 'none';
        }
      });
    });
  });

  // 5. Task 3: Automatic Execution on Aggregation Planner if params exist
  const urlParams = new URLSearchParams(window.location.search);
  const buyerId = urlParams.get('buyer_id');
  if (buyerId && (location.pathname === '/aggregation' || location.pathname === '/aggregation-planner')) {
    const buyerSelect = document.querySelector('select[name="buyer_id"]');
    if (buyerSelect) {
      buyerSelect.value = buyerId;
      setTimeout(() => {
        runAgg(null);
      }, 150);
    }
  }
});

function toggleSidebar() {
  const sidebar = document.querySelector('.app-sidebar');
  const backdrop = document.querySelector('.sidebar-backdrop');
  if (sidebar) sidebar.classList.toggle('open');
  if (backdrop) backdrop.classList.toggle('open');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
