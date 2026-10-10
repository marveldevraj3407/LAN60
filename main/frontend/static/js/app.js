/**
 * Main application initializer, router, settings manager, and setup wizard for 60% scope.
 */

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  initNavRail();

  API.initEventStream();
  await checkUserSetup();

  DiscoveryModule.init();
  TransfersModule.init();

  initNavigation();
  initSettings();
});

function initTheme() {
  const savedTheme = localStorage.getItem("lan_theme") || "auto";
  applyTheme(savedTheme);

  const toggleBtn = document.getElementById("theme-toggle-btn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "dark" ? "light" : "dark";
      localStorage.setItem("lan_theme", next);
      applyTheme(next);
      showToast(`Switched to ${next} theme`, "info");
    });
  }

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    if (localStorage.getItem("lan_theme") === "auto" || !localStorage.getItem("lan_theme")) {
      applyTheme("auto");
    }
  });
}

function applyTheme(theme) {
  let resolved = theme;
  if (theme === "auto") {
    resolved = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", resolved);

  const iconEl = document.getElementById("theme-toggle-icon");
  if (iconEl) {
    if (resolved === "dark") {
      iconEl.innerHTML = `<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>`;
    } else {
      iconEl.innerHTML = `<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>`;
    }
  }
}

function initNavRail() {
  const rail = document.getElementById("app-nav-rail");
  const collapseBtn = document.getElementById("btn-collapse-rail");
  const isCollapsed = localStorage.getItem("lan_rail_collapsed") === "true";

  function setRailState(collapsed) {
    if (!rail) return;
    if (collapsed) {
      rail.classList.add("collapsed");
      if (collapseBtn) {
        collapseBtn.title = "Expand sidebar";
        collapseBtn.setAttribute("aria-label", "Expand navigation width");
      }
    } else {
      rail.classList.remove("collapsed");
      if (collapseBtn) {
        collapseBtn.title = "Collapse sidebar";
        collapseBtn.setAttribute("aria-label", "Collapse navigation width");
      }
    }
  }

  setRailState(isCollapsed);

  if (collapseBtn && rail) {
    collapseBtn.addEventListener("click", () => {
      const willCollapse = !rail.classList.contains("collapsed");
      setRailState(willCollapse);
      localStorage.setItem("lan_rail_collapsed", String(willCollapse));
    });
  }
}

async function checkUserSetup() {
  try {
    const status = await API.getStatus();
    const config = status.config;

    const elHostname = document.getElementById("header-hostname");
    const elIp = document.getElementById("header-ip");
    const elStatusNet = document.getElementById("status-network");

    if (elHostname) elHostname.textContent = config.hostname;
    if (elIp) elIp.textContent = config.local_ip;
    if (elStatusNet) elStatusNet.textContent = `LAN: ${config.local_ip}`;

    if (!config.has_configured_user) {
      showWelcomeModal();
    } else {
      updateUserDisplay(config.username);
    }
  } catch (err) {
    console.error("Status check failed:", err);
  }
}

function updateUserDisplay(username) {
  const elName = document.getElementById("header-username");
  const elAvatar = document.getElementById("header-avatar");
  if (elName) elName.textContent = username;
  if (elAvatar) elAvatar.textContent = username.charAt(0).toUpperCase();

  const settingsUser = document.getElementById("settings-username-input");
  if (settingsUser) settingsUser.value = username;
}

function showWelcomeModal() {
  const modal = document.getElementById("welcome-modal");
  const input = document.getElementById("welcome-username-input");
  const btnSave = document.getElementById("welcome-btn-save");
  const errBox = document.getElementById("welcome-error-msg");

  modal.classList.add("active");

  btnSave.onclick = async () => {
    const candidate = input.value.trim();
    if (!candidate) {
      errBox.textContent = "Please enter a valid username.";
      errBox.style.display = "block";
      return;
    }

    btnSave.disabled = true;
    btnSave.textContent = "Checking LAN...";
    errBox.style.display = "none";

    try {
      const res = await API.setupUser(candidate);
      if (res.success) {
        modal.classList.remove("active");
        updateUserDisplay(candidate);
        showToast(`Welcome, ${candidate}! Your profile is ready.`, "success");
        DiscoveryModule.refreshPeers();
      } else {
        errBox.textContent = res.message;
        errBox.style.display = "block";
      }
    } catch (err) {
      errBox.textContent = `Error: ${err}`;
      errBox.style.display = "block";
    } finally {
      btnSave.disabled = false;
      btnSave.textContent = "Save & Continue";
    }
  };
}

function initNavigation() {
  const navTabs = document.querySelectorAll(".nav-tab");
  window.switchTab = (tabId) => {
    navTabs.forEach((tab) => {
      if (tab.dataset.tab === tabId) {
        tab.classList.add("active");
      } else {
        tab.classList.remove("active");
      }
    });

    document.querySelectorAll(".tab-pane").forEach((pane) => {
      if (pane.id === tabId) {
        pane.classList.add("active");
      } else {
        pane.classList.remove("active");
      }
    });

    if (tabId === "tab-transfers") {
      TransfersModule.renderActiveTransfers();
    } else if (tabId === "tab-settings") {
      loadSettingsToUI();
    }
  };

  navTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      window.switchTab(tab.dataset.tab);
    });
  });
}

async function loadSettingsToUI() {
  try {
    const settings = await API.getSettings();
    const elUser = document.getElementById("settings-username-input");
    const elHost = document.getElementById("settings-hostname-display");
    const elDevId = document.getElementById("settings-deviceid-display");
    const elDlDir = document.getElementById("settings-download-dir-input");

    if (elUser) elUser.value = settings.username || "";
    if (elHost) elHost.textContent = settings.hostname;
    if (elDevId) elDevId.textContent = settings.device_id;
    if (elDlDir) elDlDir.value = settings.download_dir;
  } catch (err) {
    console.error("Failed to load settings:", err);
  }
}

function initSettings() {
  const btnChangeUser = document.getElementById("btn-change-username");
  if (btnChangeUser) {
    btnChangeUser.addEventListener("click", async () => {
      const input = document.getElementById("settings-username-input");
      const newName = input.value.trim();
      if (!newName) {
        showToast("Username cannot be empty", "error");
        return;
      }

      btnChangeUser.disabled = true;
      btnChangeUser.textContent = "Checking LAN...";
      try {
        const res = await API.updateUser(newName);
        if (res.success) {
          updateUserDisplay(newName);
          showToast("Username updated successfully!", "success");
        } else {
          showToast(res.message, "error");
        }
      } catch (err) {
        showToast(`Failed to update username: ${err}`, "error");
      } finally {
        btnChangeUser.disabled = false;
        btnChangeUser.textContent = "Change Username";
      }
    });
  }

  const btnBrowseDl = document.getElementById("btn-browse-download-dir");
  if (btnBrowseDl) {
    btnBrowseDl.addEventListener("click", async () => {
      const res = await API.chooseDownloadDirNative();
      if (res.selected) {
        document.getElementById("settings-download-dir-input").value = res.download_dir;
        showToast("Download directory updated!", "success");
      }
    });
  }

  const btnCopyDeviceId = document.getElementById("btn-copy-deviceid");
  if (btnCopyDeviceId) {
    btnCopyDeviceId.addEventListener("click", async () => {
      const devIdEl = document.getElementById("settings-deviceid-display");
      if (devIdEl && devIdEl.textContent) {
        try {
          await navigator.clipboard.writeText(devIdEl.textContent.trim());
          showToast("Device ID copied to clipboard", "success");
        } catch {
          showToast("Failed to copy Device ID", "error");
        }
      }
    });
  }

  const btnSaveSettings = document.getElementById("btn-save-settings");
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", async () => {
      const payload = {
        download_dir: document.getElementById("settings-download-dir-input").value,
      };

      try {
        const res = await API.saveSettings(payload);
        if (res.success) {
          showToast("Settings saved successfully!", "success");
        } else {
          showToast(res.message, "error");
        }
      } catch (err) {
        showToast(`Failed to save settings: ${err}`, "error");
      }
    });
  }
}

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = "toast";

  let iconName = "info";
  let statusClass = "info";
  if (type === "success") { iconName = "check-circle"; statusClass = "success"; }
  if (type === "error") { iconName = "alert-circle"; statusClass = "danger"; }
  if (type === "warning") { iconName = "alert-triangle"; statusClass = "warning"; }

  const iconSvg = typeof Icons !== "undefined"
    ? Icons.get(iconName, { size: 16, className: `toast-icon ${statusClass}` })
    : `<span class="toast-icon ${statusClass}">•</span>`;

  toast.innerHTML = `
    ${iconSvg}
    <div class="toast-text">${escapeHtml(message)}</div>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    toast.style.transition = "all 0.2s ease";
    setTimeout(() => toast.remove(), 200);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
