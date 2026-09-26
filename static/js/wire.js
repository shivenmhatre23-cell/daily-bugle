/* ==========================================================================
   THE DAILY BUGLE - CLIENT CONTROLLER: THE WIRE, RADAR & CRAZY MODE
   ========================================================================== */

let activeView = "wire"; // 'wire', 'unverified', 'radar', or 'graveyard'
let isCrazyMode = false;
let isJJJMode = false; // alias for compatibility
let leafletMap = null;
let mapMarkersGroup = null;

// Default city center (Bhubaneswar coordinates)
const DEFAULT_CENTER = [20.2961, 85.8245];
const DEFAULT_ZOOM = 13;

let currentTileLayer = null;

/* ─── Status colour palettes (dark / light per requirements) ─── */
function getTheme() {
  return document.documentElement.getAttribute("data-theme") || "dark";
}

function statusColor(inc) {
  const isLight = getTheme() === "light";
  const st = typeof inc === "string" ? inc.toUpperCase() : ((inc && inc.status) || "REVIEW").toUpperCase();
  const isLethal = typeof inc === "object" && (inc.is_lethal_priority === 1 || st === "BUSTED" || st === "SUSPICIOUS");
  const isAI = typeof inc === "object" && (inc.is_regional_cluster || (inc.category || "").toLowerCase() === "ai");
  const isInfo = typeof inc === "object" && (st === "COMMUNITY" || (inc.category || "").toLowerCase() === "civic");

  if (isLethal) return isLight ? "#E11D48" : "#FF4D6D"; // Critical 🔴
  if (isAI)     return isLight ? "#7C3AED" : "#A78BFA"; // AI Signal 🟣
  if (st === "VERIFIED" || st === "CORROBORATED") return isLight ? "#16A34A" : "#39FF88"; // Verified 🟢
  if (isInfo)   return isLight ? "#0284C7" : "#38BDF8"; // Information 🔵
  return isLight ? "#D97706" : "#FFD43B";               // Under Review 🟡
}

let activeRadarFilter = "ALL";
let radarDisplayMode = "pins"; // 'pins' or 'heat'
let showHazardRadius = true;
let currentBasemap = "osm"; // 'osm' or 'satellite'
let hazardRadiusGroup = null;
let heatLayer = null;

const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const SAT_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

function setRadarFilter(filter, btn) {
  activeRadarFilter = filter;
  document.querySelectorAll(".radar-filter-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderRadarLayers(rawFeedIncidents);
}

function setRadarDisplayMode(mode, btn) {
  radarDisplayMode = mode;
  document.querySelectorAll(".radar-view-modes .radar-mode-btn:not(#btn-toggle-radius)").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderRadarLayers(rawFeedIncidents);
}

function toggleHazardRadius(btn) {
  showHazardRadius = !showHazardRadius;
  if (btn) {
    btn.classList.toggle("active", showHazardRadius);
    btn.textContent = showHazardRadius ? "⚡ 500m Radius: ON" : "⚡ 500m Radius: OFF";
  }
  renderRadarLayers(rawFeedIncidents);
}

function setBasemap(type, btn) {
  currentBasemap = type;
  document.querySelectorAll(".radar-basemaps .radar-mode-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  setRadarTileTheme();
}

/* ─── Map Tile management (Crisp OSM + High-Res Satellite) ─── */
function setRadarTileTheme() {
  if (!leafletMap) return;
  if (currentTileLayer) leafletMap.removeLayer(currentTileLayer);

  const tilePane = leafletMap.getPane("tilePane");
  if (currentBasemap === "satellite") {
    if (tilePane) tilePane.classList.add("no-invert");
    currentTileLayer = L.tileLayer(SAT_TILE_URL, {
      attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, GIS Community',
      maxZoom: 19,
      detectRetina: true
    }).addTo(leafletMap);
  } else {
    if (tilePane) tilePane.classList.remove("no-invert");
    currentTileLayer = L.tileLayer(OSM_TILE_URL, {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
      maxZoom: 19,
      detectRetina: true
    }).addTo(leafletMap);
  }
}

/* ─── Initialise map (once) ─── */
function initRadarMap() {
  if (leafletMap) {
    setTimeout(() => leafletMap.invalidateSize(), 100);
    return;
  }
  const mapEl = document.getElementById("map-viewport");
  if (!mapEl) return;

  leafletMap = L.map("map-viewport", {
    zoomControl: true,
    scrollWheelZoom: true,
    attributionControl: true
  }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);

  setRadarTileTheme();
  hazardRadiusGroup = L.layerGroup().addTo(leafletMap);
  mapMarkersGroup = L.layerGroup().addTo(leafletMap);
}

window.addEventListener("bugle-theme-changed", () => {
  // Tile CSS handles dark/light automatically via .leaflet-tile-pane filter!
  // Re-render markers so custom marker colors update for new theme
  if (leafletMap) renderRadarLayers(rawFeedIncidents);
});

/* ─── Mock fallback data (used when API returns empty) ─── */
const MOCK_INCIDENTS = [
  {
    id: 0, title: "⚠️ Sample: Waterlogging near Patia",
    summary: "Mock data — replace with live API feed.",
    status: "COMMUNITY", category: "Obstruction",
    confidence_score: 54, report_count: 3, dispute_count: 0,
    is_spatial: 1, latitude: 20.3588, longitude: 85.8201,
    updated_at: new Date().toISOString(), is_mock: true
  },
  {
    id: 0, title: "⚠️ Sample: Fire alert KIIT Square",
    summary: "Mock data — replace with live API feed.",
    status: "VERIFIED", category: "Fire",
    confidence_score: 82, report_count: 7, dispute_count: 0,
    is_spatial: 1, latitude: 20.3533, longitude: 85.8189,
    updated_at: new Date().toISOString(), is_mock: true
  }
];

/* ─── Build rich popup HTML ─── */
function buildPopupHTML(inc) {
  const theme = getTheme();
  const color = statusColor(inc.status);
  const bg    = theme === "light" ? "#ffffff" : "#181C24";
  const txt   = theme === "light" ? "#111827" : "#F5F7FA";
  const muted = theme === "light" ? "#4B5563"  : "#9CA3AF";
  const brd   = theme === "light" ? "#DDE3EA"  : "#252A33";

  const st = (inc.status || "REVIEW").replace(/_/g, " ");
  const ts = inc.updated_at
    ? new Date(inc.updated_at).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    : "—";
  const evidenceCount = inc.report_count || 0; // reports = evidence count
  const mockWarning = inc.is_mock
    ? `<div style="background:#FEF3C7;color:#92400E;padding:4px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-bottom:8px;">⚠️ MOCK DATA — not a real incident</div>`
    : "";
  const detailLink = inc.id
    ? `<a href="/incident/${inc.id}" target="_blank"
        style="display:block;text-align:center;margin-top:10px;padding:6px 0;
               background:${color}22;border:1px solid ${color}66;border-radius:5px;
               font-size:11px;font-weight:800;color:${color};text-decoration:none;">
        View Full Details →</a>`
    : "";

  return `
    <div style="background:${bg};color:${txt};min-width:220px;max-width:280px;
                font-family:'Inter',system-ui,sans-serif;font-size:13px;line-height:1.4;
                border-radius:8px;overflow:hidden;">
      ${mockWarning}
      <!-- Status badge -->
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
        <span style="padding:2px 8px;border-radius:4px;font-size:10px;font-weight:800;
                     background:${color}22;color:${color};border:1px solid ${color}55;
                     text-transform:uppercase;letter-spacing:0.4px;">${st}</span>
        <span style="font-size:10px;color:${muted};">📂 ${inc.category || "—"}</span>
      </div>
      <!-- Title -->
      <div style="font-weight:800;font-size:14px;margin-bottom:6px;color:${txt};line-height:1.3;">
        ${inc.title}
      </div>
      <!-- Key signals -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:8px;">
        <div style="background:${brd}33;border-radius:5px;padding:5px 7px;">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.4px;color:${muted};font-weight:700;">Confidence</div>
          <div style="font-size:15px;font-weight:800;color:${color};font-family:'JetBrains Mono',monospace;">${inc.confidence_score}%</div>
        </div>
        <div style="background:${brd}33;border-radius:5px;padding:5px 7px;">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.4px;color:${muted};font-weight:700;">Reports</div>
          <div style="font-size:15px;font-weight:800;color:${txt};font-family:'JetBrains Mono',monospace;">${inc.report_count || 0}</div>
        </div>
        <div style="background:${brd}33;border-radius:5px;padding:5px 7px;">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.4px;color:${muted};font-weight:700;">Evidence</div>
          <div style="font-size:15px;font-weight:800;color:${txt};font-family:'JetBrains Mono',monospace;">${evidenceCount}</div>
        </div>
        <div style="background:${brd}33;border-radius:5px;padding:5px 7px;">
          <div style="font-size:9px;text-transform:uppercase;letter-spacing:0.4px;color:${muted};font-weight:700;">Disputes</div>
          <div style="font-size:15px;font-weight:800;color:${inc.dispute_count > 0 ? '#FF4D6D' : txt};font-family:'JetBrains Mono',monospace;">${inc.dispute_count || 0}</div>
        </div>
      </div>
      <!-- Trust bar -->
      <div style="margin-bottom:8px;">
        <div style="height:4px;background:${brd};border-radius:999px;overflow:hidden;">
          <div style="height:100%;width:${inc.confidence_score}%;background:${color};border-radius:999px;"></div>
        </div>
      </div>
      <!-- Timestamp -->
      <div style="font-size:11px;color:${muted};border-top:1px solid ${brd};padding-top:6px;margin-bottom:2px;">
        🕐 ${ts}
      </div>
      <!-- Disclaimer -->
      <div style="font-size:9px;color:${muted};font-style:italic;margin-bottom:2px;">
        Confidence ≠ certainty. Backend-verified only.
      </div>
      ${detailLink}
    </div>`;
}

/* ─── Main render function ─── */
function renderRadarLayers(incidents) {
  if (!leafletMap || !mapMarkersGroup) return;
  mapMarkersGroup.clearLayers();
  if (hazardRadiusGroup) hazardRadiusGroup.clearLayers();
  if (heatLayer) {
    leafletMap.removeLayer(heatLayer);
    heatLayer = null;
  }

  // Apply status filter
  let toPlot = (incidents || []).filter(i => i.is_spatial && i.latitude && i.longitude);

  if (activeRadarFilter !== "ALL") {
    toPlot = toPlot.filter(i => {
      const s = (i.status || "").toUpperCase();
      const isLethal = i.is_lethal_priority === 1 || s === "BUSTED" || s === "SUSPICIOUS";
      if (activeRadarFilter === "CRITICAL")     return isLethal;
      if (activeRadarFilter === "REVIEW")       return s === "REVIEW" || s === "UNVERIFIED" || s === "INVESTIGATING";
      if (activeRadarFilter === "CORROBORATED") return s === "CORROBORATED" || s === "VERIFIED";
      if (activeRadarFilter === "INFORMATION")  return s === "COMMUNITY" || (i.category || "").toLowerCase() === "civic";
      return true;
    });
  }

  // Fall back to mock data if nothing to plot
  if (toPlot.length === 0) {
    toPlot = MOCK_INCIDENTS;
  }

  const latLngs = [];

  // ─── HEATMAP DISPLAY MODE ───
  if (radarDisplayMode === "heat") {
    const heatPoints = toPlot.map(inc => {
      const isLethal = inc.is_lethal_priority === 1 || inc.status === "BUSTED" || inc.status === "SUSPICIOUS";
      const weight = isLethal ? 1.0 : (inc.confidence_score ? Math.max(0.35, inc.confidence_score / 100) : 0.6);
      latLngs.push([inc.latitude, inc.longitude]);
      return [inc.latitude, inc.longitude, weight];
    });

    if (typeof L.heatLayer === "function") {
      heatLayer = L.heatLayer(heatPoints, {
        radius: 42,
        blur: 24,
        maxZoom: 16,
        minOpacity: 0.35,
        gradient: {
          0.20: "#0284C7",
          0.45: "#38BDF8",
          0.65: "#FFD43B",
          0.85: "#FF4D6D",
          1.00: "#E11D48"
        }
      }).addTo(leafletMap);
    } else {
      // Thermal radial gradient fallback if leaflet-heat is not available
      toPlot.forEach(inc => {
        const color = statusColor(inc);
        L.circle([inc.latitude, inc.longitude], {
          radius: 700,
          color: "transparent",
          fillColor: color,
          fillOpacity: 0.12
        }).addTo(mapMarkersGroup);
        L.circle([inc.latitude, inc.longitude], {
          radius: 400,
          color: "transparent",
          fillColor: color,
          fillOpacity: 0.28
        }).addTo(mapMarkersGroup);
      });
    }

    // Keep compact interactive pins in heatmap mode for popup inspection
    toPlot.forEach(inc => {
      const color = statusColor(inc);
      const marker = L.circleMarker([inc.latitude, inc.longitude], {
        radius: 6,
        color: "#ffffff",
        weight: 1.5,
        fillColor: color,
        fillOpacity: 0.95
      }).addTo(mapMarkersGroup);
      marker.bindPopup(buildPopupHTML(inc), { maxWidth: 300 });
    });
  } else {
    // ─── PIN & 500M BLAST RADIUS MODE ───
    toPlot.forEach(inc => {
      const color = statusColor(inc);
      const isLethal = inc.is_lethal_priority === 1 || inc.status === "BUSTED" || inc.status === "SUSPICIOUS";
      const pinRadius = isLethal ? 10 : 8;

      // 500m Spatiotemporal Clustering Hazard Blast Radius
      if (showHazardRadius) {
        const blastRing = L.circle([inc.latitude, inc.longitude], {
          color: color,
          fillColor: color,
          fillOpacity: isLethal ? 0.18 : 0.09,
          weight: isLethal ? 2.5 : 1.5,
          radius: 500, // Exact 500-meter spatiotemporal clustering perimeter
          className: isLethal ? "radar-blast-500m-critical" : "radar-blast-500m"
        }).addTo(hazardRadiusGroup);

        blastRing.bindTooltip(`⚡ 500m Quorum Perimeter &bull; <b>${inc.title}</b>`, {
          sticky: true,
          direction: "top"
        });
      }

      // Centre tactical marker
      const marker = L.circleMarker([inc.latitude, inc.longitude], {
        radius: pinRadius,
        color: "#ffffff",
        weight: 2,
        fillColor: color,
        fillOpacity: 1
      }).addTo(mapMarkersGroup);

      marker.bindPopup(buildPopupHTML(inc), { maxWidth: 300 });
      latLngs.push([inc.latitude, inc.longitude]);
    });
  }

  // Fit bounds if multiple pins
  if (latLngs.length > 1) {
    try { leafletMap.fitBounds(L.latLngBounds(latLngs), { padding: [48, 48], maxZoom: 15 }); } catch (e) {}
  } else if (latLngs.length === 1) {
    leafletMap.setView(latLngs[0], 14);
  }

  // Force redraw after show
  setTimeout(() => leafletMap.invalidateSize(), 150);
}

/**
 * Builds and renders the horizontal continuous sideways marquee for Breaking Wire.
 */
function updateBreakingMarquee(incidents) {
  const track = document.getElementById("ticker-track");
  if (!track) return;

  if (!incidents || incidents.length === 0) {
    track.innerHTML = `
      <span class="ticker-item">
        <span>Monitoring municipal civic bands & emergency frequencies... No alarms logged on wire.</span>
      </span>
    `;
    return;
  }

  const categoryIcons = {
    fire: "🔥",
    obstruction: "🚗",
    assault: "🚨",
    crime: "🚨",
    civic: "⚠️",
    hazard: "☢️"
  };

  const itemsHtml = incidents.map((inc) => {
    const icon = categoryIcons[(inc.category || "").toLowerCase()] || "⚡";
    const statusClass =
      inc.status === "VERIFIED"
        ? "badge-verified"
        : inc.status === "BUSTED"
        ? "badge-busted"
        : "badge-review";

    let titleText = inc.title;
    if (isCrazyMode) {
      titleText = `CRAZY BREAKING: ${inc.title.toUpperCase()}! BUGLE BOMBSHELL!`;
    }

    return `
      <a href="/incident/${inc.id}" class="ticker-item">
        <span class="ticker-badge ${statusClass}">${inc.status}</span>
        <strong>${icon} ${titleText}</strong>
        <span style="opacity: 0.75; font-family: var(--font-mono); font-size: 0.75rem;">(${inc.confidence_score}% Trust)</span>
        <span class="ticker-sep">⚡</span>
      </a>
    `;
  }).join("");

  // Duplicate items twice to ensure a completely seamless, continuous sideways marquee loop
  track.innerHTML = itemsHtml + itemsHtml;
}

/**
 * Builds and renders the news cards grid.
 */
function renderFeedCards(incidents) {
  const container = document.getElementById("feed-grid");
  if (!container) return;

  container.innerHTML = "";

  if (incidents.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-dim);">
        <p style="font-size: 1.1rem; font-weight: 700;">No incident signals currently recorded in this view.</p>
      </div>
    `;
    return;
  }

  incidents.forEach((inc) => {
    let reasons = [];
    try {
      reasons = JSON.parse(inc.explainability_json);
    } catch (e) {
      reasons = [];
    }

    // Apply Crazy Mode sensationalism if enabled (keep the exact same issue/problem!)
    let displayTitle = inc.title;
    if (isCrazyMode) {
      displayTitle = `🚨 CRAZY SCOOP: ${inc.title.toUpperCase()}! BUGLE BOMBSHELL!`;
    }

    // Determine badge classification
    let badgeClass = "badge-review";
    if (inc.status === "VERIFIED") badgeClass = "badge-verified";
    else if (inc.status === "COMMUNITY") badgeClass = "badge-community";
    else if (inc.status === "BUSTED") badgeClass = "badge-busted";
    else if (inc.status === "INVESTIGATING") badgeClass = "badge-community";

    const formattedTime = new Date(inc.updated_at).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit"
    });

    const reasonsHtml = reasons
      .slice(0, 3)
      .map((r) => {
        const isPos = String(r.value).startsWith("+");
        const valClass = isPos ? "val-pos" : "val-neg";
        return `<li><span>${r.label}</span><span class="${valClass}">${r.value}</span></li>`;
      })
      .join("");

    const isBusted = inc.status === "BUSTED";
    const progressClass = isBusted ? "score-bar-fill danger" : "score-bar-fill";
    const isLethal = inc.is_lethal_priority === 1 || inc.injuries === "CONFIRMED";

    const card = document.createElement("article");
    card.className = "news-card";
    card.innerHTML = `
      <div>
        <div class="card-top">
          <div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">
            <span class="badge ${badgeClass}">${inc.status}</span>
            ${isLethal ? '<span style="font-size: 0.68rem; font-weight: 800; background: rgba(225,29,72,0.3); color: var(--bugle-red); border: 1px solid var(--bugle-red); padding: 1px 6px; border-radius: 3px;">🚨 PRIORITY 1</span>' : ''}
          </div>
          <span class="timestamp">${formattedTime}</span>
        </div>
        <h2 class="card-headline">
          <a href="/incident/${inc.id}" style="color: inherit; text-decoration: none;">${displayTitle}</a>
        </h2>
        <p class="card-summary">${inc.summary}</p>
      </div>

      <div class="trust-panel">
        <div class="trust-header">
          <span>Confidence Index</span>
          <span class="trust-metric-highlight">${inc.confidence_score}/100</span>
        </div>
        <div class="score-bar-track">
          <div class="${progressClass}" style="width: ${Math.max(8, inc.confidence_score)}%"></div>
        </div>
        <ul class="explainability-reasons">
          ${reasonsHtml}
        </ul>
      </div>
    `;

    container.appendChild(card);
  });
}

let rawFeedIncidents = [];
let selectedFeedCategory = "ALL";
let feedSearchQuery = "";

function applyFeedFilters() {
  const feedGrid = document.getElementById("feed-grid");

  let filtered = rawFeedIncidents;
  if (selectedFeedCategory !== "ALL") {
    filtered = filtered.filter((i) => (i.category || "").toLowerCase() === selectedFeedCategory.toLowerCase());
  }

  if (feedSearchQuery.trim()) {
    const q = feedSearchQuery.toLowerCase().trim();
    filtered = filtered.filter((i) =>
      (i.title || "").toLowerCase().includes(q) ||
      (i.summary || "").toLowerCase().includes(q) ||
      (i.category || "").toLowerCase().includes(q)
    );
  }

  if (activeView === "radar") {
    feedGrid.style.display = "none";
    const radarPanel = document.getElementById("radar-panel");
    if (radarPanel) radarPanel.style.display = "block";
    initRadarMap();
    renderRadarLayers(filtered);
    if (leafletMap) {
      setTimeout(() => leafletMap.invalidateSize(), 80);
      setTimeout(() => leafletMap.invalidateSize(), 250);
    }
  } else {
    const radarPanel = document.getElementById("radar-panel");
    if (radarPanel) radarPanel.style.display = "none";
    feedGrid.style.display = "grid";
    renderFeedCards(filtered);
  }
}

function filterFeedCategory(cat, btn) {
  selectedFeedCategory = cat;
  document.querySelectorAll(".category-filters .agency-pill").forEach((b) => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  applyFeedFilters();
}

function handleFeedSearch(val) {
  feedSearchQuery = val;
  applyFeedFilters();
}

/**
 * Queries the API and switches view state.
 */
async function fetchIncidentFeed() {
  try {
    const response = await fetch(`/api/incidents?view=${activeView}`);
    rawFeedIncidents = await response.json();
    updateBreakingMarquee(rawFeedIncidents);
    applyFeedFilters();
  } catch (error) {
    console.error("Failed to load feed data:", error);
  }
}

/**
 * Handles toolbar tab clicks (Wire, Radar, Graveyard).
 */
function switchFeedView(viewName, targetElement) {
  activeView = viewName;

  document.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.remove("active"));
  if (targetElement) {
    targetElement.classList.add("active");
  }

  fetchIncidentFeed();
}

/**
 * Toggles Crazy Mode (Sensationalist Tabloid Mode).
 */
function toggleCrazyMode(checkbox) {
  isCrazyMode = checkbox.checked;
  isJJJMode = isCrazyMode;
  const disclaimer = document.getElementById("crazy-satire-disclaimer") || document.getElementById("jjj-satire-disclaimer");

  if (isCrazyMode) {
    document.body.classList.add("crazy-mode-active", "jjj-active");
    if (disclaimer) disclaimer.style.display = "block";
  } else {
    document.body.classList.remove("crazy-mode-active", "jjj-active");
    if (disclaimer) disclaimer.style.display = "none";
  }
  fetchIncidentFeed();
}

// Backward compatibility alias for any existing bindings
function toggleJJJEditorial(checkbox) {
  toggleCrazyMode(checkbox);
}

// Initial bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  fetchIncidentFeed();
});