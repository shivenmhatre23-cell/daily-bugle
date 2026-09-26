/* ==========================================================================
   THE DAILY BUGLE — REPORTER PROFILE DRAWER
   Injects the drawer HTML, fetches /api/profile/me, renders all sections.
   Called by renderProfileBadge() in each page's syncSession function.
   ========================================================================== */

(function () {
  /* ─── Inject drawer + overlay DOM once ─── */
  function injectDrawerDOM() {
    if (document.getElementById("profile-drawer")) return;

    const overlay = document.createElement("div");
    overlay.id = "profile-overlay";
    overlay.addEventListener("click", closeProfileDrawer);
    document.body.appendChild(overlay);

    const drawer = document.createElement("div");
    drawer.id = "profile-drawer";
    drawer.innerHTML = `
      <div class="profile-drawer-header">
        <span class="profile-drawer-header-title">📰 Reporter Profile</span>
        <button class="profile-drawer-close" onclick="closeProfileDrawer()" title="Close">✕</button>
      </div>
      <div class="profile-drawer-body" id="profile-drawer-body">
        <!-- skeleton loader -->
        <div class="profile-skeleton" style="height:96px;"></div>
        <div class="profile-skeleton" style="height:130px;"></div>
        <div class="profile-skeleton" style="height:80px;"></div>
        <div class="profile-skeleton" style="height:200px;"></div>
      </div>
      <div class="profile-drawer-footer">
        <a href="/report" class="profile-footer-btn primary">🚨 File New Report</a>
        <button class="profile-footer-btn secondary" onclick="profileSignOut()">🚪 Sign Out</button>
      </div>
    `;
    document.body.appendChild(drawer);
  }

  /* ─── Open drawer ─── */
  window.openProfileDrawer = async function () {
    injectDrawerDOM();
    const overlay = document.getElementById("profile-overlay");
    const drawer = document.getElementById("profile-drawer");
    const body = document.getElementById("profile-drawer-body");
    if (overlay) overlay.classList.add("open");
    if (drawer) drawer.classList.add("open");
    if (body) body.scrollTop = 0;
    document.body.style.overflow = "hidden";
    await loadAndRenderProfile();
  };

  /* ─── Close drawer ─── */
  window.closeProfileDrawer = function () {
    const d = document.getElementById("profile-drawer");
    const o = document.getElementById("profile-overlay");
    if (d) d.classList.remove("open");
    if (o) o.classList.remove("open");
    document.body.style.overflow = "";
  };

  /* ─── ESC key closes drawer ─── */
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeProfileDrawer();
  });

  /* ─── Sign out from drawer ─── */
  window.profileSignOut = async function () {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch (e) {}
    window.location.href = "/login";
  };

  /* ─── Fetch + Render ─── */
  async function loadAndRenderProfile() {
    const body = document.getElementById("profile-drawer-body");
    if (!body) return;

    try {
      const res = await fetch("/api/profile/me");
      if (!res.ok) {
        body.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:2rem;">Could not load profile. Please sign in again.</p>`;
        return;
      }
      const data = await res.json();
      renderProfile(body, data);
    } catch (err) {
      body.innerHTML = `<p style="color:var(--bugle-red);text-align:center;padding:2rem;">Network error loading profile.</p>`;
    }
  }

  function renderProfile(body, data) {
    const { user, stats, achievements, reports } = data;

    /* Trust color */
    const tierColors = {
      elite:     { stroke: "#39FF88", bar: "#39FF88" },
      verified:  { stroke: "#38BDF8", bar: "#38BDF8" },
      community: { stroke: "#FFD43B", bar: "#FFD43B" },
      review:    { stroke: "#FF4D6D", bar: "#FF4D6D" },
      risk:      { stroke: "#A78BFA", bar: "#A78BFA" },
    };
    const colors = tierColors[user.trust_tier] || tierColors.community;

    /* SVG ring math */
    const R = 30;
    const C = 2 * Math.PI * R; // circumference ≈ 188.5
    const dashOffset = C - (C * user.trust_score_pct) / 100;

    /* Role badge color */
    const roleColors = {
      EDITOR:     "background:rgba(255,77,109,0.15);color:var(--bugle-red);border:1px solid rgba(255,77,109,0.4);",
      CITIZEN:    "background:rgba(56,189,248,0.15);color:var(--bugle-blue);border:1px solid rgba(56,189,248,0.4);",
      DISPATCHER: "background:rgba(167,139,250,0.15);color:var(--bugle-purple);border:1px solid rgba(167,139,250,0.4);",
    };
    const roleStyle = roleColors[user.role] || roleColors.CITIZEN;

    /* Join date */
    const joined = user.created_at ? new Date(user.created_at).toLocaleDateString("en-IN", { year: "numeric", month: "long" }) : "—";

    /* Quarantine warning */
    const warnHtml = (user.is_quarantined || user.strike_count >= 2) ? `
      <div class="profile-warning-banner">
        ⚠️ <span>${user.is_quarantined ? "Account quarantined — reports pending manual review." : `${user.strike_count} strike${user.strike_count > 1 ? "s" : ""} on record.`}</span>
      </div>` : "";

    /* Accuracy colour */
    const accColor = stats.accuracy_rate >= 70 ? "var(--bugle-green)" :
                     stats.accuracy_rate >= 40 ? "var(--bugle-yellow)" : "var(--bugle-red)";

    /* Achievements */
    const achievHtml = achievements.length === 0
      ? `<div class="profile-empty-achievements">📭 File more reports to earn badges.</div>`
      : achievements.map(a => `
          <div class="profile-achievement-item">
            <span class="achievement-icon">${a.icon}</span>
            <div class="achievement-text">
              <div class="achievement-label">${a.label}</div>
              <div class="achievement-desc">${a.desc}</div>
            </div>
          </div>`).join("");

    /* Report history */
    const reportHtml = reports.length === 0
      ? `<div class="profile-empty-achievements">📭 No reports filed yet. Be the first to break the story.</div>`
      : reports.slice(0, 12).map(r => {
          const st = r.incident_status || "REVIEW";
          const stLabel = st.charAt(0) + st.slice(1).toLowerCase();
          const date = r.created_at ? new Date(r.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";
          const title = r.incident_title || r.category;
          return `
            <div class="profile-report-item" onclick="window.open('/incident/${r.incident_id}','_blank')">
              <div class="profile-report-top">
                <div class="profile-report-title">${title}</div>
                <span class="profile-report-status-badge badge-${st}">${stLabel}</span>
              </div>
              <div class="profile-report-desc">${r.description}</div>
              <div class="profile-report-meta">
                <span>📂 ${r.category}</span>
                <span>🕐 ${date}</span>
                ${r.incident_confidence ? `<span>🔐 ${r.incident_confidence}% trust</span>` : ""}
                ${r.injuries && r.injuries !== "NONE" ? `<span>🚑 ${r.injuries}</span>` : ""}
              </div>
            </div>`;
        }).join("");

    const displayName = user.name || user.username || "Reporter";
    const initial = displayName.charAt(0).toUpperCase();

    body.innerHTML = `
      ${warnHtml}

      <!-- Identity -->
      <div class="profile-identity-card">
        <div class="profile-avatar">${initial}</div>
        <div class="profile-identity-info">
          <div class="profile-full-name">${displayName}</div>
          <div class="profile-username">@${user.username}</div>
          ${user.email ? `<div style="font-size:0.75rem;color:var(--text-dim);margin-bottom:0.4rem;">📧 ${user.email}</div>` : ""}
          <div class="profile-role-badges">
            <span class="profile-role-badge" style="${roleStyle}">${user.role}</span>
            ${user.is_verified ? `<span class="profile-role-badge" style="background:rgba(57,255,136,0.12);color:#39FF88;border:1px solid rgba(57,255,136,0.3);">✓ Verified</span>` : ""}
          </div>
          <div class="profile-join-date">Member since ${joined}</div>
        </div>
      </div>

      <!-- Trust Score -->
      <div class="profile-trust-block">
        <div class="profile-trust-block-header">
          <span class="profile-section-label">🔐 Credibility Score</span>
          <span style="font-family:var(--font-mono);font-size:0.78rem;font-weight:800;color:${colors.stroke};">${user.trust_score_pct}%</span>
        </div>
        <div class="profile-trust-ring-row">
          <svg class="trust-ring-svg" width="72" height="72" viewBox="0 0 72 72">
            <circle class="trust-ring-bg" cx="36" cy="36" r="${R}"/>
            <circle class="trust-ring-fill" cx="36" cy="36" r="${R}"
              stroke="${colors.stroke}"
              stroke-dasharray="${C.toFixed(1)}"
              stroke-dashoffset="${dashOffset.toFixed(1)}"/>
            <text class="trust-ring-text" x="36" y="34">${user.trust_score_pct}%</text>
            <text class="trust-ring-sublabel" x="36" y="44">trust</text>
          </svg>
          <div class="profile-trust-meta">
            <div class="profile-trust-label">${user.trust_label}</div>
            <div class="profile-trust-sublabel">
              ${user.strike_count} strike${user.strike_count !== 1 ? "s" : ""} on record.<br>
              Score updates after each verified report.
            </div>
          </div>
        </div>
        <div class="profile-trust-bar-wrap">
          <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--text-dim);">
            <span>0%</span><span>50%</span><span>100%</span>
          </div>
          <div class="profile-trust-bar-track">
            <div class="profile-trust-bar-fill" style="width:${user.trust_score_pct}%;background:${colors.bar};"></div>
          </div>
        </div>
      </div>

      <!-- Stats -->
      <div class="profile-stats-grid">
        <div class="profile-stat-card">
          <span class="profile-stat-icon">📰</span>
          <span class="profile-stat-value">${stats.total_reports}</span>
          <span class="profile-stat-label">Reports Filed</span>
        </div>
        <div class="profile-stat-card">
          <span class="profile-stat-icon">✅</span>
          <span class="profile-stat-value" style="color:var(--bugle-green);">${stats.verified_count}</span>
          <span class="profile-stat-label">Verified Incidents</span>
        </div>
        <div class="profile-stat-card">
          <span class="profile-stat-icon">🎯</span>
          <span class="profile-stat-value" style="color:${accColor};">${stats.accuracy_rate}%</span>
          <span class="profile-stat-label">Accuracy Rate</span>
        </div>
        <div class="profile-stat-card">
          <span class="profile-stat-icon">🚩</span>
          <span class="profile-stat-value">${stats.dispute_count}</span>
          <span class="profile-stat-label">Disputes Filed</span>
        </div>
      </div>

      <!-- Achievements -->
      <div class="profile-section-block">
        <span class="profile-section-label">🏅 Press Credentials & Badges</span>
        <div class="profile-achievements-grid">${achievHtml}</div>
      </div>

      <!-- Report History -->
      <div class="profile-section-block">
        <span class="profile-section-label">📋 Report History</span>
        ${reportHtml}
        ${reports.length > 12 ? `<p style="font-size:0.75rem;color:var(--text-dim);text-align:center;padding:0.5rem 0;">Showing latest 12 of ${reports.length} reports.</p>` : ""}
      </div>
    `;
  }

  /* ─── Expose badge renderer for each page's syncSession to call ─── */
  window.renderProfileBadge = function (session, containerId) {
    const container = document.getElementById(containerId || "auth-header-container");
    if (!container) return;

    const roleClass = session.role === "EDITOR" ? "role-editor"
                    : session.role === "DISPATCHER" ? "role-dispatcher"
                    : "role-citizen";

    const displayName = session.name || session.username;

    container.innerHTML = `
      <div class="user-profile-badge">
        <span class="user-name user-name-clickable" onclick="openProfileDrawer()" title="Click to view Reporter Profile">👤 ${displayName}</span>
        <span class="user-role-tag ${roleClass}">${session.role}</span>
        <button class="btn-auth-action" onclick="profileSignOut()">Sign Out</button>
      </div>
    `;
  };

})();
