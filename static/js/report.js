/* ==========================================================================
   THE DAILY BUGLE - CITIZEN REPORT FORM & SOS CONTROLLER
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  const reportForm = document.getElementById("incident-report-form");
  const latInput = document.getElementById("form-lat");
  const lngInput = document.getElementById("form-lng");
  const fileInput = document.getElementById("file-upload");
  const filenameDisplay = document.getElementById("file-selected-name");
  const categorySelect = document.getElementById("category-select");
  const submitBtn = document.getElementById("submit-btn");

  // 1. Interactive Leaflet Pin-Picker Map Setup
  const mapElem = document.getElementById("picker-map");
  const coordsLabel = document.getElementById("coords-display");
  const locationNameDisplay = document.getElementById("location-name-display");
  const addressSearchInput = document.getElementById("address-search");
  const geocodeBtn = document.getElementById("btn-geocode-search");
  const gpsBtn = document.getElementById("btn-gps-locate");
  let pickerMap = null;
  let pickerMarker = null;

  function updatePinCoords(lat, lng, label = null) {
    latInput.value = Number(lat).toFixed(6);
    lngInput.value = Number(lng).toFixed(6);
    if (coordsLabel) {
      coordsLabel.textContent = `📍 Target: ${latInput.value}° N, ${lngInput.value}° E`;
    }
    if (label && locationNameDisplay) {
      locationNameDisplay.textContent = label;
    }
  }

  if (mapElem && window.L) {
    const initialLat = parseFloat(latInput.value) || 20.2961;
    const initialLng = parseFloat(lngInput.value) || 85.8245;

    pickerMap = L.map("picker-map").setView([initialLat, initialLng], 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
      maxZoom: 19
    }).addTo(pickerMap);

    pickerMarker = L.marker([initialLat, initialLng], { draggable: true }).addTo(pickerMap);

    pickerMarker.on("dragend", (e) => {
      const pos = e.target.getLatLng();
      updatePinCoords(pos.lat, pos.lng);
      reverseGeocode(pos.lat, pos.lng);
    });

    pickerMap.on("click", (e) => {
      pickerMarker.setLatLng(e.latlng);
      updatePinCoords(e.latlng.lat, e.latlng.lng);
      reverseGeocode(e.latlng.lat, e.latlng.lng);
    });

    setTimeout(() => {
      pickerMap.invalidateSize();
    }, 200);
  }

  // Reverse Geocoding helper (debounced)
  let revTimeout = null;
  function reverseGeocode(lat, lng) {
    clearTimeout(revTimeout);
    revTimeout = setTimeout(async () => {
      try {
        const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=16`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.display_name && locationNameDisplay) {
            const shortName = data.display_name.split(",").slice(0, 3).join(",");
            locationNameDisplay.textContent = shortName;
          }
        }
      } catch (e) {}
    }, 600);
  }

  // Forward Landmark Search
  async function searchLandmark() {
    const query = addressSearchInput ? addressSearchInput.value.trim() : "";
    if (!query) return;

    if (geocodeBtn) geocodeBtn.textContent = "Searching...";
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=1`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.length > 0) {
          const item = data[0];
          const lat = parseFloat(item.lat);
          const lon = parseFloat(item.lon);
          if (pickerMap && pickerMarker) {
            pickerMap.setView([lat, lon], 15);
            pickerMarker.setLatLng([lat, lon]);
            updatePinCoords(lat, lon, item.display_name.split(",").slice(0, 3).join(","));
          }
        } else {
          alert(`No location found for "${query}". You can drag the map pin manually.`);
        }
      }
    } catch (e) {
      console.warn("Geocoding lookup failed:", e);
    } finally {
      if (geocodeBtn) geocodeBtn.textContent = "🔍 Locate";
    }
  }

  if (geocodeBtn) geocodeBtn.addEventListener("click", searchLandmark);
  if (addressSearchInput) {
    addressSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        searchLandmark();
      }
    });
  }

  // GPS Auto-Locate helper
  function acquireGPS() {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser.");
      return;
    }
    if (gpsBtn) gpsBtn.textContent = "Locating...";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const uLat = position.coords.latitude;
        const uLng = position.coords.longitude;
        updatePinCoords(uLat, uLng, "Current GPS Device Position");
        if (pickerMap && pickerMarker) {
          pickerMap.setView([uLat, uLng], 15);
          pickerMarker.setLatLng([uLat, uLng]);
        }
        if (gpsBtn) gpsBtn.textContent = "📍 My GPS";
      },
      (error) => {
        console.warn("Geolocation access denied:", error);
        if (gpsBtn) gpsBtn.textContent = "📍 My GPS";
      },
      { timeout: 8000, enableHighAccuracy: true }
    );
  }

  if (gpsBtn) gpsBtn.addEventListener("click", acquireGPS);

  // 1b. Initial GPS locate on load
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const uLat = pos.coords.latitude;
        const uLng = pos.coords.longitude;
        updatePinCoords(uLat, uLng);
        if (pickerMap && pickerMarker) {
          pickerMap.setView([uLat, uLng], 14);
          pickerMarker.setLatLng([uLat, uLng]);
        }
      },
      () => {},
      { timeout: 5000, enableHighAccuracy: false }
    );
  }

  // 2. Reflect file selection in custom UI drop-box
  if (fileInput) {
    fileInput.addEventListener("change", (e) => {
      const file = e.target.files[0];
      if (file) {
        filenameDisplay.textContent = `Attached: ${file.name} (${Math.round(file.size / 1024)} KB)`;
        filenameDisplay.style.display = "block";
      } else {
        filenameDisplay.style.display = "none";
      }
    });
  }

  // 3. Highlight relevant SOS buttons based on selected category
  if (categorySelect) {
    categorySelect.addEventListener("change", (e) => {
      const val = e.target.value;
      const policeBtn = document.getElementById("sos-police");
      const fireBtn = document.getElementById("sos-fire");
      const medicalBtn = document.getElementById("sos-ambulance");

      [policeBtn, fireBtn, medicalBtn].forEach((btn) => {
        if (btn) btn.style.boxShadow = "none";
      });

      if (val === "Assault" && policeBtn) {
        policeBtn.style.boxShadow = "0 0 12px 3px rgba(225, 29, 72, 0.9)";
      } else if (val === "Fire" && fireBtn) {
        fireBtn.style.boxShadow = "0 0 12px 3px rgba(245, 158, 11, 0.9)";
      } else if (val === "Obstruction" && medicalBtn) {
        medicalBtn.style.boxShadow = "0 0 12px 3px rgba(16, 185, 129, 0.9)";
      }
    });
  }

  // 4. Form submission handler with Modal Feedback
  if (reportForm) {
    reportForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      submitBtn.disabled = true;
      submitBtn.textContent = "🚨 Transmitting Report to Dispatch...";

      const formData = new FormData(reportForm);

      try {
        const response = await fetch("/api/reports", {
          method: "POST",
          body: formData
        });

        const result = await response.json();

        if (!response.ok || result.error) {
          alert(`Submission Notice: ${result.error || 'Failed to submit report'}`);
          return;
        }

        const modal = document.getElementById("submission-success-modal");
        const detailsContainer = document.getElementById("modal-tracking-details");
        const viewBtn = document.getElementById("modal-view-incident-btn");

        const incId = result.incident_id || (result.incident ? result.incident.id : null);
        const score = result.score !== undefined ? result.score : 50;

        if (detailsContainer) {
          detailsContainer.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
              <span style="color: var(--text-dim);">Assigned Incident File:</span>
              <strong style="color: #fff;">#${incId || 'LIVE-NEW'}</strong>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
              <span style="color: var(--text-dim);">Initial Trust Confidence:</span>
              <strong style="color: ${score >= 70 ? 'var(--bugle-green)' : 'var(--bugle-yellow)'};">${score}%</strong>
            </div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
              <span style="color: var(--text-dim);">Dispatch Channel:</span>
              <span style="color: #38bdf8; font-weight: 700;">BROADCAST TO EMERGENCY DESK</span>
            </div>
            ${result.is_guest ? `
              <div style="margin-top: 0.75rem; padding: 0.5rem; background: rgba(56,189,248,0.1); border-radius: 4px; border: 1px dashed #38bdf8; font-size: 0.78rem; color: #bae6fd;">
                ℹ️ <strong>Submitted as Guest Witness.</strong> Sign in with mobile OTP later to claim this report and build verified reporter clearance.
              </div>
            ` : ''}
          `;
        }

        if (viewBtn && incId) {
          viewBtn.href = `/incident/${incId}`;
        } else if (viewBtn) {
          viewBtn.href = `/`;
        }

        if (modal) {
          modal.style.display = "flex";
        } else {
          window.location.href = incId ? `/incident/${incId}` : "/";
        }

      } catch (err) {
        console.error("Submission failed:", err);
        alert("Transmission error: Unable to ingest report into Dispatch Network. Please try again.");
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "🚨 Submit Emergency Report (Alert Dispatch)";
      }
    });
  }
});