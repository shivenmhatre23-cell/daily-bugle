/* ==========================================================================
   THE DAILY BUGLE - THEME MANAGER (DARK / LIGHT DUAL ENGINE)
   ========================================================================== */

(function () {
  // 1. Immediately apply saved theme to prevent FOUC (Flash of Unstyled Content)
  const savedTheme = localStorage.getItem("bugle_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
})();

function getActiveTheme() {
  return document.documentElement.getAttribute("data-theme") || "dark";
}

function updateThemeToggleButtons(theme) {
  const isLight = theme === "light";
  document.querySelectorAll(".theme-toggle-btn").forEach((btn) => {
    btn.setAttribute("title", isLight ? "Switch to Cyber Noir Dark Mode" : "Switch to Clean Civic Light Mode");
    btn.setAttribute("aria-label", isLight ? "Switch to Cyber Noir Dark Mode" : "Switch to Clean Civic Light Mode");
    btn.innerHTML = isLight
      ? `<span class="theme-icon">🌙</span><span class="theme-label">Dark</span>`
      : `<span class="theme-icon">☀️</span><span class="theme-label">Light</span>`;
  });
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("bugle_theme", theme);
  updateThemeToggleButtons(theme);
  window.dispatchEvent(new CustomEvent("bugle-theme-changed", { detail: { theme } }));
}

function toggleTheme() {
  const current = getActiveTheme();
  const next = current === "dark" ? "light" : "dark";
  setTheme(next);
}

document.addEventListener("DOMContentLoaded", () => {
  updateThemeToggleButtons(getActiveTheme());
});
